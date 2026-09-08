"""主引擎：编排文件解析 → 字段提取 → 冲突检测 → 欠缺检查 → 报告生成。

支持 AI 语义增强：传入 ai_config 时自动启用 AI 语义匹配、
冲突误报排除、AI 补位建议和 AI 总体摘要。
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from .ai_client import AIConfig
from .conflict import detect_conflicts
from .extractor import extract_all
from .gap import check_all
from .parser import parse_files
from .report import VerificationResult, save_report
from .rules import RuleSet, load_ruleset
from . import semantic


class VerificationEngine:
    """AI 验真引擎主类。

    用法（基础模式）：
        engine = VerificationEngine(ruleset_path="rules/general_contract.yaml")
        result = engine.verify(["doc_a.pdf", "doc_b.pdf"])

    用法（AI 增强模式）：
        from src.ai_client import AIConfig
        ai_cfg = AIConfig(base_url="https://api.deepseek.com/v1",
                          api_key="sk-xxx", model="deepseek-chat", enabled=True)
        engine = VerificationEngine(ruleset_path="rules/general_contract.yaml", ai_config=ai_cfg)
        result = engine.verify(["doc_a.pdf", "doc_b.pdf"])
    """

    def __init__(self, ruleset_path: str, ai_config: Optional[AIConfig] = None):
        if not os.path.isfile(ruleset_path):
            raise FileNotFoundError(f"规则集文件不存在: {ruleset_path}")
        self.ruleset: RuleSet = load_ruleset(ruleset_path)
        self.ruleset_path = ruleset_path
        self.ai_config: Optional[AIConfig] = ai_config
        self.ai_ready = ai_config is not None and ai_config.is_ready()

    def verify(self, file_paths: List[str]) -> VerificationResult:
        """对一组文件执行完整验真流程。"""
        # 1. 解析文件
        docs = parse_files(file_paths)
        # 2. 字段提取（AI 增强：正则提取不到时用 AI 提取）
        doc_fields = extract_all(docs, self.ruleset, self.ai_config)
        # 3. 跨文件冲突检测（AI 增强：语义二次确认排除误报）
        conflicts = detect_conflicts(doc_fields, self.ruleset, self.ai_config)
        # 4. 欠缺与违规检查（AI 增强：语义匹配 + AI 补位建议）
        gaps = check_all(docs, doc_fields, self.ruleset, self.ai_config)

        # 5. 组装结果
        result = VerificationResult(
            ruleset=self.ruleset,
            docs=docs,
            doc_fields=doc_fields,
            conflicts=conflicts,
            gaps=gaps,
            ai_enabled=self.ai_ready,
            ai_model=self.ai_config.model if self.ai_ready else "",
        )

        # 6. AI 生成总体摘要（仅 AI 模式）
        if self.ai_ready:
            top_issues = [f.rule_name for f in conflicts[:3]] + [g.rule_name for g in gaps[:3]]
            result.ai_summary = semantic.generate_summary(
                score=result.score,
                grade=result.grade,
                conflict_count=len(conflicts),
                gap_count=len(gaps),
                top_issues=top_issues,
                ai_config=self.ai_config,
            )

        return result

    def save_report(self, result: VerificationResult, output_dir: str,
                    basename: str = "verification_report") -> Dict[str, str]:
        """保存报告（Markdown + HTML）。"""
        return save_report(result, output_dir, basename)

    def print_summary(self, result: VerificationResult) -> None:
        """在终端打印验真摘要。"""
        mode = f"AI 增强（{result.ai_model}）" if result.ai_enabled else "基础规则匹配"
        print(f"\n{'='*60}")
        print(f"  AI 验真报告 — {self.ruleset.name} v{self.ruleset.version}")
        print(f"  检查模式：{mode}")
        print(f"{'='*60}")
        print(f"  验真文档：{len(result.docs)} 份")
        print(f"  验真评分：{result.score}/100（等级 {result.grade}）")
        print(f"  问题总数：{result.total_findings}")
        print(f"    严重：{result.critical_count}  高：{result.high_count}  "
              f"中：{result.medium_count}  低：{result.low_count}")
        print(f"  跨文件冲突：{len(result.conflicts)}")
        print(f"  欠缺/违规：{len(result.gaps)}")
        print(f"{'='*60}\n")

        if result.ai_summary:
            print("【🤖 AI 总体评价】")
            print(f"  {result.ai_summary}")
            print()

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
