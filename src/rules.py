"""规则引擎：加载 YAML 规则库，提供字段/条款/跨文档规则的结构化访问。

规则库设计参考网上相似项目：
- contract-lint: 确定性规则 + 稳定 rule_id + 严重度 + 行号
- Legal-Conflict-Resolver: 冲突概率阈值 + 条款类型严重度分级
- Vaulytica: 确定性规则 + 跨文档检查 + 披露前检查
- ContractGuard: 红旗/警告/保护/缺失四分类
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml


SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


@dataclass
class FieldRule:
    """字段级规则：必填、正则提取、格式校验。"""
    name: str
    required: bool = False
    patterns: List[str] = field(default_factory=list)   # 正则列表，任一匹配即提取
    format: Optional[str] = None       # date / currency / email / phone / id_card
    description: str = ""

    def extract(self, text: str) -> Optional[str]:
        """从文本中按正则提取字段值。"""
        for pat in self.patterns:
            m = re.search(pat, text)
            if m:
                # 优先取第一个非空捕获组，否则取整个匹配
                if m.groups():
                    for g in m.groups():
                        if g and g.strip():
                            return g.strip()
                val = m.group(0).strip()
                return val if val else None
        return None


@dataclass
class ClauseRule:
    """条款规则：必含 / 禁止，关键词或正则匹配。"""
    id: str
    name: str
    kind: str                  # required / forbidden
    keywords: List[str] = field(default_factory=list)
    patterns: List[str] = field(default_factory=list)
    severity: str = "medium"
    description: str = ""

    def match(self, text: str) -> bool:
        for kw in self.keywords:
            if kw in text:
                return True
        for pat in self.patterns:
            if re.search(pat, text):
                return True
        return False


@dataclass
class CrossDocRule:
    """跨文档规则：同字段在多文件间的一致性检查。"""
    id: str
    name: str
    fields: List[str]          # 要比对的字段名列表
    severity: str = "high"
    description: str = ""
    normalize: bool = True     # 是否归一化后比对（去空格、统一大小写）


@dataclass
class RuleSet:
    """完整规则集。"""
    name: str
    version: str
    description: str
    fields: Dict[str, FieldRule] = field(default_factory=dict)
    required_clauses: List[ClauseRule] = field(default_factory=list)
    forbidden_clauses: List[ClauseRule] = field(default_factory=list)
    cross_doc_rules: List[CrossDocRule] = field(default_factory=list)

    @property
    def all_clauses(self) -> List[ClauseRule]:
        return self.required_clauses + self.forbidden_clauses


def _build_field(d: dict) -> FieldRule:
    return FieldRule(
        name=d["name"],
        required=d.get("required", False),
        patterns=d.get("patterns", []),
        format=d.get("format"),
        description=d.get("description", ""),
    )


def _build_clause(d: dict, kind: str) -> ClauseRule:
    return ClauseRule(
        id=d["id"],
        name=d["name"],
        kind=kind,
        keywords=d.get("keywords", []),
        patterns=d.get("patterns", []),
        severity=d.get("severity", "medium"),
        description=d.get("description", ""),
    )


def load_ruleset(path: str) -> RuleSet:
    """从 YAML 文件加载规则集。"""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    fields = {d["name"]: _build_field(d) for d in data.get("fields", [])}
    required = [_build_clause(d, "required") for d in data.get("clauses", {}).get("required", [])]
    forbidden = [_build_clause(d, "forbidden") for d in data.get("clauses", {}).get("forbidden", [])]
    cross = [
        CrossDocRule(
            id=d["id"],
            name=d["name"],
            fields=d.get("fields", []),
            severity=d.get("severity", "high"),
            description=d.get("description", ""),
            normalize=d.get("normalize", True),
        )
        for d in data.get("cross_document", [])
    ]

    return RuleSet(
        name=data.get("name", "未命名规则集"),
        version=data.get("version", "1.0"),
        description=data.get("description", ""),
        fields=fields,
        required_clauses=required,
        forbidden_clauses=forbidden,
        cross_doc_rules=cross,
    )


def list_available_rules(rules_dir: str) -> List[str]:
    """列出规则目录下所有可用规则集。"""
    if not os.path.isdir(rules_dir):
        return []
    return sorted(f for f in os.listdir(rules_dir) if f.endswith((".yaml", ".yml")))
