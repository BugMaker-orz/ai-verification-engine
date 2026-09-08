"""字段提取与对齐：基于规则库从每份文档中提取结构化字段，并做格式校验。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .parser import ParsedDoc
from .rules import FieldRule, RuleSet
from . import semantic
from .ai_client import AIConfig


@dataclass
class ExtractedField:
    """提取出的字段值。"""
    name: str
    value: Optional[str]
    found: bool
    format_valid: Optional[bool] = None    # None=无格式要求
    format_note: str = ""
    source_line: Optional[int] = None       # 所在行号（1-based）


@dataclass
class DocFields:
    """单份文档的全部提取字段。"""
    doc: ParsedDoc
    fields: Dict[str, ExtractedField] = field(default_factory=dict)

    def get(self, name: str) -> Optional[str]:
        ef = self.fields.get(name)
        return ef.value if ef and ef.found else None


# ---------- 格式校验 ----------

_DATE_PATTERNS = [
    re.compile(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?"),
    re.compile(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}"),
]
_CURRENCY_PATTERNS = [
    re.compile(r"[¥￥$€£]?\s?\d{1,3}(,\d{3})*(\.\d{2})?\s?(元|人民币|美元|欧元|英镑|RMB|CNY|USD|EUR|GBP)?"),
]
_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
_PHONE_RE = re.compile(r"^1[3-9]\d{9}$|^0\d{2,3}-?\d{7,8}$")
_ID_CARD_RE = re.compile(r"^\d{17}[\dXx]$")


def _check_format(value: str, fmt: str) -> tuple[bool, str]:
    if fmt == "date":
        ok = any(p.search(value) for p in _DATE_PATTERNS)
        return ok, "" if ok else "未识别为标准日期格式（YYYY-MM-DD / YYYY年MM月DD日）"
    if fmt == "currency":
        ok = any(p.search(value) for p in _CURRENCY_PATTERNS)
        return ok, "" if ok else "未识别为标准金额格式"
    if fmt == "email":
        return bool(_EMAIL_RE.match(value)), "" if _EMAIL_RE.match(value) else "邮箱格式不正确"
    if fmt == "phone":
        return bool(_PHONE_RE.match(value)), "" if _PHONE_RE.match(value) else "电话格式不正确"
    if fmt == "id_card":
        return bool(_ID_CARD_RE.match(value)), "" if _ID_CARD_RE.match(value) else "身份证号格式不正确"
    return True, ""


def _find_line_number(text: str, value: str) -> Optional[int]:
    """找到值第一次出现的行号。"""
    if not value:
        return None
    for i, line in enumerate(text.splitlines(), 1):
        if value in line:
            return i
    return None


def extract_fields(doc: ParsedDoc, ruleset: RuleSet,
                   ai_config: Optional[AIConfig] = None) -> DocFields:
    """从单份文档中按规则库提取全部字段。

    ai_config 就绪时，正则提取不到的字段用 AI 语义提取增强
    （每份文档批量合并为一次调用）。
    """
    result = DocFields(doc=doc)
    ai_ready = ai_config is not None and ai_config.is_ready()

    # 第一遍：全部字段先做正则提取
    missing_rules: List[FieldRule] = []
    missing_names: List[str] = []
    for name, rule in ruleset.fields.items():
        value = rule.extract(doc.text)
        extract_method = "正则提取"
        if value is None and ai_ready:
            # 记录待 AI 批量提取的字段
            missing_rules.append(rule)
            missing_names.append(name)
            extract_method = "正则未命中，待 AI 提取"
        found = value is not None
        format_valid = None
        format_note = ""
        if found and rule.format:
            format_valid, format_note = _check_format(value, rule.format)
        result.fields[name] = ExtractedField(
            name=name,
            value=value,
            found=found,
            format_valid=format_valid,
            format_note=format_note,
            source_line=_find_line_number(doc.text, value) if found else None,
        )

    # 第二遍：正则未命中的字段批量走 AI 提取（每份文档一次请求）
    if missing_rules and ai_ready:
        batch = semantic.extract_fields_semantic_batch(doc.text, missing_rules, ai_config)
        for name in missing_names:
            value, extract_method = batch.get(name, (None, "正则未命中，AI 未启用"))
            if value is None:
                # AI 也未提取到，保持未找到状态
                result.fields[name].value = None
                result.fields[name].found = False
                continue
            rule = next(r for r in missing_rules if r.name == name)
            format_valid, format_note = (None, "")
            if rule.format:
                format_valid, format_note = _check_format(value, rule.format)
            result.fields[name].value = value
            result.fields[name].found = True
            result.fields[name].format_valid = format_valid
            result.fields[name].format_note = format_note
            result.fields[name].source_line = _find_line_number(doc.text, value)

    return result


def extract_all(docs: List[ParsedDoc], ruleset: RuleSet,
                ai_config: Optional[AIConfig] = None) -> List[DocFields]:
    """批量提取。"""
    return [extract_fields(d, ruleset, ai_config) for d in docs]
