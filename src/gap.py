"""欠缺检查：基于规则库查找文件中缺失的必填字段、必含条款，以及禁止条款。

参考 ContractGuard 的四分类：
- 缺失保护（必填字段/必含条款缺失）
- 红旗条款（禁止条款出现）
- 格式问题（字段格式不合法）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .extractor import DocFields
from .parser import ParsedDoc
from .rules import ClauseRule, RuleSet


@dataclass
class GapFinding:
    """欠缺/违规发现项。"""
    rule_id: str
    rule_name: str
    kind: str                 # missing_field / missing_clause / forbidden_clause / format_invalid
    severity: str
    description: str
    field_name: Optional[str] = None
    source_line: Optional[int] = None
    suggestion: str = ""      # 补位建议


def check_gaps(doc: ParsedDoc, doc_fields: DocFields, ruleset: RuleSet) -> List[GapFinding]:
    """对单份文档执行欠缺检查。"""
    findings: List[GapFinding] = []

    # 1. 必填字段缺失
    for name, rule in ruleset.fields.items():
        ef = doc_fields.fields.get(name)
        if rule.required and (ef is None or not ef.found):
            findings.append(GapFinding(
                rule_id=f"FIELD-MISSING-{name}",
                rule_name=f"必填字段缺失：{name}",
                kind="missing_field",
                severity="high",
                description=f"文档中未找到必填字段「{name}」",
                field_name=name,
                suggestion=f"请在文档中补充「{name}」字段，建议格式：{rule.format or '文本'}",
            ))
        # 2. 字段格式不合法
        elif ef and ef.found and ef.format_valid is False:
            findings.append(GapFinding(
                rule_id=f"FIELD-FORMAT-{name}",
                rule_name=f"字段格式不合法：{name}",
                kind="format_invalid",
                severity="medium",
                description=f"字段「{name}」值「{ef.value}」格式不合法：{ef.format_note}",
                field_name=name,
                source_line=ef.source_line,
                suggestion=f"请将「{name}」修正为标准{rule.format}格式",
            ))

    # 3. 必含条款缺失
    for clause in ruleset.required_clauses:
        if not clause.match(doc.text):
            findings.append(GapFinding(
                rule_id=clause.id,
                rule_name=f"必含条款缺失：{clause.name}",
                kind="missing_clause",
                severity=clause.severity,
                description=f"文档中未找到必含条款「{clause.name}」（关键词：{', '.join(clause.keywords)}）",
                suggestion=f"建议补充「{clause.name}」相关条款，{clause.description}",
            ))

    # 4. 禁止条款出现
    for clause in ruleset.forbidden_clauses:
        if clause.match(doc.text):
            # 定位行号
            line_no = None
            for i, line in enumerate(doc.lines(), 1):
                if clause.match(line):
                    line_no = i
                    break
            findings.append(GapFinding(
                rule_id=clause.id,
                rule_name=f"禁止条款出现：{clause.name}",
                kind="forbidden_clause",
                severity=clause.severity,
                description=f"文档中出现禁止条款「{clause.name}」（第{line_no}行）",
                source_line=line_no,
                suggestion=f"建议删除或修改「{clause.name}」相关内容，{clause.description}",
            ))

    return findings


def check_all(docs: List[ParsedDoc], doc_fields_list: List[DocFields], ruleset: RuleSet) -> List[GapFinding]:
    """批量检查。"""
    all_findings: List[GapFinding] = []
    for doc, df in zip(docs, doc_fields_list):
        all_findings.extend(check_gaps(doc, df, ruleset))
    return all_findings
