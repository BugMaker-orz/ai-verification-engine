"""AI 语义链路回归测试 — 覆盖 AI 启用路径，防止 NameError 类缺陷回归。"""
import pytest

from src.ai_client import AIConfig
from src import semantic


def _fake_ai_config() -> AIConfig:
    cfg = AIConfig()
    cfg.enabled = True
    cfg.api_key = "sk-test"
    cfg.base_url = "https://example.com/v1"
    cfg.model = "test-model"
    assert cfg.is_ready()
    return cfg


def test_generate_remedy_suggestion_with_ai(monkeypatch):
    """AI 启用时生成补位建议，不得抛 NameError（回归：rule 未定义）。"""
    def _fake_chat(config, messages, max_tokens=100, timeout=30):
        return True, "建议补充：明确合同金额、付款节点与违约责任条款。"

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    result = semantic.generate_remedy_suggestion(
        rule_name="合同金额",
        description="未找到合同金额字段",
        finding_type="missing_field",
        doc_text="本合同由甲乙双方签订……",
        ai_config=cfg,
    )
    assert "建议补充" in result


def test_generate_remedy_suggestion_no_ai():
    """AI 未启用时返回空字符串，走默认建议。"""
    result = semantic.generate_remedy_suggestion(
        rule_name="合同金额", description="x", finding_type="missing_field"
    )
    assert result == ""


def test_extract_field_semantic_ai_fallback(monkeypatch):
    """正则未命中 + AI 可用时走 AI 提取。"""
    def _fake_chat(config, messages, max_tokens=100, timeout=30):
        return True, "500,000"

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    value, method = semantic.extract_field_semantic(
        "本文档没有金额相关字样。", _field_rule(), cfg
    )
    assert value == "500,000"
    assert method == "AI 语义提取"


def test_clause_match_ai_positive(monkeypatch):
    """AI 语义命中条款。"""
    def _fake_chat(config, messages, max_tokens=200, timeout=30):
        return True, '{"matched": true, "reason": "表述虽不同但含义一致"}'

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    matched, reason = semantic.clause_match(
        "双方约定按季度结算款项。", _clause_rule(), cfg
    )
    assert matched is True
    assert "AI 语义命中" in reason


def test_semantic_conflict_check_no_conflict(monkeypatch):
    """AI 判定两值实质相同，不算冲突。"""
    def _fake_chat(config, messages, max_tokens=200, timeout=30):
        return True, '{"conflict": false, "reason": "28万元与280,000元是同一金额"}'

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    conflict, reason = semantic.semantic_conflict_check("28万元", "280,000元", "合同金额", cfg)
    assert conflict is False


def test_semantic_conflict_check_ai_failure(monkeypatch):
    """AI 调用失败时保守判定为冲突。"""
    def _fake_chat(config, messages, max_tokens=200, timeout=30):
        return False, "network error"

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    conflict, reason = semantic.semantic_conflict_check("A", "B", "字段", cfg)
    assert conflict is True
    assert "保守判定" in reason


def test_generate_summary_with_ai(monkeypatch):
    """AI 生成总体摘要。"""
    def _fake_chat(config, messages, max_tokens=400, timeout=60):
        return True, "整体合规情况一般，优先补充金额条款。"

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    summary = semantic.generate_summary(
        score=60, grade="D", conflict_count=2, gap_count=3,
        top_issues=["缺金额", "冲突"], ai_config=cfg,
    )
    assert "优先补充" in summary


def _field_rule():
    from src.rules import FieldRule
    return FieldRule(
        name="合同金额",
        required=True,
        patterns=[r"金额[：:]?\s*[\d,，.]+(?:万元|元)?"],
        description="合同总金额",
    )


def _clause_rule():
    from src.rules import ClauseRule
    return ClauseRule(
        id="payment", name="付款条款", kind="required",
        keywords=["付款", "分期"], patterns=[r"付款[^。]*"],
    )
