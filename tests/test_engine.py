#!/usr/bin/env python3
"""AI 验真引擎 — 测试用例。

运行：python tests/test_engine.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine import VerificationEngine
from src.parser import parse_file
from src.rules import load_ruleset
from src.extractor import extract_fields
from src.conflict import detect_conflicts, _values_conflict, _normalize
from src.gap import check_gaps


RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "rules", "general_contract.yaml")
SAMPLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")


def test_ruleset_load():
    """测试规则集加载。"""
    rs = load_ruleset(RULES_PATH)
    assert rs.name == "通用合同与文档验真规则"
    assert len(rs.fields) >= 10, f"字段规则应>=10，实际{len(rs.fields)}"
    assert len(rs.required_clauses) >= 5
    assert len(rs.forbidden_clauses) >= 2
    assert len(rs.cross_doc_rules) >= 5
    print("  ✓ 规则集加载正常（字段%d / 必含条款%d / 禁止条款%d / 跨文档规则%d）"
          % (len(rs.fields), len(rs.required_clauses), len(rs.forbidden_clauses), len(rs.cross_doc_rules)))


def test_parser():
    """测试文件解析。"""
    doc = parse_file(os.path.join(SAMPLES_DIR, "contract_main.txt"))
    assert doc.file_type == "txt"
    assert doc.line_count > 20
    assert "青岛海星科技有限公司" in doc.text
    print("  ✓ 文件解析正常（%d行，含甲方名称）" % doc.line_count)


def test_field_extraction():
    """测试字段提取。"""
    rs = load_ruleset(RULES_PATH)
    doc = parse_file(os.path.join(SAMPLES_DIR, "contract_main.txt"))
    df = extract_fields(doc, rs)
    assert df.get("甲方/委托方") == "青岛海星科技有限公司"
    assert df.get("乙方/受托方") == "济南蓝海软件有限公司"
    assert df.get("签订日期") == "2026年3月15日"
    assert "280,000" in df.get("合同金额")
    print("  ✓ 字段提取正常（甲方/乙方/日期/金额均提取成功）")


def test_conflict_detection():
    """测试跨文件冲突检测。"""
    rs = load_ruleset(RULES_PATH)
    doc1 = parse_file(os.path.join(SAMPLES_DIR, "contract_main.txt"))
    doc2 = parse_file(os.path.join(SAMPLES_DIR, "contract_supplement.txt"))
    from src.extractor import extract_all
    dfs = extract_all([doc1, doc2], rs)
    conflicts = detect_conflicts(dfs, rs)

    # 应检测到：甲方名称不一致（有限公司 vs 有限责任公司）、金额不一致、期限不一致
    conflict_fields = {c.field_name for c in conflicts}
    assert "甲方/委托方" in conflict_fields, "应检测到甲方名称不一致"
    assert "合同金额" in conflict_fields, "应检测到合同金额不一致"
    print("  ✓ 冲突检测正常（检测到%d处冲突：%s）"
          % (len(conflicts), ", ".join(sorted(conflict_fields))))


def test_values_conflict_logic():
    """测试值冲突判断逻辑。"""
    # 相同文本（归一化后）
    assert not _values_conflict("280,000元", "280000元", "合同金额")[0]
    # 不同数值
    assert _values_conflict("280,000元", "320,000元", "合同金额")[0]
    # 相同日期不同格式
    assert not _values_conflict("2026年3月15日", "2026-03-15", "签订日期")[0]
    # 不同文本
    assert _values_conflict("青岛海星科技有限公司", "青岛海星科技有限责任公司", "甲方")[0]
    print("  ✓ 值冲突逻辑正常（数值/日期/文本均正确判断）")


def test_gap_check():
    """测试欠缺检查。"""
    rs = load_ruleset(RULES_PATH)
    # 补充协议缺少：违约责任、争议解决、保密、不可抗力、知识产权、合同解除条款
    doc = parse_file(os.path.join(SAMPLES_DIR, "contract_supplement.txt"))
    from src.extractor import extract_fields
    df = extract_fields(doc, rs)
    gaps = check_gaps(doc, df, rs)

    gap_names = {g.rule_name for g in gaps}
    # 必含条款缺失
    assert any("违约责任" in n for n in gap_names), "应检测到违约责任条款缺失"
    assert any("争议解决" in n for n in gap_names), "应检测到争议解决条款缺失"
    # 禁止条款（空白占位符）
    assert any("空白占位符" in n for n in gap_names), "应检测到空白占位符"
    print("  ✓ 欠缺检查正常（检测到%d项欠缺/违规）" % len(gaps))


def test_full_engine():
    """测试完整引擎端到端。"""
    engine = VerificationEngine(ruleset_path=RULES_PATH)
    result = engine.verify([
        os.path.join(SAMPLES_DIR, "contract_main.txt"),
        os.path.join(SAMPLES_DIR, "contract_supplement.txt"),
    ])

    assert result.total_findings > 0
    assert len(result.conflicts) >= 2
    assert len(result.gaps) >= 3
    assert 0 <= result.score <= 100
    assert result.grade in "ABCDEF"

    # 测试报告生成
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = engine.save_report(result, tmpdir, "test_report")
        assert os.path.isfile(paths["markdown"])
        assert os.path.isfile(paths["html"])
        md_content = open(paths["markdown"], encoding="utf-8").read()
        assert "AI 验真报告" in md_content
        assert "跨文件冲突" in md_content

    print("  ✓ 完整引擎端到端正常（评分%d/%s，冲突%d，欠缺%d，报告生成成功）"
          % (result.score, result.grade, len(result.conflicts), len(result.gaps)))


def main():
    print("=" * 60)
    print("  AI 验真引擎 — 测试用例")
    print("=" * 60)

    tests = [
        ("规则集加载", test_ruleset_load),
        ("文件解析", test_parser),
        ("字段提取", test_field_extraction),
        ("值冲突逻辑", test_values_conflict_logic),
        ("跨文件冲突检测", test_conflict_detection),
        ("欠缺检查", test_gap_check),
        ("完整引擎端到端", test_full_engine),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"\n[{name}]")
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ 断言失败：{e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ 异常：{type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"  测试结果：{passed} 通过，{failed} 失败（共{len(tests)}项）")
    print(f"{'='*60}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
