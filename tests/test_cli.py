#!/usr/bin/env python3
"""AI 验真引擎 — CLI 与 AI 降级测试。

运行：python tests/test_cli.py

覆盖：
- CLI 端到端：退出码、报告文件生成
- AIConfig 配置：加载/保存/就绪判断
- AI 降级：未配置 AI 时引擎自动使用基础规则模式
- AI 客户端：连接失败时安全降级，不抛异常
- 报告内容：Markdown 关键段落齐全
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ai_client import AIConfig, load_config, save_config, chat_completion_safe
from src.engine import VerificationEngine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_PATH = os.path.join(ROOT, "rules", "general_contract.yaml")
SAMPLES_DIR = os.path.join(ROOT, "samples")
CLI_PATH = os.path.join(ROOT, "cli.py")


def test_ai_config_ready():
    """AIConfig 就绪判断：四项齐全才 ready。"""
    assert not AIConfig().is_ready(), "空配置不应就绪"
    assert not AIConfig(base_url="https://x", api_key="k", model="m").is_ready(), \
        "enabled=False 不应就绪"
    cfg = AIConfig(base_url="https://x", api_key="k", model="m", enabled=True)
    assert cfg.is_ready(), "四项齐全应就绪"
    print("  ✓ AIConfig 就绪判断正常")


def test_ai_config_save_load_roundtrip():
    """AIConfig 保存/加载往返一致。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "ai_config.json")
        cfg = AIConfig(base_url="https://api.deepseek.com/v1",
                       api_key="sk-test-key",
                       model="deepseek-chat",
                       enabled=True, timeout=30, temperature=0.2)
        save_config(cfg, path)
        loaded = load_config(path)
        assert loaded.base_url == cfg.base_url
        assert loaded.api_key == cfg.api_key
        assert loaded.model == cfg.model
        assert loaded.enabled == cfg.enabled
        assert loaded.timeout == cfg.timeout
        assert loaded.temperature == cfg.temperature
        # 文件确实写入且不含多余字段
        raw = json.load(open(path, encoding="utf-8"))
        assert set(raw) == {"base_url", "api_key", "model", "enabled", "timeout", "temperature"}
    print("  ✓ AIConfig 保存/加载往返一致")


def test_ai_config_load_missing_file():
    """配置文件不存在时返回空配置，不报错。"""
    cfg = load_config("/nonexistent/ai_config.json")
    assert cfg == AIConfig(), "缺失文件应返回空配置"
    print("  ✓ 缺失配置文件安全降级")


def test_engine_ai_graceful_degrade():
    """未配置 AI 时引擎自动降级为基础规则模式。"""
    engine = VerificationEngine(ruleset_path=RULES_PATH)
    assert engine.ai_ready is False, "无 AI 配置时 ai_ready 应为 False"
    result = engine.verify([
        os.path.join(SAMPLES_DIR, "contract_main.txt"),
        os.path.join(SAMPLES_DIR, "contract_supplement.txt"),
    ])
    assert result.ai_enabled is False
    assert result.ai_model == ""
    assert result.ai_summary == ""
    assert len(result.conflicts) >= 2, "基础模式仍应检测到冲突"
    assert 0 <= result.score <= 100
    print(f"  ✓ 无 AI 自动降级（冲突{len(result.conflicts)}，评分{result.score}）")


def test_ai_client_safe_fallback():
    """AI 调用失败时安全降级为 (False, 错误信息)，不抛异常。"""
    # 配置不完整
    ok, msg = chat_completion_safe(AIConfig(), [{"role": "user", "content": "hi"}])
    assert ok is False and msg, "配置不完整应返回失败信息"
    # 配置完整但地址不可达
    cfg = AIConfig(base_url="http://127.0.0.1:1/v1", api_key="k",
                   model="m", enabled=True, timeout=2)
    ok, msg = chat_completion_safe(cfg, [{"role": "user", "content": "hi"}])
    assert ok is False and msg, "连接失败应返回 (False, 错误信息)"
    print("  ✓ AI 客户端失败安全降级")


def test_cli_end_to_end():
    """CLI 端到端：退出码 2（存在 high+ 问题）+ 报告文件生成。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        proc = subprocess.run(
            [sys.executable, CLI_PATH,
             "-r", RULES_PATH,
             "-f",
             os.path.join(SAMPLES_DIR, "contract_main.txt"),
             os.path.join(SAMPLES_DIR, "contract_supplement.txt"),
             "-o", tmpdir, "-n", "cli_test", "--quiet"],
            capture_output=True, text=True, timeout=120,
        )
        # 示例文件故意包含 high+ 问题，应返回退出码 2
        assert proc.returncode == 2, f"退出码应为 2，实际 {proc.returncode}"
        md = os.path.join(tmpdir, "cli_test.md")
        html = os.path.join(tmpdir, "cli_test.html")
        assert os.path.isfile(md), "Markdown 报告未生成"
        assert os.path.isfile(html), "HTML 报告未生成"
        content = open(md, encoding="utf-8").read()
        assert "AI 验真报告" in content
        assert "跨文件冲突" in content
        assert "欠缺与违规" in content
    print("  ✓ CLI 端到端正常（退出码 2，双格式报告生成）")


def test_cli_missing_file_exits_1():
    """CLI 文件不存在时报错退出 1。"""
    proc = subprocess.run(
        [sys.executable, CLI_PATH,
         "-r", RULES_PATH, "-f", "/nonexistent/doc.txt",
         "-o", tempfile.gettempdir(), "--quiet"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 1, f"退出码应为 1，实际 {proc.returncode}"
    assert "文件不存在" in proc.stderr
    print("  ✓ CLI 文件不存在退出码 1")


def test_report_contains_sources_and_suggestions():
    """报告应包含双源依据与补位建议。"""
    engine = VerificationEngine(ruleset_path=RULES_PATH)
    result = engine.verify([
        os.path.join(SAMPLES_DIR, "contract_main.txt"),
        os.path.join(SAMPLES_DIR, "contract_supplement.txt"),
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = engine.save_report(result, tmpdir, "check_src")
        md = open(paths["markdown"], encoding="utf-8").read()
        assert "双源依据" in md
        assert "补位建议" in md
        assert "contract_main.txt" in md
        assert "contract_supplement.txt" in md
    print("  ✓ 报告含双源依据与补位建议")


def main():
    print("=" * 60)
    print("  AI 验真引擎 — CLI 与 AI 降级测试")
    print("=" * 60)

    tests = [
        ("AIConfig 就绪判断", test_ai_config_ready),
        ("AIConfig 保存/加载往返", test_ai_config_save_load_roundtrip),
        ("缺失配置文件降级", test_ai_config_load_missing_file),
        ("引擎无 AI 自动降级", test_engine_ai_graceful_degrade),
        ("AI 客户端失败安全降级", test_ai_client_safe_fallback),
        ("CLI 端到端", test_cli_end_to_end),
        ("CLI 文件不存在退出1", test_cli_missing_file_exits_1),
        ("报告双源依据与建议", test_report_contains_sources_and_suggestions),
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
