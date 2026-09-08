"""AI API 客户端 — 支持所有 OpenAI 兼容接口（DeepSeek / 通义千问 / 豆包 / OpenAI / 本地模型等）。

不依赖 openai SDK，纯 requests 调用 /v1/chat/completions，轻量且通用。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional

import requests


@dataclass
class AIConfig:
    """AI 配置。"""
    base_url: str = ""           # API 地址，如 https://api.deepseek.com/v1
    api_key: str = ""            # API Key
    model: str = ""              # 模型名，如 deepseek-chat / gpt-4o-mini
    enabled: bool = False        # 是否启用 AI
    timeout: int = 60            # 超时秒数
    temperature: float = 0.1     # 温度（越低越确定）

    def is_ready(self) -> bool:
        """配置是否完整可用。"""
        return self.enabled and bool(self.base_url) and bool(self.api_key) and bool(self.model)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AIConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# 默认配置文件路径
DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "ai_config.json"
)


def load_config(path: str = DEFAULT_CONFIG_PATH) -> AIConfig:
    """从 JSON 文件加载配置。"""
    if not os.path.isfile(path):
        return AIConfig()
    try:
        with open(path, encoding="utf-8") as f:
            return AIConfig.from_dict(json.load(f))
    except (json.JSONDecodeError, OSError):
        return AIConfig()


def save_config(config: AIConfig, path: str = DEFAULT_CONFIG_PATH) -> None:
    """保存配置到 JSON 文件。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)


def test_connection(config: AIConfig) -> tuple[bool, str]:
    """测试 AI 连接是否可用。返回 (是否成功, 消息)。"""
    if not config.is_ready():
        return False, "配置不完整：请填写 API 地址、Key 和模型名"

    url = config.base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": "回复'连接成功'三个字。"}],
        "max_tokens": 20,
        "temperature": 0,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=config.timeout)
        if resp.status_code == 200:
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            return True, f"连接成功，模型回复：{content}"
        else:
            return False, f"连接失败（HTTP {resp.status_code}）：{resp.text[:200]}"
    except requests.exceptions.Timeout:
        return False, f"连接超时（{config.timeout}秒），请检查网络或 API 地址"
    except requests.exceptions.ConnectionError:
        return False, "网络连接失败，请检查 API 地址是否正确"
    except Exception as e:
        return False, f"连接出错：{type(e).__name__}: {e}"


def chat_completion(config: AIConfig, messages: List[dict],
                    max_tokens: int = 2000, temperature: Optional[float] = None) -> str:
    """调用 AI 聊天接口，返回回复文本。失败时抛出异常。"""
    if not config.is_ready():
        raise RuntimeError("AI 配置不完整")

    url = config.base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature if temperature is not None else config.temperature,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=config.timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"AI API 返回错误（HTTP {resp.status_code}）：{resp.text[:300]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def chat_completion_safe(config: AIConfig, messages: List[dict],
                         max_tokens: int = 2000, temperature: Optional[float] = None) -> tuple[bool, str]:
    """安全版聊天接口，失败时返回 (False, 错误信息)，不抛异常。"""
    try:
        return True, chat_completion(config, messages, max_tokens, temperature)
    except Exception as e:
        return False, str(e)
