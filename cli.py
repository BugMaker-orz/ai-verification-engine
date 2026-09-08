#!/usr/bin/env python3
"""AI 验真引擎 — 命令行入口。

基础模式用法：
  python cli.py -r rules/general_contract.yaml -f doc1.pdf doc2.txt -o output/

AI 增强模式用法（命令行指定）：
  python cli.py -r rules/general_contract.yaml -f doc1.pdf doc2.txt \
    --ai-base-url https://api.deepseek.com/v1 \
    --ai-key sk-xxx \
    --ai-model deepseek-chat

AI 增强模式用法（从配置文件加载）：
  python cli.py -r rules/general_contract.yaml -f doc1.pdf doc2.txt --ai-config config/ai_config.json
"""
from __future__ import annotations

import argparse
import os
import sys

# 确保 src 可导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ai_client import AIConfig, load_config
from src.engine import VerificationEngine


def main():
    ap = argparse.ArgumentParser(
        description="AI 验真引擎：多文件字段对齐、跨文件冲突定位、规则驱动欠缺检查"
    )
    ap.add_argument("-r", "--rules", required=True, help="规则集 YAML 文件路径")
    ap.add_argument("-f", "--files", required=True, nargs="+", help="待验真的文件列表（PDF/TXT/DOCX）")
    ap.add_argument("-o", "--output", default="output", help="报告输出目录（默认 output/）")
    ap.add_argument("-n", "--name", default="verification_report", help="报告文件名前缀")
    ap.add_argument("--quiet", action="store_true", help="不打印终端摘要")

    # AI 配置参数
    ap.add_argument("--ai-config", default="", help="AI 配置文件路径（JSON），默认不加载")
    ap.add_argument("--ai-base-url", default="", help="AI API 地址（如 https://api.deepseek.com/v1）")
    ap.add_argument("--ai-key", default="", help="AI API Key")
    ap.add_argument("--ai-model", default="", help="AI 模型名（如 deepseek-chat / gpt-4o-mini）")
    ap.add_argument("--ai-enabled", action="store_true", help="显式启用 AI（覆盖配置文件中的 enabled=false）")

    args = ap.parse_args()

    # 检查文件存在
    for f in args.files:
        if not os.path.isfile(f):
            print(f"错误：文件不存在 — {f}", file=sys.stderr)
            sys.exit(1)

    # 构建 AI 配置
    ai_config = None
    # 优先从配置文件加载
    if args.ai_config:
        ai_config = load_config(args.ai_config)
    # 命令行参数覆盖配置文件
    if args.ai_base_url or args.ai_key or args.ai_model:
        if ai_config is None:
            ai_config = AIConfig()
        if args.ai_base_url:
            ai_config.base_url = args.ai_base_url
        if args.ai_key:
            ai_config.api_key = args.ai_key
        if args.ai_model:
            ai_config.model = args.ai_model
        ai_config.enabled = True
    # 显式启用
    if args.ai_enabled and ai_config is not None:
        ai_config.enabled = True

    # 初始化引擎
    try:
        engine = VerificationEngine(ruleset_path=args.rules, ai_config=ai_config)
    except Exception as e:
        print(f"错误：加载规则集失败 — {e}", file=sys.stderr)
        sys.exit(1)

    mode = f"AI 增强（{ai_config.model}）" if engine.ai_ready else "基础规则匹配"
    print(f"正在验真 {len(args.files)} 份文档（规则集：{engine.ruleset.name} v{engine.ruleset.version}，模式：{mode}）...")
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
