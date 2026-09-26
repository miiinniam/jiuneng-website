"""
DeepSeek V4 Flash AI 客户端
===========================

封装 DeepSeek API 调用（OpenAI 兼容接口），提供：
- 单次对话补全
- 结构化 JSON 输出
- 自动重试 + 超时

API 文档: https://platform.deepseek.com/api-docs
"""

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from app.config import settings


class AIClientError(Exception):
    pass


class AIClient:
    """DeepSeek API 轻量封装，只依赖 httpx（项目已有），不引入额外 SDK。"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        self.api_key = (api_key or settings.deepseek_api_key).strip()
        self.base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self.model = model or settings.deepseek_model
        self.max_tokens = max_tokens or settings.deepseek_max_tokens
        self.temperature = temperature or settings.deepseek_temperature

        if not self.api_key:
            raise AIClientError(
                "DEEPSEEK_API_KEY 未设置。请在 .env 文件中设置 DEEPSEEK_API_KEY=sk-xxx "
                "或设置环境变量。"
            )

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(
        self,
        messages: list[dict],
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> str:
        """同步对话补全，返回 assistant 文本。"""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if system:
            payload["messages"] = [{"role": "system", "content": system}] + payload["messages"]
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                resp = httpx.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=self._headers,
                    json=payload,
                    timeout=timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code >= 500 and attempt < max_retries:
                    time.sleep(2**attempt)
                    continue
                raise AIClientError(f"API 返回 {e.response.status_code}: {e.response.text[:500]}") from e
            except httpx.RequestError as e:
                last_error = e
                if attempt < max_retries:
                    time.sleep(2**attempt)
                    continue
                raise AIClientError(f"API 请求失败: {e}") from e
        raise AIClientError(f"重试 {max_retries} 次后仍失败: {last_error}")

    async def achat(
        self,
        messages: list[dict],
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        timeout: float = 60.0,
        max_retries: int = 2,
    ) -> str:
        """异步对话补全，返回 assistant 文本。"""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if system:
            payload["messages"] = [{"role": "system", "content": system}] + payload["messages"]
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{self.base_url}/v1/chat/completions",
                        headers=self._headers,
                        json=payload,
                        timeout=timeout,
                    )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code >= 500 and attempt < max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise AIClientError(f"API 返回 {e.response.status_code}: {e.response.text[:500]}") from e
            except httpx.RequestError as e:
                last_error = e
                if attempt < max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise AIClientError(f"API 请求失败: {e}") from e
        raise AIClientError(f"重试 {max_retries} 次后仍失败: {last_error}")

    def chat_json(
        self,
        messages: list[dict],
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Any:
        """同步对话，返回解析后的 JSON 对象。"""
        text = self.chat(
            messages, system=system, temperature=temperature,
            max_tokens=max_tokens, json_mode=True, **kwargs,
        )
        return json.loads(text)

    async def achat_json(
        self,
        messages: list[dict],
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Any:
        """异步对话，返回解析后的 JSON 对象。"""
        text = await self.achat(
            messages, system=system, temperature=temperature,
            max_tokens=max_tokens, json_mode=True, **kwargs,
        )
        return json.loads(text)


# ── 流式对话（支持 function calling）──

class StreamChunk:
    """流式响应中的单个 token/事件。"""
    def __init__(self, delta_content: str = "", finish_reason: str | None = None,
                 tool_calls: list[dict] | None = None):
        self.delta_content = delta_content
        self.finish_reason = finish_reason
        self.tool_calls = tool_calls or []

    def __repr__(self):
        return (f"StreamChunk(content={self.delta_content!r}, "
                f"finish={self.finish_reason}, tools={len(self.tool_calls)})")


async def astream_chat(
    messages: list[dict],
    *,
    system: str | None = None,
    tools: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float = 90.0,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
):
    """异步流式对话补全，逐 token yield StreamChunk。

    支持 function calling：当 model 返回 tool_calls 时，
    在 finish_reason="tool_calls" 的 chunk 中携带累积完成的 tool_calls 列表。"""

    key = api_key or settings.deepseek_api_key
    url = (base_url or settings.deepseek_base_url).rstrip("/")
    mdl = model or settings.deepseek_model

    if not key:
        raise AIClientError("DEEPSEEK_API_KEY 未设置")

    _messages = messages
    if system:
        _messages = [{"role": "system", "content": system}] + list(_messages)

    payload: dict[str, Any] = {
        "model": mdl,
        "messages": _messages,
        "temperature": temperature if temperature is not None else 0.3,
        "max_tokens": max_tokens or 2048,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", f"{url}/v1/chat/completions",
                                  headers=headers, json=payload) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise AIClientError(
                    f"API 返回 {response.status_code}: {body.decode()[:500]}")

            tool_call_acc: dict[int, dict] = {}

            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choice = data.get("choices", [{}])[0]
                delta = choice.get("delta", {})
                finish = choice.get("finish_reason")

                # tool_calls delta — 流式累积
                tc_deltas = delta.get("tool_calls")
                if tc_deltas:
                    for tc in tc_deltas:
                        idx = tc.get("index", 0)
                        if idx not in tool_call_acc:
                            tool_call_acc[idx] = {
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        acc = tool_call_acc[idx]
                        if "id" in tc and tc["id"]:
                            acc["id"] = tc["id"]
                        fn = tc.get("function", {})
                        if "name" in fn:
                            acc["function"]["name"] += fn["name"]
                        if "arguments" in fn:
                            acc["function"]["arguments"] += fn["arguments"]

                content = delta.get("content", "") or ""

                if finish == "tool_calls":
                    yield StreamChunk(
                        finish_reason="tool_calls",
                        tool_calls=[tool_call_acc[i] for i in sorted(tool_call_acc)],
                    )
                elif content:
                    yield StreamChunk(delta_content=content, finish_reason=finish)
                elif finish:
                    yield StreamChunk(finish_reason=finish)


# ── 模块级单例 ──

_client: AIClient | None = None


def get_ai_client() -> AIClient:
    global _client
    if _client is None:
        _client = AIClient()
    return _client
