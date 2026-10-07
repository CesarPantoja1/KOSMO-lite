from __future__ import annotations

from typing import Any

from kosmo.contracts import RespuestaChatLLM
from kosmo.contracts.pipeline.orchestrator_ports import ToolDefinition
from kosmo.contracts.pipeline.phase_outputs import (
    GenerationMetadata,
    ValidationResult,
)


class BaseChatMode:
    @property
    def temperature(self) -> float:
        return 0.4

    @property
    def max_tokens(self) -> int:
        return 8192

    @property
    def output_type(self) -> type[RespuestaChatLLM]:
        return RespuestaChatLLM

    @property
    def available_tools(self) -> list[ToolDefinition]:
        return []

    def validate_output(self, output: Any, *, context: Any = None) -> ValidationResult:  # noqa: ARG002
        errors: list[str] = []

        if isinstance(output, RespuestaChatLLM):
            if not output.content or not output.content.strip():
                errors.append("El campo content no puede estar vacío.")
            if output.change_suggestions is not None:
                for idx, cs in enumerate(output.change_suggestions):
                    prefix = f"change_suggestions[{idx}]."
                    if not cs.section or not cs.section.strip():
                        errors.append(f"{prefix}section no puede estar vacío.")
                    if not cs.description or not cs.description.strip():
                        errors.append(f"{prefix}description no puede estar vacío.")
                    if not cs.diff_before or not cs.diff_before.strip():
                        errors.append(f"{prefix}diff_before no puede estar vacío.")
                    if cs.diff_before.strip() == cs.diff_after.strip():
                        errors.append(
                            f"{prefix}diff_before y diff_after son idénticos; la sugerencia no propone cambios reales."
                        )
        elif isinstance(output, dict):
            errors.append("Formato de salida no reconocido. Se esperaba RespuestaChatLLM.")
        else:
            errors.append("Formato de salida no reconocido.")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
        )

    def build_validation_feedback(self, errors: list[str]) -> str:
        error_list = "\n".join(f"- {e}" for e in errors)
        return (
            "## Feedback de validación\n\n"
            f"La respuesta tiene los siguientes errores:\n\n{error_list}\n\n"
            "Corrige los problemas indicados y genera una nueva respuesta en el formato JSON esperado."
        )

    def build_retry_prompt(
        self,
        original_prompt: str,
        errors: list[str],
        retry_count: int,
    ) -> str:
        error_list = "\n".join(f"- {e}" for e in errors)
        return (
            f"{original_prompt}\n\n"
            f"## Correcciones necesarias (intento {retry_count})\n\n"
            f"Errores detectados:\n{error_list}\n\n"
            "Genera una nueva respuesta corrigiendo exclusivamente estos errores."
        )

    def build_output(
        self,
        raw_output: Any,
        validation_result: ValidationResult,  # noqa: ARG002
        metadata: GenerationMetadata,  # noqa: ARG002
        *,
        context: Any = None,  # noqa: ARG002
    ) -> Any:
        return raw_output
