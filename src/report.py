"""报告生成器：输出 Markdown 和 HTML 格式的验真报告，带冲突定位、双源依据、补位建议。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from jinja2 import Template

from .conflict import ConflictFinding
from .extractor import DocFields
from .gap import GapFinding
from .parser import ParsedDoc
from .rules import RuleSet, SEVERITY_ORDER


SEVERITY_LABEL = {
    "critical": "严重",
    "high": "高",
    "medium": "中",
    "low": "低",
    "info": "提示",
}

SEVERITY_COLOR = {
    "critical": "#dc2626",
    "high": "#ea580c",
    "medium": "#ca8a04",
    "low": "#2563eb",
    "info": "#6b7280",
}


@dataclass
class VerificationResult:
    """完整验真结果。"""
    ruleset: RuleSet
    docs: List[ParsedDoc]
    doc_fields: List[DocFields]
    conflicts: List[ConflictFinding] = field(default_factory=list)
    gaps: List[GapFinding] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    @property
    def total_findings(self) -> int:
        return len(self.conflicts) + len(self.gaps)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.conflicts + self.gaps if f.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.conflicts + self.gaps if f.severity == "high")

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.conflicts + self.gaps if f.severity == "medium")

    @property
    def low_count(self) -> int:
        return sum(1 for f in self.conflicts + self.gaps if f.severity == "low")

    @property
    def score(self) -> int:
        """验真评分：100 - 加权扣分。"""
        weights = {"critical": 25, "high": 10, "medium": 4, "low": 1, "info": 0}
        deduction = sum(weights.get(f.severity, 0) for f in self.conflicts + self.gaps)
        return max(0, 100 - deduction)

    @property
    def grade(self) -> str:
        s = self.score
        if s >= 90:
            return "A"
        if s >= 80:
            return "B"
        if s >= 70:
            return "C"
        if s >= 60:
            return "D"
        return "F"


def _sort_findings(findings):
    return sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 0), reverse=True)


# ---------- Markdown 报告 ----------

_MD_TEMPLATE = """# AI 验真报告

**规则集**：{{ ruleset.name }} v{{ ruleset.version }}
**生成时间**：{{ generated_at }}
**验真文档**：{{ doc_count }} 份

---

## 一、验真概览

| 指标 | 数值 |
|------|------|
| 验真评分 | **{{ score }} / 100**（等级 {{ grade }}） |
| 发现问题总数 | {{ total_findings }} |
| 严重（critical） | {{ critical_count }} |
| 高（high） | {{ high_count }} |
| 中（medium） | {{ medium_count }} |
| 低（low） | {{ low_count }} |
| 跨文件冲突 | {{ conflict_count }} |
| 欠缺/违规 | {{ gap_count }} |

### 文档清单

{% for doc in docs %}
- **{{ doc.filename }}**（{{ doc.file_type | upper }}，{{ doc.line_count }} 行）
{% endfor %}

---

## 二、字段提取结果

{% for df in doc_fields %}
### {{ df.doc.filename }}

| 字段 | 值 | 状态 | 行号 |
|------|-----|------|------|
{% for name, ef in df.fields.items() %}
| {{ name }} | {{ ef.value if ef.found else "*(未找到)*" }} | {% if not ef.found %}缺失{% elif ef.format_valid == False %}格式不合法{% else %}✓{% endif %} | {{ ef.source_line or "-" }} |
{% endfor %}

{% endfor %}

---

## 三、跨文件冲突定位

{% if conflicts %}
{% for c in conflicts %}
### [{{ c.rule_id }}] {{ c.rule_name }} — {{ c.field_name }}

- **严重度**：<span style="color:{{ severity_color(c.severity) }}">**{{ severity_label(c.severity) }}**</span>
- **冲突类型**：{{ c.conflict_type }}
- **描述**：{{ c.description }}
- **双源依据**：

{% for filename, value, line in c.sources %}
  - {{ filename }}{% if line %}（第 {{ line }} 行）{% endif %}：`{{ value }}`
{% endfor %}

{% endfor %}
{% else %}
*未发现跨文件冲突。*
{% endif %}

---

## 四、欠缺与违规检查

{% if gaps %}
{% for g in gaps %}
### [{{ g.rule_id }}] {{ g.rule_name }}

- **严重度**：<span style="color:{{ severity_color(g.severity) }}">**{{ severity_label(g.severity) }}**</span>
- **类型**：{{ g.kind }}
- **描述**：{{ g.description }}
{% if g.source_line %}- **位置**：第 {{ g.source_line }} 行{% endif %}
{% if g.suggestion %}- **补位建议**：{{ g.suggestion }}{% endif %}

{% endfor %}
{% else %}
*未发现欠缺或违规。*
{% endif %}

---

## 五、规则集说明

{{ ruleset.description }}

- 字段规则：{{ field_count }} 条
- 必含条款：{{ required_clause_count }} 条
- 禁止条款：{{ forbidden_clause_count }} 条
- 跨文档规则：{{ cross_doc_count }} 条

---

*本报告由 AI 验真引擎自动生成，仅供参考。关键决策请结合人工复核。*
"""


def generate_markdown(result: VerificationResult) -> str:
    """生成 Markdown 格式报告。"""
    t = Template(_MD_TEMPLATE)
    return t.render(
        ruleset=result.ruleset,
        generated_at=result.generated_at,
        doc_count=len(result.docs),
        docs=result.docs,
        doc_fields=result.doc_fields,
        conflicts=_sort_findings(result.conflicts),
        gaps=_sort_findings(result.gaps),
        conflict_count=len(result.conflicts),
        gap_count=len(result.gaps),
        total_findings=result.total_findings,
        critical_count=result.critical_count,
        high_count=result.high_count,
        medium_count=result.medium_count,
        low_count=result.low_count,
        score=result.score,
        grade=result.grade,
        field_count=len(result.ruleset.fields),
        required_clause_count=len(result.ruleset.required_clauses),
        forbidden_clause_count=len(result.ruleset.forbidden_clauses),
        cross_doc_count=len(result.ruleset.cross_doc_rules),
        severity_label=lambda s: SEVERITY_LABEL.get(s, s),
        severity_color=lambda s: SEVERITY_COLOR.get(s, "#000"),
    )


# ---------- HTML 报告 ----------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 验真报告 — {{ ruleset.name }}</title>
<style>
  :root { --bg: #f8fafc; --card: #fff; --border: #e2e8f0; --text: #1e293b; --muted: #64748b; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--text); line-height: 1.7; padding: 2rem; }
  .container { max-width: 960px; margin: 0 auto; }
  h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }
  h2 { font-size: 1.3rem; margin: 2rem 0 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid var(--border); }
  h3 { font-size: 1.05rem; margin: 1.2rem 0 0.6rem; }
  .meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem; }
  .score-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; margin: 1rem 0; }
  .score-item { text-align: center; padding: 1rem; border-radius: 8px; background: var(--bg); }
  .score-item .num { font-size: 1.8rem; font-weight: 700; }
  .score-item .label { font-size: 0.8rem; color: var(--muted); margin-top: 0.3rem; }
  table { width: 100%; border-collapse: collapse; margin: 0.8rem 0; font-size: 0.9rem; }
  th, td { padding: 0.6rem 0.8rem; text-align: left; border-bottom: 1px solid var(--border); }
  th { background: var(--bg); font-weight: 600; }
  .badge { display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; color: #fff; }
  .finding { border-left: 4px solid; padding: 1rem 1.2rem; margin: 0.8rem 0; background: var(--card); border-radius: 0 8px 8px 0; }
  .finding .fid { font-family: monospace; font-size: 0.8rem; color: var(--muted); }
  .finding .desc { margin: 0.4rem 0; }
  .finding .suggestion { background: #f0fdf4; border: 1px solid #bbf7d0; padding: 0.6rem 0.8rem; border-radius: 6px; font-size: 0.9rem; margin-top: 0.5rem; }
  .sources { margin: 0.5rem 0; padding-left: 1.2rem; font-size: 0.88rem; }
  .sources li { margin: 0.2rem 0; }
  .grade-A { color: #16a34a; } .grade-B { color: #2563eb; } .grade-C { color: #ca8a04; }
  .grade-D { color: #ea580c; } .grade-F { color: #dc2626; }
  .footer { text-align: center; color: var(--muted); font-size: 0.8rem; margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--border); }
</style>
</head>
<body>
<div class="container">

<h1>AI 验真报告</h1>
<div class="meta">
  规则集：{{ ruleset.name }} v{{ ruleset.version }} ｜ 生成时间：{{ generated_at }} ｜ 验真文档：{{ doc_count }} 份
</div>

<h2>一、验真概览</h2>
<div class="score-grid">
  <div class="score-item"><div class="num grade-{{ grade }}">{{ score }}</div><div class="label">验真评分 / 100</div></div>
  <div class="score-item"><div class="num grade-{{ grade }}">{{ grade }}</div><div class="label">等级</div></div>
  <div class="score-item"><div class="num">{{ total_findings }}</div><div class="label">问题总数</div></div>
  <div class="score-item"><div class="num" style="color:#dc2626">{{ critical_count + high_count }}</div><div class="label">严重+高</div></div>
  <div class="score-item"><div class="num">{{ conflict_count }}</div><div class="label">跨文件冲突</div></div>
  <div class="score-item"><div class="num">{{ gap_count }}</div><div class="label">欠缺/违规</div></div>
</div>

<div class="card">
<strong>文档清单</strong>
<ul style="margin-top:0.5rem; padding-left:1.2rem;">
{% for doc in docs %}
  <li><strong>{{ doc.filename }}</strong>（{{ doc.file_type | upper }}，{{ doc.line_count }} 行）</li>
{% endfor %}
</ul>
</div>

<h2>二、字段提取结果</h2>
{% for df in doc_fields %}
<h3>{{ df.doc.filename }}</h3>
<table>
<tr><th>字段</th><th>提取值</th><th>状态</th><th>行号</th></tr>
{% for name, ef in df.fields.items() %}
<tr>
  <td>{{ name }}</td>
  <td>{{ ef.value if ef.found else '<em style="color:#dc2626">未找到</em>' }}</td>
  <td>{% if not ef.found %}<span class="badge" style="background:#dc2626">缺失</span>{% elif ef.format_valid == False %}<span class="badge" style="background:#ca8a04">格式不合法</span>{% else %}<span class="badge" style="background:#16a34a">✓</span>{% endif %}</td>
  <td>{{ ef.source_line or "-" }}</td>
</tr>
{% endfor %}
</table>
{% endfor %}

<h2>三、跨文件冲突定位</h2>
{% if conflicts %}
{% for c in conflicts %}
<div class="finding" style="border-color:{{ severity_color(c.severity) }}">
  <div class="fid">{{ c.rule_id }} ｜ 字段：{{ c.field_name }} ｜ 类型：{{ c.conflict_type }}</div>
  <h3 style="margin-top:0.3rem;">{{ c.rule_name }} <span class="badge" style="background:{{ severity_color(c.severity) }}">{{ severity_label(c.severity) }}</span></h3>
  <div class="desc">{{ c.description }}</div>
  <strong>双源依据：</strong>
  <ul class="sources">
  {% for filename, value, line in c.sources %}
    <li><strong>{{ filename }}</strong>{% if line %}（第 {{ line }} 行）{% endif %}：<code>{{ value }}</code></li>
  {% endfor %}
  </ul>
</div>
{% endfor %}
{% else %}
<div class="card" style="text-align:center; color:#16a34a;">✓ 未发现跨文件冲突</div>
{% endif %}

<h2>四、欠缺与违规检查</h2>
{% if gaps %}
{% for g in gaps %}
<div class="finding" style="border-color:{{ severity_color(g.severity) }}">
  <div class="fid">{{ g.rule_id }} ｜ 类型：{{ g.kind }}{% if g.source_line %} ｜ 第 {{ g.source_line }} 行{% endif %}</div>
  <h3 style="margin-top:0.3rem;">{{ g.rule_name }} <span class="badge" style="background:{{ severity_color(g.severity) }}">{{ severity_label(g.severity) }}</span></h3>
  <div class="desc">{{ g.description }}</div>
  {% if g.suggestion %}<div class="suggestion"><strong>补位建议：</strong>{{ g.suggestion }}</div>{% endif %}
</div>
{% endfor %}
{% else %}
<div class="card" style="text-align:center; color:#16a34a;">✓ 未发现欠缺或违规</div>
{% endif %}

<h2>五、规则集说明</h2>
<div class="card">
  <p>{{ ruleset.description }}</p>
  <ul style="margin-top:0.5rem; padding-left:1.2rem;">
    <li>字段规则：{{ field_count }} 条</li>
    <li>必含条款：{{ required_clause_count }} 条</li>
    <li>禁止条款：{{ forbidden_clause_count }} 条</li>
    <li>跨文档规则：{{ cross_doc_count }} 条</li>
  </ul>
</div>

<div class="footer">本报告由 AI 验真引擎自动生成，仅供参考。关键决策请结合人工复核。</div>
</div>
</body>
</html>
"""


def generate_html(result: VerificationResult) -> str:
    """生成 HTML 格式报告。"""
    t = Template(_HTML_TEMPLATE)
    return t.render(
        ruleset=result.ruleset,
        generated_at=result.generated_at,
        doc_count=len(result.docs),
        docs=result.docs,
        doc_fields=result.doc_fields,
        conflicts=_sort_findings(result.conflicts),
        gaps=_sort_findings(result.gaps),
        conflict_count=len(result.conflicts),
        gap_count=len(result.gaps),
        total_findings=result.total_findings,
        critical_count=result.critical_count,
        high_count=result.high_count,
        medium_count=result.medium_count,
        low_count=result.low_count,
        score=result.score,
        grade=result.grade,
        field_count=len(result.ruleset.fields),
        required_clause_count=len(result.ruleset.required_clauses),
        forbidden_clause_count=len(result.ruleset.forbidden_clauses),
        cross_doc_count=len(result.ruleset.cross_doc_rules),
        severity_label=lambda s: SEVERITY_LABEL.get(s, s),
        severity_color=lambda s: SEVERITY_COLOR.get(s, "#000"),
    )


def save_report(result: VerificationResult, output_dir: str, basename: str = "verification_report") -> Dict[str, str]:
    """保存 Markdown 和 HTML 报告到指定目录，返回文件路径字典。"""
    os.makedirs(output_dir, exist_ok=True)
    md_path = os.path.join(output_dir, f"{basename}.md")
    html_path = os.path.join(output_dir, f"{basename}.html")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_markdown(result))
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(generate_html(result))
    return {"markdown": md_path, "html": html_path}
