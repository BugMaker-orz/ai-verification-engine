"""跨文件冲突检测：同字段值比对、语义近似冲突、引用完整性。

参考 Legal-Conflict-Resolver 的设计：
- 字段值精确比对（归一化后）
- 数值型字段的容差比对
- 冲突严重度分级
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .extractor import DocFields
from .rules import CrossDocRule, RuleSet
from . import semantic
from .ai_client import AIConfig


@dataclass
class ConflictFinding:
    """冲突发现项。"""
    rule_id: str
    rule_name: str
    field_name: str
    severity: str
    description: str
    sources: List[Tuple[str, str, Optional[int]]]   # (文件名, 字段值, 行号)
    conflict_type: str = "value_mismatch"           # value_mismatch / missing_in_one / reference_broken


def _normalize(value: str) -> str:
    """归一化：去空白、全角转半角、统一大小写。"""
    v = value.strip()
    v = v.replace("，", ",").replace("：", ":").replace("（", "(").replace("）", ")")
    v = re.sub(r"\s+", "", v)
    return v.lower()


def _extract_number(value: str) -> Optional[float]:
    """从字符串中提取数值（用于金额、数量等比对）。"""
    # 先匹配带千位逗号的数字（必须至少有一个逗号），再匹配普通数字
    m = re.search(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?", value)
    if m:
        return float(m.group(0).replace(",", ""))
    return None


def _values_conflict(v1: str, v2: str, field_name: str) -> Tuple[bool, str]:
    """判断两个字段值是否冲突，返回 (是否冲突, 描述)。"""
    n1, n2 = _normalize(v1), _normalize(v2)
    if n1 == n2:
        return False, ""

    # 数值型字段：提取数值比对（允许单位差异但数值一致）
    num_fields = {"合同金额", "金额", "总价", "数量", "期限", "天数", "比例", "百分比"}
    if any(k in field_name for k in num_fields):
        a, b = _extract_number(v1), _extract_number(v2)
        if a is not None and b is not None:
            if abs(a - b) < 1e-6:
                return False, ""
            return True, f"数值不一致：{v1} vs {v2}（差值 {abs(a-b):g}）"

    # 日期型字段
    if "日期" in field_name or "时间" in field_name:
        d1 = re.search(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}", v1)
        d2 = re.search(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}", v2)
        if d1 and d2:
            # 归一化日期：年月/ → -，去前导零，去末尾日字
            def norm_date(s: str) -> str:
                s = re.sub(r"[年月]", "-", s).replace("/", "-").rstrip("日-")
                # 去除月、日的前导零以便比较
                parts = s.split("-")
                return "-".join(p.lstrip("0") or "0" for p in parts)
            if norm_date(d1.group(0)) == norm_date(d2.group(0)):
                return False, ""
            return True, f"日期不一致：{v1} vs {v2}"

    return True, f"文本不一致：'{v1}' vs '{v2}'"


def detect_conflicts(doc_fields_list: List[DocFields], ruleset: RuleSet,
                     ai_config: Optional[AIConfig] = None) -> List[ConflictFinding]:
    """对所有跨文档规则执行冲突检测。

    ai_config 就绪时，对基础检测到的冲突做 AI 语义二次确认，
    排除"表述不同但意思相同"的误报。
    """
    findings: List[ConflictFinding] = []
    ai_ready = ai_config is not None and ai_config.is_ready()
    if len(doc_fields_list) < 2:
        return findings

    for rule in ruleset.cross_doc_rules:
        for field_name in rule.fields:
            # 收集所有文档中该字段的值
            present: List[Tuple[DocFields, str]] = []
            missing_docs: List[str] = []
            for df in doc_fields_list:
                val = df.get(field_name)
                if val:
                    present.append((df, val))
                else:
                    missing_docs.append(df.doc.filename)

            # 某文档缺失该字段
            if missing_docs and present:
                findings.append(ConflictFinding(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    field_name=field_name,
                    severity=rule.severity,
                    description=f"字段「{field_name}」在 {len(missing_docs)} 份文档中缺失：{', '.join(missing_docs)}",
                    sources=[(df.doc.filename, v, df.fields[field_name].source_line) for df, v in present]
                             + [(d, "(缺失)", None) for d in missing_docs],
                    conflict_type="missing_in_one",
                ))
                continue

            if len(present) < 2:
                continue

            # 两两比对
            base_val = present[0][1]
            conflicts = []
            pending_pairs: List[Tuple[str, str, str]] = []   # (字段名, 基准值, 对比值)
            pending_meta: List[Tuple[DocFields, str, str, str]] = []  # (df, val, base_val, desc)
            for df, val in present[1:]:
                is_conflict, desc = _values_conflict(base_val, val, field_name)
                if is_conflict:
                    if ai_ready:
                        # 收集待 AI 批量语义确认
                        pending_pairs.append((field_name, base_val, val))
                        pending_meta.append((df, val, base_val, desc))
                    else:
                        conflicts.append((df, val, desc))

            # AI 批量语义二次确认：一次请求排除"表述不同但意思相同"的误报
            if ai_ready and pending_pairs:
                ai_results = semantic.semantic_conflict_check_batch(pending_pairs, ai_config)
                for (df, val, base_val, desc), (ai_conflict, ai_reason) in zip(pending_meta, ai_results):
                    if not ai_conflict:
                        continue
                    conflicts.append((df, val, f"{desc}（AI 确认：{ai_reason}）"))

            if conflicts:
                findings.append(ConflictFinding(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    field_name=field_name,
                    severity=rule.severity,
                    description=f"字段「{field_name}」跨文档不一致：基准值「{base_val}」，{len(conflicts)} 处冲突",
                    sources=[(present[0][0].doc.filename, base_val, present[0][0].fields[field_name].source_line)]
                             + [(df.doc.filename, v, df.fields[field_name].source_line) for df, v, _ in conflicts],
                    conflict_type="value_mismatch",
                ))

    return findings
