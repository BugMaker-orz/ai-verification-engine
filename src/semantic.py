"""语义理解模块 — 基础规则匹配 + AI 语义理解双模式。

当 AI 配置可用时，调用大模型做语义级分析；
当 AI 不可用时，自动降级为关键词/正则匹配。

设计原则：
- 基础模式零依赖、零成本、确定性结果
- AI 模式用于：语义级条款匹配、冲突误报排除、补位建议生成、字段提取增强
- AI 调用尽量少：同类任务按文档/批次合并为一次调用，
  先基础筛选、再 AI 批量二次判断，避免逐项发请求
- 提示词统一为 system（角色+输出规范）+ user（任务数据），
  输出固定 JSON 结构，解析失败自动重试一次
"""
from __future__ import annotations

import json
import re
import time
from typing import Dict, List, Optional, Tuple

from .ai_client import AIConfig, chat_completion_safe
from .rules import ClauseRule, FieldRule


# ============================================================
# 工具函数
# ============================================================

def _smart_snippet(text: str, limit: int = 3000) -> str:
    """智能截取：保留文档首部与尾部。

    合同的标题、金额、期限等关键信息常出现在首部，
    签署条款、违约责任等常在尾部；中间内容省略。
    """
    if not text:
        return ""
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    tail = limit - head
    return text[:head] + "\n……（中间内容省略）……\n" + text[-tail:]


def _extract_json(resp: str):
    """从 AI 响应中提取 JSON（对象或数组），容忍 markdown 代码块与多余文字。"""
    if not resp or not resp.strip():
        return None
    # 去掉 ```json ... ``` 代码块包裹
    m = re.search(r"```(?:json)?\s*(.*?)```", resp, re.DOTALL)
    if m:
        resp = m.group(1).strip()
    try:
        return json.loads(resp)
    except json.JSONDecodeError:
        pass
    # 兜底：提取第一个完整的 {...} 或 [...] 片段
    for pat in (r"\{.*\}", r"\[.*\]"):
        m = re.search(pat, resp, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    return None


def _chat_with_retry(config: AIConfig, messages: List[dict],
                     max_tokens: int = 200, retries: int = 1) -> Tuple[bool, str]:
    """带重试的 AI 调用：失败后等待 1s 重试一次。"""
    for attempt in range(retries + 1):
        ok, resp = chat_completion_safe(config, messages, max_tokens=max_tokens)
        if ok:
            return ok, resp
        if attempt < retries:
            time.sleep(1.0 * (attempt + 1))
    return ok, resp


def _basic_clause_match(text: str, rule: ClauseRule) -> Tuple[bool, str]:
    """基础关键词/正则匹配。"""
    for kw in rule.keywords:
        if kw in text:
            return True, f"关键词命中：{kw}"
    for pat in rule.patterns:
        if re.search(pat, text):
            return True, f"正则命中：{pat}"
    return False, "关键词/正则未命中"


# ============================================================
# 1. 条款语义匹配（支持批量）
# ============================================================

def clause_match(text: str, rule: ClauseRule, ai_config: Optional[AIConfig] = None) -> Tuple[bool, str]:
    """单条条款匹配（兼容单条调用场景）。"""
    matched, method = _basic_clause_match(text, rule)
    if matched:
        return True, method
    if ai_config and ai_config.is_ready():
        matched, reason = _ai_clause_match(text, rule, ai_config)
        if matched:
            return True, f"AI 语义命中：{reason}"
        return False, f"AI 语义未命中：{reason}"
    return False, method


def clause_match_batch(text: str, clauses: List[ClauseRule],
                       ai_config: Optional[AIConfig] = None) -> Dict[str, Tuple[bool, str]]:
    """批量条款匹配：一次请求判断全部条款。

    先对每条做基础匹配；AI 可用时，仅对基础未命中的条款
    发起一次批量语义确认。

    返回 {clause_id: (是否匹配, 匹配方式说明)}。
    """
    results: Dict[str, Tuple[bool, str]] = {}
    pending: List[ClauseRule] = []
    for rule in clauses:
        matched, method = _basic_clause_match(text, rule)
        results[rule.id] = (matched, method)
        if not matched and ai_config is not None and ai_config.is_ready():
            pending.append(rule)

    if pending and ai_config is not None and ai_config.is_ready():
        items = [
            {"id": r.id, "name": r.name, "description": r.description or "",
             "keywords": r.keywords or []}
            for r in pending
        ]
        system_msg = (
            "你是一个合同审查专家。请判断文档片段中是否包含列表中的每个条款。"
            "只输出 JSON 数组，不要任何解释。"
        )
        user_msg = (
            f"条款列表：{json.dumps(items, ensure_ascii=False)}\n\n"
            f"文档片段：\n\"\"\"\n{_smart_snippet(text)}\n\"\"\"\n\n"
            '请输出 JSON 数组：[{"id": "条款id", "matched": true或false, '
            '"reason": "20字以内说明"}]'
        )
        ok, resp = _chat_with_retry(ai_config, [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ], max_tokens=min(800, 200 + 40 * len(pending)))

        data = _extract_json(resp) if ok else None
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                rid = item.get("id")
                if rid not in results:
                    continue
                matched = bool(item.get("matched", False))
                reason = str(item.get("reason", "")).strip()
                if reason:
                    results[rid] = (matched, f"AI 语义{'命中' if matched else '未命中'}：{reason}")
                else:
                    results[rid] = (matched, "AI 语义命中" if matched else "AI 语义未命中")
        # 解析失败时保持基础匹配结果（保守降级）

    return results


def _ai_clause_match(text: str, rule: ClauseRule, config: AIConfig) -> Tuple[bool, str]:
    """单条 AI 语义判断（供 clause_match 单条路径使用）。"""
    snippet = _smart_snippet(text)
    system_msg = (
        "你是一个合同审查专家。判断文档片段中是否包含指定条款。"
        "只输出 JSON 对象，不要任何解释。"
    )
    prompt = (
        f"条款名称：{rule.name}\n"
        f"条款说明：{rule.description or '无'}\n"
        f"参考关键词：{', '.join(rule.keywords) if rule.keywords else '无'}\n\n"
        f"文档片段：\n\"\"\"\n{snippet}\n\"\"\"\n\n"
        '请输出 JSON：{"matched": true或false, "reason": "20字以内说明"}'
    )
    ok, resp = _chat_with_retry(config, [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
    ], max_tokens=200)
    if not ok:
        return False, f"AI 调用失败：{resp[:50]}"

    data = _extract_json(resp)
    if isinstance(data, dict):
        return bool(data.get("matched", False)), str(data.get("reason", ""))
    return False, "AI 返回格式无法解析"


# ============================================================
# 2. 语义级冲突检测（支持批量）
# ============================================================

def semantic_conflict_check(value_a: str, value_b: str, field_name: str,
                            ai_config: Optional[AIConfig] = None) -> Tuple[bool, str]:
    """单条语义冲突检测（兼容单条调用场景）。"""
    if not ai_config or not ai_config.is_ready():
        return True, "基础模式：文本不一致"
    results = semantic_conflict_check_batch([(field_name, value_a, value_b)], ai_config)
    return results[0]


def semantic_conflict_check_batch(pairs: List[Tuple[str, str, str]],
                                  ai_config: Optional[AIConfig] = None) -> List[Tuple[bool, str]]:
    """批量语义冲突检测：一次请求判断多组字段值对。

    pairs: [(字段名, 值A, 值B), ...]，返回同序 [(是否冲突, 说明)]。
    AI 不可用时全部保守判定为冲突；调用失败同样保守判定。
    """
    if not pairs:
        return []
    if not ai_config or not ai_config.is_ready():
        return [(True, "基础模式：文本不一致") for _ in pairs]

    items = [
        {"index": i, "field": f, "value_a": a, "value_b": b}
        for i, (f, a, b) in enumerate(pairs)
    ]
    system_msg = (
        "你是一个合同审查专家。请判断多组字段值对是否存在实质性冲突。"
        "表述不同但意思相同（如'28万元'与'280,000元'）不算冲突；"
        "无法判断时按冲突处理（保守原则）。只输出 JSON 数组，不要任何解释。"
    )
    user_msg = (
        f"待判断列表：{json.dumps(items, ensure_ascii=False)}\n\n"
        '请输出 JSON 数组：[{"index": 0, "conflict": true或false, '
        '"reason": "30字以内说明"}]'
    )
    ok, resp = _chat_with_retry(ai_config, [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ], max_tokens=min(800, 200 + 40 * len(pairs)))

    result: List[Tuple[bool, str]] = [
        (True, "AI 调用失败，保守判定为冲突") for _ in pairs
    ]
    data = _extract_json(resp) if ok else None
    if isinstance(data, list):
        by_idx = {item.get("index"): item for item in data if isinstance(item, dict)}
        for i in range(len(pairs)):
            item = by_idx.get(i)
            if item is None:
                continue
            reason = str(item.get("reason", "")).strip()
            if item.get("conflict"):
                result[i] = (True, f"AI 确认冲突：{reason}" if reason else "AI 确认冲突")
            else:
                result[i] = (False, f"AI 判定一致：{reason}" if reason else "AI 判定一致")
    return result


# ============================================================
# 3. AI 增强字段提取（支持批量）
# ============================================================

def extract_field_semantic(text: str, rule: FieldRule,
                           ai_config: Optional[AIConfig] = None) -> Tuple[Optional[str], str]:
    """单条 AI 字段提取（兼容单条调用场景）。"""
    basic = rule.extract(text)
    if basic:
        return basic, "正则提取"
    if not ai_config or not ai_config.is_ready():
        return None, "正则未命中，AI 未启用"
    results = extract_fields_semantic_batch(text, [rule], ai_config)
    return results[rule.name]


def extract_fields_semantic_batch(text: str, field_rules: List[FieldRule],
                                  ai_config: Optional[AIConfig] = None) -> Dict[str, Tuple[Optional[str], str]]:
    """批量 AI 字段提取：一次请求提取多个字段。

    field_rules: 仅传正则未命中的字段规则。
    返回 {字段名: (提取值或None, 提取方式说明)}。
    """
    result: Dict[str, Tuple[Optional[str], str]] = {
        r.name: (None, "正则未命中，AI 未启用") for r in field_rules
    }
    if not field_rules:
        return result
    if not ai_config or not ai_config.is_ready():
        return result

    items = [
        {"name": r.name, "description": r.description or "",
         "format": r.format or "不限"}
        for r in field_rules
    ]
    system_msg = (
        "你是合同信息提取助手。根据字段列表从文档片段中提取对应值；"
        "文档中没有的字段输出 null。只输出 JSON 对象，不要任何解释。"
    )
    user_msg = (
        f"字段列表：{json.dumps(items, ensure_ascii=False)}\n\n"
        f"文档片段：\n\"\"\"\n{_smart_snippet(text)}\n\"\"\"\n\n"
        '请输出 JSON 对象：{"字段名": "值" 或 null}'
    )
    ok, resp = _chat_with_retry(ai_config, [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ], max_tokens=min(800, 100 + 30 * len(items)))

    data = _extract_json(resp) if ok else None
    if isinstance(data, dict):
        for name, val in data.items():
            if name not in result:
                continue
            if val is None or (isinstance(val, str) and val.strip().upper() == "NOT_FOUND"):
                result[name] = (None, "AI 判断字段不存在")
            else:
                result[name] = (str(val).strip(), "AI 语义提取")
    return result


# ============================================================
# 4. AI 生成补位建议（支持批量）
# ============================================================

_TYPE_MAP = {
    "missing_field": "缺失必填字段",
    "missing_clause": "缺失必含条款",
    "forbidden_clause": "出现禁止条款",
    "format_invalid": "字段格式不合法",
}


def generate_remedy_suggestion(rule_name: str, description: str, finding_type: str,
                               doc_text: str = "",
                               ai_config: Optional[AIConfig] = None) -> str:
    """单条 AI 补位建议（兼容单条调用场景）。"""
    if not ai_config or not ai_config.is_ready():
        return ""
    results = generate_remedy_suggestions_batch(
        [{"type": finding_type, "name": rule_name, "description": description}],
        doc_text, ai_config,
    )
    return results[0]


def generate_remedy_suggestions_batch(items: List[dict], doc_text: str,
                                      ai_config: Optional[AIConfig] = None) -> List[str]:
    """批量 AI 补位建议：一次请求为多个欠缺项生成建议。

    items: [{"type": missing_field/missing_clause/forbidden_clause, "name": ..., "description": ...}]
    返回同序建议列表（AI 不可用或失败时为空字符串，由调用方回退默认建议）。
    """
    if not items:
        return []
    if not ai_config or not ai_config.is_ready():
        return ["" for _ in items]

    snippet = _smart_snippet(doc_text, limit=2000) if doc_text else "(未提供文档内容)"
    payload = [
        {"index": i,
         "type": _TYPE_MAP.get(it.get("type", ""), it.get("type", "")),
         "name": it.get("name", ""),
         "description": it.get("description", "")}
        for i, it in enumerate(items)
    ]
    system_msg = (
        "你是一个合同修改顾问。为下列每个合同问题给出具体、可操作的修改建议："
        "缺失条款给出建议条款内容模板，禁止条款说明风险与改法，"
        "不要客套话，每条建议 100 字以内。只输出 JSON 数组，不要任何解释。"
    )
    user_msg = (
        f"问题列表：{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"文档相关片段：\n\"\"\"\n{snippet}\n\"\"\"\n\n"
        '请输出 JSON 数组：[{"index": 0, "suggestion": "具体修改建议"}]'
    )
    ok, resp = _chat_with_retry(ai_config, [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ], max_tokens=min(1000, 200 + 60 * len(items)))

    result: List[str] = ["" for _ in items]
    data = _extract_json(resp) if ok else None
    if isinstance(data, list):
        by_idx = {item.get("index"): item for item in data if isinstance(item, dict)}
        for i in range(len(items)):
            item = by_idx.get(i)
            if item and item.get("suggestion"):
                result[i] = str(item["suggestion"]).strip()
    return result


# ============================================================
# 5. AI 生成总体审查摘要
# ============================================================

def generate_summary(score: int, grade: str, conflict_count: int, gap_count: int,
                     top_issues: List[str],
                     ai_config: Optional[AIConfig] = None) -> str:
    """AI 生成总体审查摘要和改进方向。"""
    if not ai_config or not ai_config.is_ready():
        return ""

    issues_text = "\n".join(f"- {i+1}. {issue}" for i, issue in enumerate(top_issues[:5]))
    system_msg = (
        "你是一个合同审查专家。根据验真结果给出总体评价与优先改进方向，"
        "语气专业但不生硬，避免'首先其次最后'式模板表达。"
    )
    prompt = (
        f"一份文档的验真结果：\n"
        f"- 评分：{score}/100（等级 {grade}）\n"
        f"- 跨文件冲突：{conflict_count} 处\n"
        f"- 欠缺/违规：{gap_count} 项\n"
        f"- 主要问题：\n{issues_text}\n\n"
        f"请用 3-5 句话给出总体评价和优先改进方向："
        f"先一句概括整体情况，再指出最需优先修改的 1-2 个问题并给出改进建议。"
    )
    ok, resp = _chat_with_retry(ai_config, [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
    ], max_tokens=400)
    if ok and resp:
        return resp.strip()
    return ""
