# AI 验真引擎

多文件字段级对齐、跨文件冲突定位、规则驱动欠缺检查的自动化验真工具。支持 AI 语义增强，也可在无 AI 环境下纯规则运行。

> 上传多份文件后，引擎自动做字段级对齐拆解和跨文件冲突定位，依据预设的条款规范查找文件中不足和欠缺的内容，输出带冲突定位、双源依据、补位建议的完整校验报告。

## 功能特性

### 核心验真能力

- **多格式文件解析**：支持 PDF / TXT / DOCX，统一输出纯文本与分页信息
- **字段级对齐拆解**：基于规则库的正则提取，自动识别甲方、乙方、金额、日期等结构化字段
- **跨文件冲突定位**：同字段在多文档间的一致性比对，支持数值容差、日期归一化、文本归一化
- **规则驱动欠缺检查**：必填字段缺失、必含条款缺失、禁止条款出现、字段格式不合法
- **双源依据展示**：每项冲突标注来源文件名与行号，便于人工复核
- **补位建议**：每项欠缺自动生成修改建议
- **验真评分**：100 分制 + A-F 等级，加权扣分（严重25/高10/中4/低1）
- **双格式报告**：Markdown（可编辑）+ HTML（可视化，带严重度颜色标签）

### AI 语义增强（可选）

- **语义级条款匹配**：不只是关键词匹配，AI 理解条款语义（同义表述也能识别）
- **冲突误报排除**：AI 二次确认，排除"表述不同但意思相同"的误报（如"28万元"vs"280,000元"）
- **AI 字段提取增强**：正则提取不到时，AI 语义提取兜底
- **AI 补位建议**：根据文档实际内容生成具体的修改建议和条款模板
- **AI 总体评价**：3-5 句话的总体审查结论和优先改进方向
- **自动降级**：未配置 AI 时自动使用基础规则匹配，所有功能正常

### 使用方式

- **Web 图形界面**：Gradio 构建，拖拽上传、可视化结果、报告下载，零命令行操作
- **命令行工具**：适合脚本化和批量处理
- **Python API**：可嵌入其他项目
- **打包成 exe**：双击即用，对方电脑无需安装 Python（见 [打包指南](docs/打包指南.md)）

## 快速开始

### 环境要求

- Python 3.9+
- 依赖：`pdfplumber`, `python-docx`, `PyYAML`, `Jinja2`, `gradio`, `requests`

### 安装

```bash
pip install -r requirements.txt
```

### Web 界面使用（推荐，无需敲命令）

```bash
python app.py
```

运行后浏览器会自动打开 http://127.0.0.1:7860 ，在页面上：

1. **（可选）配置 AI**：展开顶部"🤖 AI 设置"面板，填写 API 地址、Key、模型名，点"测试连接"确认可用后"保存配置"。配置后自动启用 AI 语义增强；不配置则使用基础规则匹配。
2. 拖拽或点击上传多个文件（PDF / DOCX / TXT）
3. 下拉选择规则库
4. 输入报告名称（可选）
5. 点击"开始验真"
6. 页面显示评分、冲突列表、欠缺列表，可下载 HTML / Markdown 报告

**支持的 AI 服务**：所有 OpenAI 兼容接口（DeepSeek、通义千问、豆包、OpenAI、本地模型等），只需填写对应的 base_url 和 model。详见 [AI 配置指南](docs/AI配置指南.md)。

### 命令行使用

```bash
# 基础模式（无 AI）
python cli.py -r rules/general_contract.yaml -f doc1.pdf doc2.txt -o output/

# AI 增强模式（命令行指定）
python cli.py -r rules/general_contract.yaml -f doc1.pdf doc2.txt \
  --ai-base-url https://api.deepseek.com/v1 \
  --ai-key sk-xxx \
  --ai-model deepseek-chat

# AI 增强模式（从配置文件加载）
python cli.py -r rules/general_contract.yaml -f doc1.pdf doc2.txt --ai-config config/ai_config.json

# 指定报告文件名
python cli.py -r rules/general_contract.yaml -f samples/contract_main.txt samples/contract_supplement.txt -o output/ -n my_report

# 静默模式（不打印终端摘要）
python cli.py -r rules/general_contract.yaml -f doc1.pdf doc2.pdf -o output/ --quiet
```

### Python API 使用

```python
from src.engine import VerificationEngine
from src.ai_client import AIConfig

# ---- 基础模式（无 AI）----
engine = VerificationEngine(ruleset_path="rules/general_contract.yaml")
result = engine.verify(["doc1.pdf", "doc2.txt"])
engine.print_summary(result)
paths = engine.save_report(result, "output/", "report")

# ---- AI 增强模式 ----
ai_cfg = AIConfig(
    base_url="https://api.deepseek.com/v1",
    api_key="sk-xxx",
    model="deepseek-chat",
    enabled=True,
)
engine = VerificationEngine(ruleset_path="rules/general_contract.yaml", ai_config=ai_cfg)
result = engine.verify(["doc1.pdf", "doc2.txt"])
# result.ai_enabled = True, result.ai_model = "deepseek-chat"
# result.ai_summary = AI 生成的总体评价
```

## 规则库配置

规则库采用 YAML 格式，位于 `rules/` 目录。可根据不同行业扩展字段与条款。详见 [规则库编写指南](docs/规则库编写指南.md)。

```yaml
name: "规则集名称"
version: "1.0"
description: "规则集描述"

fields:                    # 字段级规则
  - name: "甲方/委托方"
    required: true
    patterns: ["甲方[:：]\\s*(.+)"]
    format: null           # date / currency / email / phone / id_card

clauses:
  required:                # 必含条款
    - id: "C-001"
      name: "违约责任条款"
      keywords: ["违约责任", "违约金"]
      severity: "high"
  forbidden:               # 禁止条款
    - id: "F-001"
      name: "空白占位符"
      patterns: ["_{3,}", "TODO"]
      severity: "critical"

cross_document:            # 跨文档一致性规则
  - id: "X-001"
    name: "甲方名称一致性"
    fields: ["甲方/委托方"]
    severity: "high"
```

## 项目结构

```
ai-verification-engine/
├── app.py                  # Web 图形界面（Gradio）
├── cli.py                  # 命令行入口
├── requirements.txt        # Python 依赖
├── README.md               # 项目说明（本文件）
├── CHANGELOG.md            # 版本变更日志
├── config/
│   └── ai_config.json      # AI 配置（自动生成，含 API Key，勿提交到公开仓库）
├── src/
│   ├── __init__.py
│   ├── engine.py           # 主引擎编排
│   ├── parser.py           # 文件解析（PDF/TXT/DOCX）
│   ├── rules.py            # 规则库加载与数据结构
│   ├── extractor.py        # 字段提取与格式校验
│   ├── conflict.py         # 跨文件冲突检测
│   ├── gap.py              # 欠缺与违规检查
│   ├── report.py           # 报告生成（Markdown/HTML）
│   ├── ai_client.py        # AI API 客户端（OpenAI 兼容接口）
│   └── semantic.py         # 语义理解模块（基础规则 + AI 双模式）
├── rules/
│   └── general_contract.yaml  # 通用合同与文档验真规则
├── samples/
│   ├── contract_main.txt       # 示例：主合同
│   └── contract_supplement.txt # 示例：补充协议（含冲突与欠缺）
├── tests/
│   └── test_engine.py      # 测试用例（7项）
├── docs/
│   ├── architecture.md     # 技术架构文档
│   ├── 零基础使用指南.md    # 面向非技术人员的使用指南
│   ├── 规则库编写指南.md    # 自定义规则库编写教程
│   └── AI配置指南.md        # 各 AI 服务配置方法
└── output/                 # 报告输出目录
```

## 运行测试

```bash
python tests/test_engine.py
```

测试覆盖：规则集加载、文件解析、字段提取、值冲突逻辑、跨文件冲突检测、欠缺检查、完整引擎端到端。

## 设计参考

本项目规则设计参考了以下开源项目与实践：

- **contract-lint**：确定性规则 + 稳定 rule_id + 严重度 + 行号定位
- **Legal-Conflict-Resolver**：NLI 冲突检测 + 条款类型严重度分级（LIABILITY > PAYMENT > TERMINATION）
- **Vaulytica**：1825 条确定性规则 + 20 条跨文档检查 + 披露前检查
- **ContractGuard**：红旗/警告/保护/缺失四分类 + 公平评分

## 扩展方向

- [x] 接入 LLM API 做语义级条款冲突检测
- [x] Web UI（Gradio）拖拽上传
- [x] AI 语义增强（条款匹配/冲突确认/补位建议/总体评价）
- [ ] 规则库可视化编辑器
- [ ] 支持 Excel/CSV 表格类文件解析
- [ ] 报告导出 PDF
- [ ] 多语言规则库（英文合同）
- [ ] 跨字段逻辑校验（如"金额=单价×数量"）
- [ ] OCR 集成（扫描件 PDF）

## 许可证

MIT License
