#!/usr/bin/env python3
"""AI 验真引擎 — 命令行入口。

用法：
  python cli.py --rules rules/general_contract.yaml --files doc1.pdf doc2.txt --output output/
  python cli.py -r rules/general_contract.yaml -f samples/contract_main.txt samples/contract_supplement.txt -o output/
"""
from __future__ import annotations

import argparse
import os
import sys

# 确保 src 可导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.engine import VerificationEngine


def main():
    ap = argparse.ArgumentParser(description="AI 验真引擎：多文件字段对齐、跨文件冲突定位、规则驱动欠缺检查")
    ap.add_argument("-r", "--rules", required=True, help="规则集 YAML 文件路径")
    ap.add_argument("-f", "--files", required=True, nargs="+", help="待验真的文件列表（PDF/TXT/DOCX）")
    ap.add_argument("-o", "--output", default="output", help="报告输出目录（默认 output/）")
    ap.add_argument("-n", "--name", default="verification_report", help="报告文件名前缀")
    ap.add_argument("--quiet", action="store_true", help="不打印终端摘要")
    args = ap.parse_args()

    # 检查文件存在
    for f in args.files:
        if not os.path.isfile(f):
            print(f"错误：文件不存在 — {f}", file=sys.stderr)
            sys.exit(1)

    # 初始化引擎
    try:
        engine = VerificationEngine(ruleset_path=args.rules)
    except Exception as e:
        print(f"错误：加载规则集失败 — {e}", file=sys.stderr)
        sys.exit(1)

    # 执行验真
    print(f"正在验真 {len(args.files)} 份文档（规则集：{engine.ruleset.name} v{engine.ruleset.version}）...")
    result = engine.verify(args.files)

    # 打印摘要
    if not args.quiet:
        engine.print_summary(result)

    # 保存报告
    paths = engine.save_report(result, args.output, args.name)
    print(f"报告已生成：")
    print(f"  Markdown：{paths['markdown']}")
    print(f"  HTML：    {paths['html']}")

    # 有 high 及以上问题时返回非零退出码
    if result.critical_count + result.high_count > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()
