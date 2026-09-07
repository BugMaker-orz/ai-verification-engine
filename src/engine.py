"""主引擎：编排文件解析 → 字段提取 → 冲突检测 → 欠缺检查 → 报告生成。"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from .conflict import detect_conflicts
from .extractor import extract_all
from .gap import check_all
from .parser import parse_files
from .report import VerificationResult, save_report
from .rules import RuleSet, load_ruleset


class VerificationEngine:
    """AI 验真引擎主类。

    用法：
        engine = VerificationEngine(ruleset_path="rules/general_contract.yaml")
        result = engine.verify(["doc_a.pdf", "doc_b.pdf"])
        engine.save_report(result, "output/")
    """

    def __init__(self, ruleset_path: str):
        if not os.path.isfile(ruleset_path):
            raise FileNotFoundError(f"规则集文件不存在: {ruleset_path}")
        self.ruleset: RuleSet = load_ruleset(ruleset_path)
        self.ruleset_path = ruleset_path

    def verify(self, file_paths: List[str]) -> VerificationResult:
        """对一组文件执行完整验真流程。"""
        # 1. 解析文件
        docs = parse_files(file_paths)
        # 2. 字段提取
        doc_fields = extract_all(docs, self.ruleset)
        # 3. 跨文件冲突检测
        conflicts = detect_conflicts(doc_fields, self.ruleset)
        # 4. 欠缺与违规检查
        gaps = check_all(docs, doc_fields, self.ruleset)
        # 5. 组装结果
        return VerificationResult(
            ruleset=self.ruleset,
            docs=docs,
            doc_fields=doc_fields,
            conflicts=conflicts,
            gaps=gaps,
        )

    def save_report(self, result: VerificationResult, output_dir: str,
                    basename: str = "verification_report") -> Dict[str, str]:
        """保存报告（Markdown + HTML）。"""
        return save_report(result, output_dir, basename)

    def print_summary(self, result: VerificationResult) -> None:
        """在终端打印验真摘要。"""
        print(f"\n{'='*60}")
        print(f"  AI 验真报告 — {self.ruleset.name} v{self.ruleset.version}")
        print(f"{'='*60}")
        print(f"  验真文档：{len(result.docs)} 份")
        print(f"  验真评分：{result.score}/100（等级 {result.grade}）")
        print(f"  问题总数：{result.total_findings}")
        print(f"    严重：{result.critical_count}  高：{result.high_count}  "
              f"中：{result.medium_count}  低：{result.low_count}")
        print(f"  跨文件冲突：{len(result.conflicts)}")
        print(f"  欠缺/违规：{len(result.gaps)}")
        print(f"{'='*60}\n")

        if result.conflicts:
            print("【跨文件冲突】")
            for c in result.conflicts:
                print(f"  [{c.severity.upper()}] {c.rule_name} — {c.field_name}")
                print(f"    {c.description}")
            print()

        if result.gaps:
            print("【欠缺与违规】")
            for g in result.gaps:
                loc = f"（第{g.source_line}行）" if g.source_line else ""
                print(f"  [{g.severity.upper()}] {g.rule_name}{loc}")
                print(f"    {g.description}")
                if g.suggestion:
                    print(f"    建议：{g.suggestion}")
            print()
