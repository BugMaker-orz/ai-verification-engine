"""AI 语义链路回归测试 — 覆盖 AI 启用路径（单条 + 批量接口）。

防止 NameError 类缺陷回归，并验证批量合并调用与 JSON 解析逻辑。
"""
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


# ============================================================
# 补位建议
# ============================================================

def test_generate_remedy_suggestion_with_ai(monkeypatch):
    """AI 启用时生成补位建议，不得抛 NameError（回归：rule 未定义）。"""
    def _fake_chat(config, messages, max_tokens=100, timeout=30):
        return True, '[{"index": 0, "suggestion": "建议补充：明确合同金额、付款节点与违约责任条款。"}]'

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


def test_generate_remedy_suggestions_batch(monkeypatch):
    """批量补位建议：一次请求返回多个建议，按 index 对齐。"""
    calls = []

    def _fake_chat(config, messages, max_tokens=100, timeout=30):
        calls.append(1)
        return True, ('[{"index": 0, "suggestion": "补充金额字段"}, '
                      '{"index": 1, "suggestion": "补充违约责任条款"}]')

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    result = semantic.generate_remedy_suggestions_batch(
        [{"type": "missing_field", "name": "合同金额", "description": "d"},
         {"type": "missing_clause", "name": "违约责任", "description": "d"}],
        "文档内容……", cfg,
    )
    assert result == ["补充金额字段", "补充违约责任条款"]
    assert len(calls) == 1  # 合并为一次调用


def test_generate_remedy_suggestion_no_ai():
    """AI 未启用时返回空字符串，走默认建议。"""
    result = semantic.generate_remedy_suggestion(
        rule_name="合同金额", description="x", finding_type="missing_field"
    )
    assert result == ""


# ============================================================
# 字段提取
# ============================================================

def test_extract_field_semantic_ai_fallback(monkeypatch):
    """正则未命中 + AI 可用时走 AI 提取。"""
    def _fake_chat(config, messages, max_tokens=100, timeout=30):
        return True, '{"合同金额": "500,000"}'

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    value, method = semantic.extract_field_semantic(
        "本文档没有金额相关字样。", _field_rule(), cfg
    )
    assert value == "500,000"
    assert method == "AI 语义提取"


def test_extract_fields_semantic_batch(monkeypatch):
    """批量字段提取：一次请求返回多字段。"""
    calls = []

    def _fake_chat(config, messages, max_tokens=100, timeout=30):
        calls.append(1)
        return True, '{"合同金额": "500,000", "甲方": null}'

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    result = semantic.extract_fields_semantic_batch(
        "文档内容……", [_field_rule(), _field_rule("甲方", r"甲方[:：]?\S+")], cfg
    )
    assert result["合同金额"] == ("500,000", "AI 语义提取")
    assert result["甲方"] == (None, "AI 判断字段不存在")
    assert len(calls) == 1


# ============================================================
# 条款匹配
# ============================================================

def test_clause_match_ai_positive(monkeypatch):
    """AI 语义命中条款（单条）。"""
    def _fake_chat(config, messages, max_tokens=200, timeout=30):
        return True, '{"matched": true, "reason": "表述虽不同但含义一致"}'

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    matched, reason = semantic.clause_match(
        "双方约定按季度结算款项。", _clause_rule(), cfg
    )
    assert matched is True
    assert "AI 语义命中" in reason


def test_clause_match_batch(monkeypatch):
    """批量条款匹配：基础未命中的条款合并为一次 AI 请求。"""
    calls = []

    def _fake_chat(config, messages, max_tokens=200, timeout=30):
        calls.append(1)
        return True, ('[{"id": "payment", "matched": true, "reason": "结算即付款约定"}, '
                      '{"id": "force", "matched": false, "reason": "未提及不可抗力"}]')

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    # 第一个条款基础未命中（无关键词），第二个也未命中
    results = semantic.clause_match_batch(
        "双方约定按季度结算款项。",
        [_clause_rule(), _clause_rule("force", "不可抗力", ["不可抗力"])],
        cfg,
    )
    assert results["payment"][0] is True
    assert "AI 语义命中" in results["payment"][1]
    assert results["force"][0] is False
    assert "AI 语义未命中" in results["force"][1]
    assert len(calls) == 1  # 合并为一次调用


def test_clause_match_batch_basic_hit_no_ai_call(monkeypatch):
    """基础命中的条款不消耗 AI 调用。"""
    calls = []

    def _fake_chat(config, messages, max_tokens=200, timeout=30):
        calls.append(1)
        return True, "[]"

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    results = semantic.clause_match_batch(
        "双方约定分期付款。", [_clause_rule()], cfg  # 文本含关键词"付款"
    )
    assert results["payment"][0] is True
    assert "关键词命中" in results["payment"][1]
    assert len(calls) == 0  # 基础命中，无需 AI


# ============================================================
# 冲突检测
# ============================================================

def test_semantic_conflict_check_no_conflict(monkeypatch):
    """AI 判定两值实质相同，不算冲突（单条）。"""
    def _fake_chat(config, messages, max_tokens=200, timeout=30):
        return True, '[{"index": 0, "conflict": false, "reason": "28万元与280,000元是同一金额"}]'

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    conflict, reason = semantic.semantic_conflict_check("28万元", "280,000元", "合同金额", cfg)
    assert conflict is False
    assert "判定一致" in reason


def test_semantic_conflict_check_batch(monkeypatch):
    """批量冲突检测：一次请求判断多对。"""
    calls = []

    def _fake_chat(config, messages, max_tokens=200, timeout=30):
        calls.append(1)
        return True, ('[{"index": 0, "conflict": false, "reason": "同一金额"}, '
                      '{"index": 1, "conflict": true, "reason": "金额不同"}]')

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    result = semantic.semantic_conflict_check_batch(
        [("合同金额", "28万元", "280,000元"), ("合同金额", "100万", "200万")], cfg
    )
    assert result[0] == (False, "AI 判定一致：同一金额")
    assert result[1][0] is True
    assert len(calls) == 1


def test_semantic_conflict_check_ai_failure(monkeypatch):
    """AI 调用失败时保守判定为冲突。"""
    def _fake_chat(config, messages, max_tokens=200, timeout=30):
        return False, "network error"

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    conflict, reason = semantic.semantic_conflict_check("A", "B", "字段", cfg)
    assert conflict is True
    assert "保守判定" in reason


def test_semantic_conflict_check_markdown_wrapped(monkeypatch):
    """AI 返回带 markdown 代码块的 JSON 也能正确解析。"""
    def _fake_chat(config, messages, max_tokens=200, timeout=30):
        return True, '```json\n[{"index": 0, "conflict": true, "reason": "金额不一致"}]\n```'

    monkeypatch.setattr(semantic, "chat_completion_safe", _fake_chat)
    cfg = _fake_ai_config()

    conflict, reason = semantic.semantic_conflict_check("100万", "200万", "合同金额", cfg)
    assert conflict is True
    assert "金额不一致" in reason


# ============================================================
# 摘要
# ============================================================

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


def test_smart_snippet():
    """智能截取保留首尾。"""
    text = "甲" * 5000
    snippet = semantic._smart_snippet(text, limit=3000)
    assert len(snippet) < 3200
    assert snippet.startswith("甲")
    assert snippet.endswith("甲")
    assert "中间内容省略" in snippet


# ============================================================
# 辅助
# ============================================================

def _field_rule(name="合同金额", pattern=r"金额[：:]?\s*[\d,，.]+(?:万元|元)?"):
    from src.rules import FieldRule
    return FieldRule(
        name=name,
        required=True,
        patterns=[pattern],
        description="字段描述",
    )


def _clause_rule(rid="payment", name="付款条款", keywords=None):
    from src.rules import ClauseRule
    return ClauseRule(
        id=rid, name=name, kind="required",
        keywords=keywords or ["付款", "分期"], patterns=[r"付款[^。]*"],
    )
