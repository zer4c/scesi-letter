from dataclasses import dataclass
from typing import Any

import httpx
from groq import AsyncGroq

from app.core.config import Settings


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class Completion:
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    usage_input_tokens: int | None
    usage_output_tokens: int | None
    headers: dict[str, str]


class CompletionAdapter:
    async def complete(self, **kwargs: Any) -> Completion:
        raise NotImplementedError


class GroqCompletionAdapter(CompletionAdapter):
    def __init__(self, settings: Settings) -> None:
        if settings.GROQ_API_KEY is None:
            raise RuntimeError("Groq is not configured")
        self._client = AsyncGroq(
            api_key=settings.GROQ_API_KEY.get_secret_value(),
            timeout=httpx.Timeout(settings.LLM_REQUEST_TIMEOUT_SECONDS),
            max_retries=0,
        )
        self._settings = settings

    async def complete(self, *, messages, tools=None, json_output=False) -> Completion:
        response = await self._client.chat.completions.create(
            model=self._settings.GROQ_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto" if tools else "none",
            parallel_tool_calls=False,
            max_tokens=self._settings.LLM_MAX_OUTPUT_TOKENS,
            response_format={"type": "json_object"} if json_output else None,
            reasoning_effort=self._settings.GROQ_REASONING_EFFORT,
            include_reasoning=False,
        )
        message = response.choices[0].message
        calls = tuple(
            ToolCall(
                id=call.id, name=call.function.name, arguments=call.function.arguments
            )
            for call in (message.tool_calls or [])
        )
        usage = response.usage
        headers = {
            str(key).casefold(): str(value)
            for key, value in getattr(response, "_headers", {}).items()
        }
        return Completion(
            content=message.content,
            tool_calls=calls,
            usage_input_tokens=getattr(usage, "prompt_tokens", None),
            usage_output_tokens=getattr(usage, "completion_tokens", None),
            headers=headers,
        )

    async def close(self) -> None:
        await self._client.close()
