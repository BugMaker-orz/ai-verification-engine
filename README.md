# AI 验真引擎

多文件字段级对齐、跨文件冲突定位、规则驱动欠缺检查的自动化验真工具。

> 上传多份文件后，引擎自动做字段级对齐拆解和跨文件冲突定位，依据预设的条款规范查找文件中不足和欠缺的内容，输出带冲突定位、双源依据、补位建议的完整校验报告。

## 功能特性

- **多格式文件解析**：支持 PDF / TXT / DOCX，统一输出纯文本与分页信息
- **字段级对齐拆解**：基于规则库的正则提取，自动识别甲方、乙方、金额、日期等结构化字段
- **跨文件冲突定位**：同字段在多文档间的一致性比对，支持数值容差、日期归一化、文本归一化
- **规则驱动欠缺检查**：必填字段缺失、必含条款缺失、禁止条款出现、字段格式不合法
- **双源依据展示**：每项冲突标注来源文件名与行号，便于人工复核
- **补位建议**：每项欠缺自动生成修改建议
- **验真评分**：100 分制 + A-F 等级，加权扣分（严重25/高10/中4/低1）
- **双格式报告**：Markdown（可编辑）+ HTML（可视化，带严重度颜色标签）

## 快速开始

### 环境要求

- Python 3.9+
- 依赖：`pdfplumber`, `python-docx`, `PyYAML`, `Jinja2`

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

**支持的 AI 服务**：所有 OpenAI 兼容接口（DeepSeek、通义千问、豆包、OpenAI、本地模型等），只需填写对应的 base_url 和 model。

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

# 初始化引擎（加载规则集）
engine = VerificationEngine(ruleset_path="rules/general_contract.yaml")

# 执行验真
result = engine.verify(["doc1.pdf", "doc2.txt"])

# 打印摘要
engine.print_summary(result)

# 保存报告（Markdown + HTML）
paths = engine.save_report(result, "output/", "report")
print(paths["markdown"], paths["html"])
```

## 规则库配置

规则库采用 YAML 格式，位于 `rules/` 目录。可根据不同行业（5类产业）扩展字段与条款。

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
├── cli.py                  # 命令行入口
├── requirements.txt        # Python 依赖
├── README.md               # 项目说明
├── src/
│   ├── __init__.py
│   ├── engine.py           # 主引擎编排
│   ├── parser.py           # 文件解析（PDF/TXT/DOCX）
│   ├── rules.py            # 规则库加载与数据结构
│   ├── extractor.py        # 字段提取与格式校验
│   ├── conflict.py         # 跨文件冲突检测
│   ├── gap.py              # 欠缺与违规检查
│   └── report.py           # 报告生成（Markdown/HTML）
├── rules/
│   └── general_contract.yaml  # 通用合同与文档验真规则
├── samples/
│   ├── contract_main.txt       # 示例：主合同
│   └── contract_supplement.txt # 示例：补充协议（含冲突与欠缺）
├── tests/
│   └── test_engine.py      # 测试用例（7项）
├── docs/
│   └── architecture.md     # 技术架构文档
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

- [ ] 接入 LLM API 做语义级条款冲突检测（当前为关键词/正则）
- [ ] Web UI（Gradio/Streamlit）拖拽上传
- [ ] 规则库可视化编辑器
- [ ] 支持 Excel/CSV 表格类文件解析
- [ ] 报告导出 PDF
- [ ] 多语言规则库（英文合同）

## 许可证

MIT License
