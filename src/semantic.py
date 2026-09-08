"""语义理解模块 — 基础规则匹配 + AI 语义理解双模式。

当 AI 配置可用时，调用大模型做语义级分析；
当 AI 不可用时，自动降级为关键词/正则匹配。

设计原则：
- 基础模式零依赖、零成本、确定性结果
- AI 模式用于：语义级条款匹配、冲突误报排除、补位建议生成、字段提取增强
- AI 调用尽量少（先基础筛选，再 AI 二次判断）
"""
from __future__ import annotations

import json
import re
from typing import List, Optional, Tuple

from .ai_client import AIConfig, chat_completion_safe
from .rules import ClauseRule, FieldRule


# ============================================================
# 1. 条款语义匹配
# ============================================================

def clause_match(text: str, rule: ClauseRule, ai_config: Optional[AIConfig] = None) -> Tuple[bool, str]:
    """判断文本是否包含某条款。

    返回 (是否匹配, 匹配方式说明)。
    - 基础模式：关键词/正则匹配
    - AI 模式：先关键词快速匹配，未命中时调用 AI 做语义二次判断
    """
    # 第一步：基础关键词/正则匹配
    for kw in rule.keywords:
        if kw in text:
            return True, f"关键词命中：{kw}"
    for pat in rule.patterns:
        if re.search(pat, text):
            return True, f"正则命中：{pat}"

    # 第二步：如果 AI 可用，做语义二次判断
    if ai_config and ai_config.is_ready():
        matched, reason = _ai_clause_match(text, rule, ai_config)
        if matched:
            return True, f"AI 语义命中：{reason}"
        return False, f"AI 语义未命中：{reason}"

    return False, "关键词/正则未命中"


def _ai_clause_match(text: str, rule: ClauseRule, config: AIConfig) -> Tuple[bool, str]:
    """AI 语义判断文本是否包含某条款。"""
    # 截取文本前 3000 字符，避免超长
    snippet = text[:3000]
    prompt = f"""你是一个合同审查专家。请判断以下文档片段中是否包含「{rule.name}」相关条款。

条款说明：{rule.description or '无'}
参考关键词：{', '.join(rule.keywords) if rule.keywords else '无'}

文档片段：
\"\"\"
{snippet}
\"\"\"

请只回答 JSON，不要解释：
{{"matched": true或false, "reason": "简短说明为什么命中或未命中（20字以内）"}}"""

    ok, resp = chat_completion_safe(config, [{"role": "user", "content": prompt}], max_tokens=200)
    if not ok:
        return False, f"AI 调用失败：{resp[:50]}"

    # 解析 JSON
    try:
        # 提取 JSON 部分（AI 可能加了 markdown 代码块）
        json_str = re.search(r'\{.*\}', resp, re.DOTALL)
        if json_str:
            data = json.loads(json_str.group(0))
            return bool(data.get("matched", False)), str(data.get("reason", ""))
    except (json.JSONDecodeError, AttributeError):
        pass
    return False, "AI 返回格式无法解析"


# ============================================================
# 2. 语义级冲突检测
# ============================================================

def semantic_conflict_check(value_a: str, value_b: str, field_name: str,
                             ai_config: Optional[AIConfig] = None) -> Tuple[bool, str]:
    """语义级冲突检测。

    基础模式检测到值不一致后，调用 AI 判断是否真的语义冲突
    （排除"表述不同但意思相同"的误报，如"28万元"vs"280,000元"）。

    返回 (是否冲突, 说明)。
    """
    # AI 不可用时，直接认为是冲突（基础模式已判断不一致）
    if not ai_config or not ai_config.is_ready():
        return True, "基础模式：文本不一致"

    prompt = f"""你是一个合同审查专家。请判断以下两个字段值是否存在**实质性冲突**。

字段名：{field_name}
值A：{value_a}
值B：{value_b}

判断规则：
- 如果两个值表达的是同一个意思（只是格式/表述不同），不算冲突
- 如果两个值在金额、日期、名称、数量等实质上不同，算冲突
- 如果无法判断，算冲突（保守原则）

请只回答 JSON：
{{"conflict": true或false, "reason": "简短说明（30字以内）"}}"""

    ok, resp = chat_completion_safe(ai_config, [{"role": "user", "content": prompt}], max_tokens=200)
    if not ok:
        return True, f"AI 调用失败，保守判定为冲突：{resp[:50]}"

    try:
        json_str = re.search(r'\{.*\}', resp, re.DOTALL)
        if json_str:
            data = json.loads(json_str.group(0))
            return bool(data.get("conflict", True)), str(data.get("reason", ""))
    except (json.JSONDecodeError, AttributeError):
        pass
    return True, "AI 返回格式无法解析，保守判定为冲突"


# ============================================================
# 3. AI 增强字段提取
# ============================================================

def extract_field_semantic(text: str, rule: FieldRule,
                            ai_config: Optional[AIConfig] = None) -> Tuple[Optional[str], str]:
    """AI 增强字段提取。基础正则提取失败时，调用 AI 提取。

    返回 (提取值或None, 提取方式说明)。
    """
    # 先基础提取
    basic = rule.extract(text)
    if basic:
        return basic, "正则提取"

    # AI 不可用
    if not ai_config or not ai_config.is_ready():
        return None, "正则未命中，AI 未启用"

    snippet = text[:3000]
    prompt = f"""请从以下文档片段中提取字段「{rule.name}」的值。

字段说明：{rule.description or '无'}
要求格式：{rule.format or '不限'}

文档片段：
\"\"\"
{snippet}
\"\"\"

如果文档中没有这个字段，回答 "NOT_FOUND"。
如果有，只回答字段值本身，不要加任何解释。"""

    ok, resp = chat_completion_safe(ai_config, [{"role": "user", "content": prompt}], max_tokens=100)
    if not ok:
        return None, f"AI 提取失败：{resp[:50]}"

    value = resp.strip().strip('"').strip("'")
    if value.upper() == "NOT_FOUND" or not value:
        return None, "AI 判断字段不存在"
    return value, "AI 语义提取"


# ============================================================
# 4. AI 生成补位建议
# ============================================================

def generate_remedy_suggestion(rule_name: str, description: str, finding_type: str,
                                 doc_text: str = "",
                                 ai_config: Optional[AIConfig] = None) -> str:
    """AI 生成更具体的补位建议。

    finding_type: missing_field / missing_clause / forbidden_clause / format_invalid
    """
    if not ai_config or not ai_config.is_ready():
        return ""  # AI 不可用时返回空，使用规则库中的默认建议

    snippet = doc_text[:1500] if doc_text else "(未提供文档内容)"
    type_map = {
        "missing_field": "缺失必填字段",
        "missing_clause": "缺失必含条款",
        "forbidden_clause": "出现禁止条款",
        "format_invalid": "字段格式不合法",
    }
    type_label = type_map.get(finding_type, finding_type)

    prompt = f"""你是一个合同审查专家。文档中发现一个问题：{type_label}「{rule_name}」。

问题说明：{description}

文档相关片段：
\"\"\"
{snippet}
\"\"\"

请给出具体的修改建议，要求：
1. 直接说明应该怎么改
2. 如果是缺失条款，给出建议的条款内容模板（50字以内）
3. 如果是禁止条款，说明为什么有风险以及怎么改
4. 不要客套话，直接给建议（100字以内）"""

    ok, resp = chat_completion_safe(ai_config, [{"role": "user", "content": prompt}], max_tokens=300)
    if ok and resp:
        return resp.strip()
    return ""


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
    prompt = f"""你是一个合同审查专家。以下是一份文档的验真结果：

- 评分：{score}/100（等级 {grade}）
- 跨文件冲突：{conflict_count} 处
- 欠缺/违规：{gap_count} 项
- 主要问题：
{issues_text}

请用 3-5 句话给出总体评价和优先改进方向。要求：
1. 先一句话概括整体情况
2. 指出最需要优先修改的 1-2 个问题
3. 给出改进建议
4. 语气专业但不生硬，不要用"首先其次最后"这种模板化表达"""

    ok, resp = chat_completion_safe(ai_config, [{"role": "user", "content": prompt}], max_tokens=400)
    if ok and resp:
        return resp.strip()
    return ""
