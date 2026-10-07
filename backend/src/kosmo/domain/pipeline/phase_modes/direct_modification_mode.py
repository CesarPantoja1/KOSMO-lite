from __future__ import annotations

from typing import Any

from kosmo.contracts.pipeline.phase_contexts import DirectModificationContext
from kosmo.contracts.pipeline.phase_outputs import (
    DirectModificationResult,
    GenerationMetadata,
    ValidationResult,
)
from kosmo.contracts.sdd.document import SpecPhase

_DIRECT_MODIFICATION_SYSTEM_PROMPT = """Eres un asistente que modifica documentos de especificacion de software.

Recibiras el contenido actual del documento, su tipo y la instruccion del usuario.
Debes aplicar el cambio directamente sobre el documento y devolver el resultado en formato JSON.
No propones sugerencias: aplicas el cambio inmediatamente sobre el documento completo.

Reglas:
1. Si la instruccion es clara y especifica que cambiar y en que seccion, aplica el cambio.
2. Si la instruccion es ambigua (como "cambia eso" sin especificar seccion ni contenido),
   responde con applied=false y un mensaje pidiendo clarificacion.
3. modified_document debe contener el documento completo actualizado.
4. modified_section debe contener el nombre de la seccion modificada.
5. Manten el resto del documento intacto: solo modifica la seccion indicada.

Formato de salida (JSON):
{
  "applied": true,
  "modified_document": "<documento completo actualizado>",
  "modified_section": "<nombre de la seccion modificada>",
  "change_description": "<descripcion breve del cambio>",
  "clarification_message": ""
}
"""


class DirectModificationMode:
    """Modo que aplica modificaciones directas a documentos sin fase de plan."""

    def __init__(self, phase_name: SpecPhase = SpecPhase.DESCUBRIMIENTO) -> None:
        self._phase_name = phase_name

    @property
    def phase_name(self) -> SpecPhase:
        return self._phase_name

    @property
    def system_prompt(self) -> str:
        return _DIRECT_MODIFICATION_SYSTEM_PROMPT

    @property
    def temperature(self) -> float:
        return 0.1

    @property
    def max_tokens(self) -> int:
        return 8192

    @property
    def output_type(self) -> type[DirectModificationResult]:
        return DirectModificationResult

    def build_user_prompt(self, context: DirectModificationContext) -> str:
        parts = [
            "## Documento actual",
            context.current_document,
            "",
            f"## Tipo de documento: {context.document_type.value}",
            "",
            "## Instruccion del usuario",
            context.instruction,
        ]
        return "\n".join(parts)

    def validate_output(self, output: Any, *, context: Any = None) -> ValidationResult:  # noqa: ARG002
        errors: list[str] = []

        if isinstance(output, DirectModificationResult):
            if output.applied and not output.modified_document.strip():
                errors.append("El campo modified_document no puede estar vacío cuando applied=true.")
            if output.applied and not output.modified_section.strip():
                errors.append("El campo modified_section no puede estar vacío cuando applied=true.")
            if not output.applied and not output.clarification_message.strip():
                errors.append("El campo clarification_message no puede estar vacío cuando applied=false.")
        else:
            errors.append("Formato de salida no reconocido. Se esperaba DirectModificationResult.")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
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

    def build_validation_feedback(self, errors: list[str]) -> str:
        error_list = "\n".join(f"- {e}" for e in errors)
        return (
            "## Feedback de validación\n\n"
            f"La respuesta tiene los siguientes errores:\n\n{error_list}\n\n"
            "Corrige los problemas indicados y genera una nueva respuesta en el formato JSON esperado."
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
