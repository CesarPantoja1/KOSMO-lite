from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from pydantic import BaseModel
from pydantic_ai.agent import Agent
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import Tool
from tenacity import (
    AsyncRetrying,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
)

from kosmo.contracts.auth.context import current_user_id
from kosmo.contracts.llm.ports import LLMResponse, LLMUsage, PromptTemplate, ToolCallRecord
from kosmo.contracts.telemetry import record_llm_tokens

T = TypeVar("T")


def _parse_typed_output[T](text: str, output_type: type[T]) -> T:
    # Intentar extraer JSON incluso si hay texto circundante o markdown
    json_text = _extract_json(text)
    if json_text:
        try:
            return output_type.model_validate_json(json_text)  # type: ignore[reportReturnType]
        except Exception:
            pass

    # Si el texto completo es JSON valido
    if text.startswith("{") or text.startswith("["):
        try:
            return output_type.model_validate_json(text)  # type: ignore[reportReturnType]
        except Exception:
            pass

    # Fallback para modelos de un solo campo (DiscoveryDocument, RequirementsDocument, DiagramSpec)
    if issubclass(output_type, BaseModel):
        field_names = list(output_type.model_fields.keys())
        if len(field_names) == 1:
            return output_type.model_validate({field_names[0]: text})  # type: ignore[reportReturnType]

        primary = field_names[0] if field_names else "content"
        fallback: dict[str, Any] = {name: (text if name == primary else None) for name in field_names}
        return output_type.model_validate(fallback)  # type: ignore[reportReturnType]

    msg = f"No se pudo convertir la respuesta del LLM a {output_type.__name__}"
    raise ValueError(msg)


def _extract_json(text: str) -> str | None:
    """Extrae el primer objeto o array JSON del texto, tolerando markdown y texto circundante."""
    # Quitar fences markdown (```json ... ``` o ``` ... ```)
    if "```json" in text:
        text = text.split("```json", 1)[1]
        if "```" in text:
            text = text.split("```", 1)[0]
    elif text.count("```") >= 2:
        parts = text.split("```")
        text = parts[1]

    # Buscar el primer { o [
    for start_char in ("{", "["):
        idx = text.find(start_char)
        if idx != -1:
            return _extract_balanced(text, idx, start_char)

    return None


def _extract_balanced(text: str, start: int, open_char: str) -> str | None:
    close_char = "}" if open_char == "{" else "]"
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


class PydanticAILLMClient:
    _DEFAULT_TIMEOUT_SECONDS = 120
    _MAX_AGENTS = 32
    _RETRY_ATTEMPTS = 2
    _RETRY_DELAY_SECONDS = 1.0

    def __init__(self, model: Any, retry_wait_seconds: float | None = None) -> None:
        self._model = model
        self._agents: OrderedDict[str, Agent[Any]] = OrderedDict()
        self._retry_wait_seconds = retry_wait_seconds

    async def _run_with_retry(self, coro_fn: Any) -> Any:
        wait_strategy = (
            wait_fixed(self._retry_wait_seconds)
            if self._retry_wait_seconds is not None
            else wait_exponential(multiplier=1, min=1, max=5)
        )
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._RETRY_ATTEMPTS),
            wait=wait_strategy,
            retry=retry_if_not_exception_type(ValueError),
            reraise=True,
        ):
            with attempt:
                return await coro_fn()

    def _get_agent(self, system_prompt: str) -> Agent[Any]:
        agent = self._agents.get(system_prompt)
        if agent is not None:
            self._agents.move_to_end(system_prompt)
            return agent
        agent = Agent(model=self._model, system_prompt=system_prompt)  # type: ignore[reportCallIssue]
        if len(self._agents) >= self._MAX_AGENTS:
            self._agents.popitem(last=False)
        self._agents[system_prompt] = agent
        return agent

    async def complete(
        self,
        prompt: PromptTemplate,
        temperature: float = 0.3,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        agent = self._get_agent(prompt.system_prompt)

        async def _call() -> Any:
            return await asyncio.wait_for(
                agent.run(
                    prompt.user_prompt,
                    model_settings=ModelSettings(temperature=temperature, max_tokens=max_tokens),
                ),
                timeout=self._DEFAULT_TIMEOUT_SECONDS,
            )

        result = await self._run_with_retry(_call)

        usage = result.usage()
        model_name = getattr(result, "model_name", "") or (str(self._model) if hasattr(self, "_model") else "")
        record_llm_tokens(
            tokens=usage.total_tokens,
            model=model_name,
            user_id=current_user_id.get(),
        )
        return LLMResponse(
            text=result.output,
            usage=LLMUsage(
                prompt_tokens=usage.input_tokens,
                completion_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
            ),
            model=getattr(result, "model_name", ""),
        )

    async def complete_typed[T](
        self,
        prompt: PromptTemplate,
        output_type: type[T],
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> T:
        response = await self.complete(prompt=prompt, temperature=temperature, max_tokens=max_tokens)
        return _parse_typed_output(response.text.strip(), output_type)

    async def complete_json(
        self,
        prompt: PromptTemplate,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        return await self.complete(prompt=prompt, temperature=temperature, max_tokens=max_tokens)

    @property
    def supports_native_tools(self) -> bool:
        return True

    async def complete_with_tools(
        self,
        prompt: PromptTemplate,
        tools: list[dict[str, Any]],
        tool_handler: Any,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> tuple[str, list[ToolCallRecord]]:
        records: list[ToolCallRecord] = []

        def _make_tool_fn(name: str):
            async def tool_fn(**kwargs: object) -> str:
                args: dict[str, Any] = dict(kwargs)
                result = await tool_handler(name, args)
                records.append(ToolCallRecord(name=name, args=args, result_snippet=(result or "")[:500]))
                return result

            tool_fn.__name__ = name  # type: ignore[reportFunctionMemberAccess]
            return tool_fn

        pydantic_tools = [
            Tool(
                _make_tool_fn(t["name"]),
                name=t["name"],
                description=t.get("description", ""),
            )
            for t in tools
        ]

        agent: Agent[Any] = Agent(self._model, system_prompt=prompt.system_prompt, tools=pydantic_tools)  # type: ignore[reportCallIssue]

        async def _call() -> Any:
            return await asyncio.wait_for(
                agent.run(
                    prompt.user_prompt,
                    model_settings=ModelSettings(temperature=temperature, max_tokens=max_tokens),
                ),
                timeout=self._DEFAULT_TIMEOUT_SECONDS,
            )

        result = await self._run_with_retry(_call)

        try:
            usage = result.usage()
            model_name = getattr(result, "model_name", "") or (str(self._model) if hasattr(self, "_model") else "")
            record_llm_tokens(
                tokens=usage.total_tokens,
                model=model_name,
                user_id=current_user_id.get(),
            )
        except Exception:
            pass

        return (result.output or "", records)

    @asynccontextmanager  # type: ignore[reportUntypedFunctionDecorator]
    async def stream_typed(
        self,
        prompt: PromptTemplate,
        output_type: type[T],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncIterator[StreamedTypedResult[T]]:
        # Modo texto: sin output_type para que pydantic-ai exponga stream_text()
        # y no envíe tools/tool_choice. El JSON tipado se parsea al final con
        # la misma lógica que complete_typed (ver _parse_typed_output).
        agent = self._get_agent(prompt.system_prompt)
        async with asyncio.timeout(self._DEFAULT_TIMEOUT_SECONDS):
            async with agent.run_stream(  # type: ignore[reportUnknownMemberType]
                prompt.user_prompt,
                model_settings=ModelSettings(temperature=temperature, max_tokens=max_tokens),
            ) as streamed:  # type: ignore[reportUnknownVariableType]
                yield StreamedTypedResult(streamed, output_type)  # type: ignore[reportArgumentType]


class StreamedTypedResult[T]:
    def __init__(self, streamed: Any, output_type: type[T]) -> None:
        self._streamed = streamed
        self._output_type = output_type

    def stream_text(self, *, delta: bool = False) -> AsyncIterator[str]:
        return self._streamed.stream_text(delta=delta)  # type: ignore[reportReturnType]

    async def get_data(self) -> T:
        text = await self._streamed.get_output()  # type: ignore[reportUnknownMemberType]
        return _parse_typed_output(str(text).strip(), self._output_type)
