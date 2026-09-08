"""欠缺检查：基于规则库查找文件中缺失的必填字段、必含条款，以及禁止条款。

参考 ContractGuard 的四分类：
- 缺失保护（必填字段/必含条款缺失）
- 红旗条款（禁止条款出现）
- 格式问题（字段格式不合法）

支持 AI 语义增强：AI 可用时用语义匹配替代纯关键词匹配，
并生成更具体的补位建议。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .ai_client import AIConfig
from .extractor import DocFields
from .parser import ParsedDoc
from .rules import ClauseRule, RuleSet
from . import semantic


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
    match_method: str = ""    # 匹配方式：关键词/正则/AI语义


def check_gaps(doc: ParsedDoc, doc_fields: DocFields, ruleset: RuleSet,
               ai_config: Optional[AIConfig] = None) -> List[GapFinding]:
    """对单份文档执行欠缺检查。

    ai_config 为 None 或未就绪时，使用基础关键词/正则匹配；
    ai_config 就绪时，使用 AI 语义匹配和 AI 补位建议。
    """
    findings: List[GapFinding] = []
    ai_ready = ai_config is not None and ai_config.is_ready()

    # 1. 必填字段缺失
    for name, rule in ruleset.fields.items():
        ef = doc_fields.fields.get(name)
        if rule.required and (ef is None or not ef.found):
            # AI 增强补位建议
            ai_suggestion = ""
            if ai_ready:
                ai_suggestion = semantic.generate_remedy_suggestion(
                    rule_name=name, description=rule.description or "必填字段",
                    finding_type="missing_field", doc_text=doc.text, ai_config=ai_config
                )
            findings.append(GapFinding(
                rule_id=f"FIELD-MISSING-{name}",
                rule_name=f"必填字段缺失：{name}",
                kind="missing_field",
                severity="high",
                description=f"文档中未找到必填字段「{name}」",
                field_name=name,
                suggestion=ai_suggestion or f"请在文档中补充「{name}」字段，建议格式：{rule.format or '文本'}",
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

    # 3. 必含条款缺失（语义匹配）
    for clause in ruleset.required_clauses:
        matched, method = semantic.clause_match(doc.text, clause, ai_config)
        if not matched:
            ai_suggestion = ""
            if ai_ready:
                ai_suggestion = semantic.generate_remedy_suggestion(
                    rule_name=clause.name, description=clause.description,
                    finding_type="missing_clause", doc_text=doc.text, ai_config=ai_config
                )
            findings.append(GapFinding(
                rule_id=clause.id,
                rule_name=f"必含条款缺失：{clause.name}",
                kind="missing_clause",
                severity=clause.severity,
                description=f"文档中未找到必含条款「{clause.name}」（匹配方式：{method}）",
                suggestion=ai_suggestion or f"建议补充「{clause.name}」相关条款，{clause.description}",
                match_method=method,
            ))

    # 4. 禁止条款出现（语义匹配）
    for clause in ruleset.forbidden_clauses:
        matched, method = semantic.clause_match(doc.text, clause, ai_config)
        if matched:
            # 定位行号（用基础匹配定位）
            line_no = None
            for i, line in enumerate(doc.lines(), 1):
                if clause.match(line):
                    line_no = i
                    break
            ai_suggestion = ""
            if ai_ready:
                ai_suggestion = semantic.generate_remedy_suggestion(
                    rule_name=clause.name, description=clause.description,
                    finding_type="forbidden_clause", doc_text=doc.text, ai_config=ai_config
                )
            findings.append(GapFinding(
                rule_id=clause.id,
                rule_name=f"禁止条款出现：{clause.name}",
                kind="forbidden_clause",
                severity=clause.severity,
                description=f"文档中出现禁止条款「{clause.name}」（匹配方式：{method}，第{line_no or '?'}行）",
                source_line=line_no,
                suggestion=ai_suggestion or f"建议删除或修改「{clause.name}」相关内容，{clause.description}",
                match_method=method,
            ))

    return findings


def check_all(docs: List[ParsedDoc], doc_fields_list: List[DocFields], ruleset: RuleSet,
               ai_config: Optional[AIConfig] = None) -> List[GapFinding]:
    """批量检查。"""
    all_findings: List[GapFinding] = []
    for doc, df in zip(docs, doc_fields_list):
        all_findings.extend(check_gaps(doc, df, ruleset, ai_config))
    return all_findings
