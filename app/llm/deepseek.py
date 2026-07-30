"""DeepSeek OpenAI-compatible chat completion adapter."""

from __future__ import annotations

import json
import logging
from typing import Generator, Optional

import httpx

from app.llm.loader import LLMGenerationError, LLMLoader
from app.tools.types import ErrorCode

logger = logging.getLogger(__name__)


class DeepSeekLLM:
    """Expose DeepSeek through the same generate/stream contract as LLMLoader."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int = 1024,
        temperature: float = 0.6,
        top_p: float = 0.95,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p

    def _validate_configuration(self) -> None:
        if not self.api_key:
            raise LLMGenerationError(
                ErrorCode.CONFIG_MISSING,
                "DeepSeek is not configured. Set DEEPSEEK_API_KEY (or the Windows compatibility variable DeepSeek) and retry.",
            )

    def _payload(
        self,
        prompt: str,
        *,
        stream: bool,
        max_new_tokens: Optional[int],
        temperature: Optional[float],
        top_p: Optional[float],
    ) -> dict:
        LLMLoader._validate_prompt(prompt)
        self._validate_configuration()
        tokens = self.max_tokens if max_new_tokens is None else max_new_tokens
        if tokens <= 0:
            raise LLMGenerationError(
                ErrorCode.INVALID_PARAM,
                "The requested generation length must be positive.",
            )
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": tokens,
            "temperature": self.temperature if temperature is None else temperature,
            "top_p": self.top_p if top_p is None else top_p,
            "stream": stream,
            "thinking": {"type": "disabled"},
        }

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_transport_error(exc: Exception) -> None:
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status in {401, 403}:
                raise LLMGenerationError(
                    ErrorCode.PERMISSION_DENIED,
                    "DeepSeek rejected the configured API credentials.",
                ) from exc
            logger.error("DeepSeek returned HTTP %s", status)
        elif isinstance(exc, httpx.TimeoutException):
            logger.error("DeepSeek request timed out")
        else:
            logger.error("DeepSeek request failed: %s", type(exc).__name__)
        raise LLMGenerationError(
            ErrorCode.NETWORK_ERROR,
            "The DeepSeek service is temporarily unavailable.",
        ) from exc

    def generate(
        self,
        prompt: str,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> str:
        payload = self._payload(
            prompt,
            stream=False,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers,
                    json=payload,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            if isinstance(exc, httpx.HTTPError):
                self._raise_transport_error(exc)
            logger.error("DeepSeek returned an invalid completion payload")
            raise LLMGenerationError(
                ErrorCode.INTERNAL_ERROR,
                "DeepSeek returned an invalid response.",
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMGenerationError(
                ErrorCode.INTERNAL_ERROR,
                "DeepSeek returned an empty response.",
            )
        return content.strip()

    def generate_stream(
        self,
        prompt: str,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
    ) -> Generator[str, None, None]:
        payload = self._payload(
            prompt,
            stream=True,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
        )
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers,
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        if not data:
                            continue
                        event = json.loads(data)
                        content = event["choices"][0].get("delta", {}).get("content")
                        if content:
                            yield str(content)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            if isinstance(exc, httpx.HTTPError):
                self._raise_transport_error(exc)
            logger.error("DeepSeek returned an invalid streaming payload")
            raise LLMGenerationError(
                ErrorCode.INTERNAL_ERROR,
                "DeepSeek returned an invalid streaming response.",
            ) from exc
