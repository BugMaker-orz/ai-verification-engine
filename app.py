#!/usr/bin/env python3
"""AI 验真引擎 — Web 图形界面（Gradio）

用法：
  python app.py
  然后浏览器打开 http://127.0.0.1:7860
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gradio as gr
from src.engine import VerificationEngine
from src.rules import list_available_rules


# ---------- 配置 ----------
RULES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

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
GRADE_COLOR = {
    "A": "#16a34a", "B": "#2563eb", "C": "#ca8a04",
    "D": "#ea580c", "F": "#dc2626",
}


def _get_rules_list() -> list[str]:
    """获取可用规则库列表。"""
    rules = list_available_rules(RULES_DIR)
    return rules if rules else ["general_contract.yaml"]


def _badge(text: str, color: str) -> str:
    return f'<span style="background:{color};color:#fff;padding:2px 10px;border-radius:999px;font-size:0.8rem;font-weight:600;">{text}</span>'


def verify_files(files, rule_file: str, report_name: str):
    """核心验真函数，被 Gradio 调用。"""
    if not files:
        return (
            gr.update(value="⚠️ 请先上传要检查的文件"),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            None,
            None,
        )

    # 收集文件路径（Gradio 上传的文件是临时路径）
    file_paths = [f.name if hasattr(f, "name") else f for f in files]

    # 加载规则库
    rule_path = os.path.join(RULES_DIR, rule_file)
    if not os.path.isfile(rule_path):
        return (
            gr.update(value=f"❌ 规则库文件不存在：{rule_file}"),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            None,
            None,
        )

    try:
        engine = VerificationEngine(ruleset_path=rule_path)
        result = engine.verify(file_paths)
    except Exception as e:
        return (
            gr.update(value=f"❌ 运行出错：{type(e).__name__}: {e}"),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            None,
            None,
        )

    # 保存报告
    safe_name = report_name.strip() or "verification_report"
    paths = engine.save_report(result, OUTPUT_DIR, safe_name)

    # ---- 构建结果 HTML ----
    grade_color = GRADE_COLOR.get(result.grade, "#6b7280")

    # 概览
    overview_html = f"""
    <div style="text-align:center;padding:1.5rem;background:#f8fafc;border-radius:12px;margin-bottom:1rem;">
        <div style="font-size:3rem;font-weight:800;color:{grade_color};">{result.score}<span style="font-size:1.2rem;color:#64748b;">/100</span></div>
        <div style="font-size:1.5rem;font-weight:700;color:{grade_color};margin-top:0.3rem;">等级 {result.grade}</div>
        <div style="margin-top:1rem;display:flex;justify-content:center;gap:1rem;flex-wrap:wrap;">
            {_badge(f"严重 {result.critical_count}", SEVERITY_COLOR['critical'])}
            {_badge(f"高 {result.high_count}", SEVERITY_COLOR['high'])}
            {_badge(f"中 {result.medium_count}", SEVERITY_COLOR['medium'])}
            {_badge(f"低 {result.low_count}", SEVERITY_COLOR['low'])}
            {_badge(f"冲突 {len(result.conflicts)}", "#7c3aed")}
            {_badge(f"欠缺 {len(result.gaps)}", "#0891b2")}
        </div>
    </div>
    <div style="margin-bottom:0.5rem;"><strong>检查文件（{len(result.docs)} 份）：</strong></div>
    <ul style="margin:0 0 1rem 1.5rem;">
    """
    for doc in result.docs:
        overview_html += f"<li>{doc.filename}（{doc.file_type.upper()}，{doc.line_count} 行）</li>"
    overview_html += "</ul>"

    # 冲突列表
    conflict_html = ""
    if result.conflicts:
        for c in result.conflicts:
            color = SEVERITY_COLOR.get(c.severity, "#6b7280")
            sources_html = ""
            for filename, value, line in c.sources:
                loc = f"（第 {line} 行）" if line else ""
                sources_html += f"<li><strong>{filename}</strong>{loc}：<code>{value}</code></li>"
            conflict_html += f"""
            <div style="border-left:4px solid {color};padding:0.8rem 1rem;margin-bottom:0.8rem;background:#fff;border-radius:0 8px 8px 0;">
                <div style="font-weight:700;margin-bottom:0.3rem;">
                    {_badge(SEVERITY_LABEL.get(c.severity, c.severity), color)}
                    <span style="margin-left:0.5rem;">{c.rule_name}</span>
                    <span style="color:#64748b;font-size:0.8rem;margin-left:0.5rem;">{c.rule_id} · {c.field_name}</span>
                </div>
                <div style="margin-bottom:0.3rem;">{c.description}</div>
                <div><strong>双源依据：</strong><ul style="margin:0.3rem 0 0 1.2rem;">{sources_html}</ul></div>
            </div>
            """
    else:
        conflict_html = '<div style="text-align:center;padding:2rem;color:#16a34a;font-weight:600;">✓ 未发现跨文件冲突</div>'

    # 欠缺列表
    gap_html = ""
    if result.gaps:
        for g in result.gaps:
            color = SEVERITY_COLOR.get(g.severity, "#6b7280")
            loc = f"（第 {g.source_line} 行）" if g.source_line else ""
            suggestion_html = f'<div style="background:#f0fdf4;border:1px solid #bbf7d0;padding:0.5rem 0.8rem;border-radius:6px;margin-top:0.4rem;font-size:0.9rem;"><strong>补位建议：</strong>{g.suggestion}</div>' if g.suggestion else ""
            gap_html += f"""
            <div style="border-left:4px solid {color};padding:0.8rem 1rem;margin-bottom:0.8rem;background:#fff;border-radius:0 8px 8px 0;">
                <div style="font-weight:700;margin-bottom:0.3rem;">
                    {_badge(SEVERITY_LABEL.get(g.severity, g.severity), color)}
                    <span style="margin-left:0.5rem;">{g.rule_name}</span>
                    <span style="color:#64748b;font-size:0.8rem;margin-left:0.5rem;">{g.rule_id}{loc}</span>
                </div>
                <div>{g.description}</div>
                {suggestion_html}
            </div>
            """
    else:
        gap_html = '<div style="text-align:center;padding:2rem;color:#16a34a;font-weight:600;">✓ 未发现欠缺或违规</div>'

    return (
        gr.update(value=overview_html),
        gr.update(value=conflict_html, visible=True),
        gr.update(value=gap_html, visible=True),
        gr.update(visible=True),
        paths["html"],
        paths["markdown"],
    )


# ---------- Gradio 界面 ----------
def build_ui():
    with gr.Blocks(
        title="AI 验真引擎",
    ) as demo:
        gr.Markdown("""
        # 🔍 AI 验真引擎
        上传多份文件，自动做字段级对齐、跨文件冲突定位、规则驱动欠缺检查，生成带双源依据和补位建议的校验报告。
        """)

        with gr.Row():
            # 左侧：输入区
            with gr.Column(scale=1):
                gr.Markdown("### 📁 1. 上传文件")
                file_input = gr.File(
                    label="支持 PDF / DOCX / TXT，可多选",
                    file_count="multiple",
                    file_types=[".pdf", ".docx", ".txt", ".md"],
                    height=200,
                )

                gr.Markdown("### ⚙️ 2. 选择规则库")
                rule_dropdown = gr.Dropdown(
                    label="检查规则",
                    choices=_get_rules_list(),
                    value="general_contract.yaml",
                    allow_custom_value=True,
                )

                gr.Markdown("### 📝 3. 报告名称")
                report_name = gr.Textbox(
                    label="报告文件名（可选）",
                    value="verification_report",
                    placeholder="比如：2024合同检查",
                )

                run_btn = gr.Button("🚀 开始验真", variant="primary", size="lg")

            # 右侧：结果区
            with gr.Column(scale=2):
                gr.Markdown("### 📊 验真结果")
                overview = gr.HTML(value='<div style="text-align:center;padding:3rem;color:#94a3b8;">上传文件后点击"开始验真"</div>')

                with gr.Group(visible=False) as conflict_group:
                    gr.Markdown("#### ⚠️ 跨文件冲突")
                    conflict_out = gr.HTML()
                with gr.Group(visible=False) as gap_group:
                    gr.Markdown("#### 📋 欠缺与违规")
                    gap_out = gr.HTML()

                with gr.Group(visible=False) as download_group:
                    gr.Markdown("#### 📥 下载报告")
                    with gr.Row():
                        html_download = gr.File(label="HTML 报告（浏览器打开，可视化）")
                        md_download = gr.File(label="Markdown 报告（可编辑）")

        run_btn.click(
            fn=verify_files,
            inputs=[file_input, rule_dropdown, report_name],
            outputs=[overview, conflict_group, gap_group, download_group, html_download, md_download],
        )

        gr.Markdown("""
        <div class="footer">
        AI 验真引擎 · 所有检查在本地运行，文件不会上传到任何服务器<br>
        项目地址：<a href="https://github.com/BugMaker-orz/ai-verification-engine" target="_blank">github.com/BugMaker-orz/ai-verification-engine</a>
        </div>
        """)

    return demo


if __name__ == "__main__":
    demo = build_ui()
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        inbrowser=True,
        show_error=True,
        theme=gr.themes.Soft(),
        css="""
        .gradio-container { max-width: 1100px !important; }
        .footer { text-align: center; color: #94a3b8; font-size: 0.8rem; margin-top: 1rem; }
        """,
    )
