# AI 配置指南

本指南说明如何为 AI 验真引擎配置 AI 语义增强功能。引擎支持所有 **OpenAI 兼容接口**，只需填写 API 地址（base_url）和模型名（model）。

## 1. 配置方式

### 方式一：Web 界面配置（推荐）

1. 运行 `python app.py` 打开 Web 界面
2. 展开顶部"🤖 AI 设置"面板
3. 填写以下三项：
   - **API 地址**：对应服务的 base_url（见下方各服务配置表）
   - **API Key**：你的 API 密钥
   - **模型名**：对应服务的模型名
4. 点击"🔌 测试连接"，确认显示绿色"连接成功"
5. 点击"💾 保存配置"，配置会保存到 `config/ai_config.json`，下次打开自动加载

### 方式二：命令行参数

```bash
python cli.py -r rules/general_contract.yaml -f doc1.pdf doc2.pdf \
  --ai-base-url https://api.deepseek.com/v1 \
  --ai-key sk-xxxxxxxx \
  --ai-model deepseek-chat
```

### 方式三：配置文件

手动创建 `config/ai_config.json`：

```json
{
  "base_url": "https://api.deepseek.com/v1",
  "api_key": "sk-xxxxxxxx",
  "model": "deepseek-chat",
  "enabled": true,
  "timeout": 60,
  "temperature": 0.1
}
```

然后命令行使用 `--ai-config config/ai_config.json` 加载。

### 方式四：Python API

```python
from src.ai_client import AIConfig
from src.engine import VerificationEngine

ai_cfg = AIConfig(
    base_url="https://api.deepseek.com/v1",
    api_key="sk-xxxxxxxx",
    model="deepseek-chat",
    enabled=True,
)
engine = VerificationEngine(ruleset_path="rules/general_contract.yaml", ai_config=ai_cfg)
result = engine.verify(["doc1.pdf", "doc2.pdf"])
```

## 2. 各 AI 服务配置

### 国内服务

| 服务 | API 地址 (base_url) | 模型名 (model) | 获取 Key |
|------|---------------------|----------------|---------|
| **DeepSeek** | `https://api.deepseek.com/v1` | `deepseek-chat` | https://platform.deepseek.com/ |
| **通义千问 (DashScope)** | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` / `qwen-turbo` / `qwen-max` | https://dashscope.console.aliyun.com/ |
| **豆包 (火山方舟)** | `https://ark.cn-beijing.volces.com/api/v3` | 接入点 ID（如 `ep-xxxxxxxx`） | https://console.volcengine.com/ark |
| **智谱 GLM** | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-plus` / `glm-4-flash` | https://open.bigmodel.cn/ |
| **百度文心 (千帆)** | `https://qianfan.baidubce.com/v2` | `ernie-4.0` / `ernie-3.5` | https://console.bce.baidu.com/qianfan/ |
| **Moonshot (Kimi)** | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` / `moonshot-v1-32k` | https://platform.moonshot.cn/ |
| **MiniMax** | `https://api.minimax.chat/v1` | `abab6.5s-chat` | https://platform.minimaxi.com/ |
| **零一万物 (Yi)** | `https://api.lingyiwanwu.com/v1` | `yi-large` / `yi-medium` | https://platform.lingyiwanwu.com/ |

### 国际服务

| 服务 | API 地址 (base_url) | 模型名 (model) | 获取 Key |
|------|---------------------|----------------|---------|
| **OpenAI** | `https://api.openai.com/v1` | `gpt-4o-mini` / `gpt-4o` / `gpt-3.5-turbo` | https://platform.openai.com/api-keys |
| **Anthropic (经代理)** | 代理地址 + `/v1` | 需代理转换 | 需 OpenAI 兼容代理 |
| **Google Gemini (经代理)** | 代理地址 + `/v1` | 需代理转换 | 需 OpenAI 兼容代理 |

> 注：Anthropic 和 Google 的原生 API 不是 OpenAI 兼容格式，需要通过代理服务（如 One API、New API、Claude Proxy 等）转换为 OpenAI 兼容接口后使用。

### 本地模型 / 自建服务

| 服务 | API 地址 (base_url) | 模型名 (model) | 说明 |
|------|---------------------|----------------|------|
| **Ollama** | `http://localhost:11434/v1` | 已拉取的模型名（如 `qwen2.5:7b`） | 需先 `ollama pull qwen2.5:7b` |
| **vLLM** | `http://localhost:8000/v1` | 加载的模型名 | 自建推理服务 |
| **LM Studio** | `http://localhost:1234/v1` | 加载的模型名 | 桌面端本地推理 |
| **Xinference** | `http://localhost:9997/v1` | 模型 UID | 开源推理平台 |
| **One API / New API** | 你的域名 + `/v1` | 渠道模型名 | API 聚合管理平台 |

## 3. 配置示例

### DeepSeek 示例（性价比高，推荐）

```
API 地址：https://api.deepseek.com/v1
API Key：sk-xxxxxxxxxxxxxxxx（在 DeepSeek 开放平台获取）
模型名：deepseek-chat
```

### 通义千问示例（阿里云用户方便）

```
API 地址：https://dashscope.aliyuncs.com/compatible-mode/v1
API Key：sk-xxxxxxxxxxxxxxxx（在阿里云 DashScope 控制台获取）
模型名：qwen-plus
```

### 本地 Ollama 示例（完全免费，需本地 GPU）

```
API 地址：http://localhost:11434/v1
API Key：ollama（任意值，Ollama 不校验 Key）
模型名：qwen2.5:7b（需先执行 ollama pull qwen2.5:7b）
```

## 4. 模型选择建议

| 场景 | 推荐模型 | 理由 |
|------|---------|------|
| **日常使用 / 性价比** | `deepseek-chat` / `qwen-plus` | 价格低，中文理解好，速度快 |
| **复杂合同 / 长文档** | `gpt-4o` / `qwen-max` / `glm-4-plus` | 推理能力强，长上下文，语义理解更准确 |
| **快速预览 / 大批量** | `deepseek-chat` / `qwen-turbo` / `gpt-4o-mini` | 速度快，价格极低，适合初步筛查 |
| **隐私敏感 / 离线** | 本地 Ollama (`qwen2.5:14b`) | 数据不出本地，完全免费 |
| **预算有限** | `glm-4-flash` / `qwen-turbo` | 免费或极低价，基础语义理解够用 |

## 5. AI 增强功能说明

配置 AI 后，引擎会自动启用以下增强功能：

| 功能 | 说明 | 调用次数（每份文档） |
|------|------|---------------------|
| 语义级条款匹配 | 关键词未命中时，AI 判断是否语义覆盖 | 每条必含/禁止条款 × 每份文档 |
| 冲突误报排除 | 基础检测到冲突后，AI 二次确认 | 每处冲突 |
| AI 字段提取 | 正则提取不到时，AI 语义提取 | 每个未提取到的字段 |
| AI 补位建议 | 根据文档内容生成具体修改建议 | 每项欠缺/违规 |
| AI 总体评价 | 生成 3-5 句审查结论 | 每次验真 1 次 |

> **成本估算**：以一份 10 条款的合同为例，AI 调用约 15-25 次，每次输入约 500-2000 token。使用 `deepseek-chat` 约 0.01-0.05 元/份文档。

## 6. 常见问题

### Q：配置后测试连接失败怎么办？

1. 检查 API 地址是否正确（注意末尾是否需要 `/v1`）
2. 检查 API Key 是否复制完整（不要有多余空格）
3. 检查模型名是否正确（大小写、连字符）
4. 检查账户余额是否充足
5. 检查网络是否能访问该 API（国际服务可能需要代理）

### Q：不配置 AI 能用吗？

完全可以。不配置 AI 时自动使用"基础规则匹配"模式，所有核心功能（字段提取、冲突检测、欠缺检查、报告生成）都正常工作。AI 只是增强语义理解能力。

### Q：AI 调用失败会怎样？

所有 AI 调用都有降级机制：AI 调用失败时自动回退到基础规则结果，不会导致整个验真失败。报告中会标注使用的是基础模式还是 AI 模式。

### Q：API Key 安全吗？

API Key 保存在本地 `config/ai_config.json` 文件中，不会上传到任何服务器。建议将此文件加入 `.gitignore`，不要提交到公开仓库。

### Q：可以用公司内部的 AI 平台吗？

可以。只要公司内部平台提供 OpenAI 兼容接口（大多数企业 AI 平台都支持），填写对应的 base_url、api_key、model 即可。

### Q：temperature 参数是什么？

`temperature` 控制 AI 输出的随机性。验真场景建议使用较低值（默认 0.1），让输出更确定、更一致。值越高输出越随机、越有创造性。可在 `config/ai_config.json` 中修改。
