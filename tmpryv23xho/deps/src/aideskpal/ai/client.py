"""Minimal OpenAI-compatible chat client (DeepSeek, OpenAI, Ollama, ...)."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from aideskpal.config import AIConfig

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    def __init__(self, message: str, *, code: str = "llm_error", retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _endpoint(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise LLMError("AI Base URL 为空", code="missing_base_url")
    if not (base.startswith("http://") or base.startswith("https://")):
        raise LLMError("AI Base URL 必须以 http:// 或 https:// 开头", code="bad_base_url")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _looks_like_json_object(content: str) -> bool:
    content = content.strip()
    return content.startswith("{") and content.endswith("}")


class LLMClient:
    """Synchronous client used from a worker thread; safe to discard after a turn."""

    def __init__(self, config: AIConfig, api_key: str | None = None, *, transport=None) -> None:
        self.config = config
        self.api_key = (config.api_key if api_key is None else api_key).strip()
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "User-Agent": "AIDeskPal-SICK/1.0"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def chat_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        content = self._chat(
            system,
            user,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=True,
        )
        return _extract_json(content)

    def chat_text(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        return self._chat(
            system,
            user,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=False,
        ).strip()

    def ping(self) -> str:
        return self.chat_text(
            "只回复两个字符：OK。不要添加任何其他内容。",
            "ping",
            max_tokens=8,
            temperature=0.0,
        )

    def _chat(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int | None,
        temperature: float | None,
        json_mode: bool,
    ) -> str:
        if not self.api_key:
            raise LLMError("尚未配置 AI API Key", code="missing_key")
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
            "stream": False,
        }
        attempts = 1
        last_error: Exception | None = None
        use_json_mode = json_mode
        for attempt in range(attempts + 1):
            if use_json_mode:
                payload["response_format"] = {"type": "json_object"}
            else:
                payload.pop("response_format", None)
            try:
                with httpx.Client(
                    timeout=httpx.Timeout(float(self.config.timeout_seconds), connect=15.0),
                    transport=self._transport,
                    follow_redirects=True,
                ) as client:
                    response = client.post(
                        _endpoint(self.config.base_url), headers=self._headers(), json=payload
                    )
                if response.status_code == 400 and use_json_mode and attempt == 0:
                    logger.info("Provider rejected JSON mode; retrying in plain mode")
                    use_json_mode = False
                    continue
                if response.status_code == 401:
                    raise LLMError("API Key 无效或已过期", code="unauthorized")
                if response.status_code == 403:
                    raise LLMError("API Key 没有访问该模型的权限", code="forbidden")
                if response.status_code == 404:
                    raise LLMError("接口或模型不存在，请检查 Base URL 和模型名", code="not_found")
                if response.status_code == 429:
                    raise LLMError("请求太频繁，已触发服务商限流", code="rate_limited", retryable=True)
                if response.status_code >= 500:
                    raise LLMError("AI 服务暂时不可用", code="server_error", retryable=True)
                if response.status_code >= 400:
                    detail = ""
                    try:
                        detail = response.json().get("error", {}).get("message", "")
                    except Exception:
                        detail = response.text[:200]
                    raise LLMError(
                        f"AI 请求失败（HTTP {response.status_code}）{('：' + str(detail)) if detail else ''}",
                        code="http_error",
                    )
                data = response.json()
                choices = data.get("choices") or []
                if not choices:
                    raise LLMError("AI 返回了空结果", code="empty_response")
                message = choices[0].get("message") or {}
                content = message.get("content")
                if isinstance(content, list):
                    content = "".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in content
                    )
                if not isinstance(content, str) or not content.strip():
                    raise LLMError("AI 没有返回文本内容", code="empty_content")
                return content
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(0.7)
                    continue
                raise LLMError(f"连接 AI 服务失败：{type(exc).__name__}", code="network") from exc
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(0.7)
                    continue
                raise LLMError(f"AI 网络错误：{type(exc).__name__}", code="network") from exc
        raise LLMError(f"AI 请求失败：{last_error}", code="network")


def _extract_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        snippet = text[start : end + 1]
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            raise LLMError(f"AI 返回的 JSON 无法解析：{exc}", code="bad_json") from exc
    raise LLMError("AI 没有返回合法的 JSON 对象", code="bad_json")
