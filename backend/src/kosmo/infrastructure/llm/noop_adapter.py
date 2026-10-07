from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from kosmo.contracts.llm.ports import LLMResponse, LLMUsage, PromptTemplate, ToolCallRecord

_DISCOVERY_DOC = "\n\n".join(
    f"## {section}\n\nContenido de ejemplo para la sección de {section.lower()}."
    for section in [
        "Visión del producto",
        "Espacio del problema",
        "Actores",
        "Propuesta de valor",
        "Metas del producto",
        "Reglas de negocio",
        "Alcance",
    ]
)

_FEATURES = [
    {
        "number": i,
        "title": f"Característica {i}",
        "description": f"Descripción 4W de la característica {i}",
        "slug": f"característica-{i}",
        "origin": (
            f"Se deriva de las metas del producto. Se traza a Metas del "
            f"producto y Reglas de negocio. Caracteristica {i}."
        ),
    }
    for i in range(1, 6)
]

_REQUIREMENTS = [
    {
        "code": "REQ-1.1",
        "pattern": "ubiquitous",
        "statement": "El sistema shall gestionar los datos de forma segura",
        "origin": "Requisito fundamental de seguridad. Se deriva de C01 y Reglas de negocio.",
        "acceptance_criteria": [
            {
                "scenario": "Acceso autenticado a los datos",
                "given": "un usuario autenticado",
                "when": "accede a sus datos",
                "then": "los datos se muestran correctamente",
            },
            {
                "scenario": "Acceso no autenticado",
                "given": "un usuario no autenticado",
                "when": "intenta acceder a los datos",
                "then": "recibe un error de autenticación",
            },
        ],
    }
]

_NOOP_RESPONSE = json.dumps(
    {
        "document": _DISCOVERY_DOC,
        "features": _FEATURES,
        "requirements": _REQUIREMENTS,
    }
)


class NoopLLMClient:
    """Adapter de desarrollo que retorna datos de ejemplo para todas las fases.

    Devuelve siempre la misma respuesta combinada que incluye ``document``,
    ``features`` y ``requirements``. Cada ``PhaseMode.validate_output``
    extrae la clave que necesita, haciendo que el adapter funcione
    uniformemente para discovery, características y requisitos sin
    lógica de detección de fase.
    """

    async def complete(  # noqa: ARG002
        self,
        prompt: PromptTemplate,  # noqa: ARG002
        temperature: float = 0.3,  # noqa: ARG002
        max_tokens: int = 8192,  # noqa: ARG002
    ) -> LLMResponse:
        return LLMResponse(
            text=_NOOP_RESPONSE,
            usage=LLMUsage(prompt_tokens=10, completion_tokens=100, total_tokens=110),
            model="noop",
        )

    async def complete_json(
        self,
        prompt: PromptTemplate,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        return await self.complete(prompt=prompt, temperature=temperature, max_tokens=max_tokens)

    async def complete_typed[T](
        self,
        prompt: PromptTemplate,
        output_type: type[T],
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ) -> T:
        response = await self.complete(prompt, temperature=temperature, max_tokens=max_tokens)
        if output_type is str:
            return response.text  # type: ignore[return-value]
        if hasattr(output_type, "model_validate"):
            try:
                return output_type.model_validate(json.loads(response.text))  # type: ignore[reportAttributeAccessIssue]
            except Exception:
                field_names = list(getattr(output_type, "model_fields", {}).keys())
                if field_names:
                    return output_type.model_validate({field_names[0]: response.text})  # type: ignore[reportAttributeAccessIssue]
                return output_type.model_validate({})  # type: ignore[reportAttributeAccessIssue]
        return response.text  # type: ignore[return-value]

    @property
    def supports_native_tools(self) -> bool:
        return False

    async def complete_with_tools(  # noqa: ARG002
        self,
        prompt: PromptTemplate,  # noqa: ARG002
        tools: list[dict[str, object]],  # noqa: ARG002
        tool_handler: object,  # noqa: ARG002
        temperature: float = 0.1,  # noqa: ARG002
        max_tokens: int = 2000,  # noqa: ARG002
    ) -> tuple[str, list[ToolCallRecord]]:
        return ("", [])

    @asynccontextmanager
    async def stream_typed[T](
        self,
        prompt: PromptTemplate,
        output_type: type[T],
        temperature: float = 0.1,  # noqa: ARG002
        max_tokens: int = 8192,  # noqa: ARG002
    ) -> AsyncGenerator[Any]:
        class _NoopStreamed:
            def __init__(self, data: T):
                self._data = data

            async def stream_text(self, *, delta: bool = False) -> AsyncIterator[str]:  # noqa: ARG002
                content = getattr(self._data, "content", None)
                if isinstance(content, str):
                    yield content
                else:
                    yield str(self._data)

            async def get_data(self) -> T:
                return self._data

        typed_res = await self.complete_typed(prompt, output_type=output_type)
        yield _NoopStreamed(typed_res)
