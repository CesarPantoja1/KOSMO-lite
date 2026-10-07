from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel

from kosmo.contracts.pipeline.orchestrator_ports import ToolDefinition
from kosmo.contracts.pipeline.phase_contexts import RequirementsRefinePhaseContext
from kosmo.contracts.pipeline.phase_outputs import (
    EARSPhaseOutput,
    GenerationMetadata,
    ValidationResult,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import FeatureId
from kosmo.domain.pipeline._dict_utils import extract_requirements_list, requirements_to_markdown
from kosmo.domain.pipeline.phase_validators.requirements_refine_validator import (
    validate_refine_input_exists,
)

_REQUIREMENTS_REFINE_SYSTEM_PROMPT = """Eres un editor de documentos experto. Recibes un documento de requisitos
en formato Markdown y una instrucción de refinamiento del usuario.

## Tu tarea

Eres un editor quirúrgico de texto. El documento de entrada es la fuente de verdad.
Debes devolver el documento COMPLETO con ÚNICAMENTE los cambios solicitados aplicados.
Cada carácter que no fue mencionado en la instrucción debe permanecer IDÉNTICO al
original: incluyendo espacios, saltos de línea, puntuación y formato markdown.

## Reglas estrictas

1. Si la instrucción menciona un requisito específico (por código REQ-X.Y o por su
   contenido), modifica EXACTAMENTE ese requisito y nada más.
2. Si la instrucción pide eliminar algo, solo elimínalo. No toques el resto.
3. Si la instrucción pide agregar algo, agrégalo sin alterar los existentes.
4. PROHIBIDO reformatear, reescribir o "mejorar" requisitos no mencionados.
5. PROHIBIDO cambiar numeración, puntuación, formato o estilo de partes no afectadas.
6. PROHIBIDO agregar criterios de aceptación, escenarios o cualquier contenido
   que el usuario no haya solicitado explícitamente.
7. PROHIBIDO eliminar o modificar los separadores `---` entre requisitos a menos
   que la instrucción lo pida.
8. Si no entiendes la instrucción, devuelve el documento SIN CAMBIOS.
9. No añadas texto introductorio, explicaciones ni comentarios fuera del documento.

## Formato de salida

Responde en el campo `output` del JSON de respuesta final con el documento
editado. El valor de `output` debe ser el contenido que aparece después del
marcador `---` en el prompt del usuario (la sección "DOCUMENTO A EDITAR").
No incluyas el contexto, las instrucciones ni los marcadores `---` en el
documento. El documento editado debe empezar directamente con `### REQ-X.Y`,
sin texto antes ni después.

**IMPORTANTE SOBRE EL FORMATO JSON:** El campo `output` es una cadena JSON.
Escapa TODOS los saltos de línea como \\n y TODAS las comillas dobles como
\\". No uses saltos de línea reales dentro de la cadena JSON. Ejemplo:
{"reasoning": "...", "final": true, "output": "### REQ-1.1 Titulo\\n\\nUbicuo\\n\\nEl sistema debe..."}
"""


class RequirementsRefineMode:
    @property
    def phase_name(self) -> SpecPhase:
        return SpecPhase.REQUISITOS

    @property
    def temperature(self) -> float:
        return 0.3

    @property
    def max_tokens(self) -> int:
        return 8192

    @property
    def output_type(self) -> type[BaseModel]:
        from kosmo.contracts.pipeline.phase_outputs import RequirementsDocument

        return RequirementsDocument

    @property
    def system_prompt(self) -> str:
        return _REQUIREMENTS_REFINE_SYSTEM_PROMPT

    @property
    def available_tools(self) -> list[ToolDefinition]:
        return []

    def build_user_prompt(self, context: RequirementsRefinePhaseContext) -> str:

        val = validate_refine_input_exists(context.current_requirements_markdown)
        if not val.is_valid:
            raise ValueError(val.errors[0])

        parts = ["## Contexto (NO incluir en tu respuesta)\n"]
        parts.append(f"- **Código**: {context.feature.display_id}")
        parts.append(f"- **Título**: {context.feature.title}\n")

        parts.append("---\n")
        parts.append("## DOCUMENTO A EDITAR (comienza aquí)\n")
        parts.append(context.current_requirements_markdown)

        parts.append("\n---\n")
        parts.append("## Instrucción del usuario\n")
        parts.append(context.user_instructions)

        if context.user_preferences:
            prefs = "\n".join(f"- {p.rule_text}" for p in context.user_preferences)
            parts.append(f"\n## Preferencias del usuario\n\n{prefs}")

        return "\n".join(parts)

    def validate_output(self, output: Any, *, context: Any = None) -> ValidationResult:  # noqa: ARG002
        from kosmo.contracts.pipeline.phase_outputs import RequirementsDocument

        text = ""
        if isinstance(output, RequirementsDocument):
            text = output.requirements_markdown.strip()
        elif isinstance(output, str):
            text = output.strip()
        elif isinstance(output, dict):
            as_dict = cast(dict[str, object], output)
            text = str(as_dict.get("output", "")).strip()

        if not text:
            return ValidationResult(is_valid=False, errors=["El output está vacío"])

        if text.startswith("{") or text.startswith("["):
            return ValidationResult(
                is_valid=False,
                errors=["El output parece JSON crudo en lugar de markdown de requisitos"],
            )

        if "### REQ-" not in text:
            return ValidationResult(
                is_valid=False,
                errors=["El output no contiene requisitos en formato esperado (### REQ-...)"],
            )

        return ValidationResult(is_valid=True)

    def build_validation_feedback(self, errors: list[str]) -> str:
        error_list = "\n".join(f"- {e}" for e in errors)
        return (
            "## Feedback de validacion\n\n"
            f"El documento tiene los siguientes errores:\n\n{error_list}\n\n"
            "Corrige UNICAMENTE estos problemas puntuales en el documento. "
            "NO modifiques, reescribas ni reformatees el resto del contenido "
            "que ya esta correcto. Aplica cambios quirurgicos, especificos y "
            "localizados."
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
            f"Los requisitos generados tienen los siguientes problemas:\n\n"
            f"{error_list}\n\n"
            f"Corrige estos problemas y genera los requisitos nuevamente."
        )

    def build_output(
        self,
        raw_output: Any,
        validation_result: ValidationResult,
        metadata: GenerationMetadata,
        *,
        context: Any = None,
    ) -> EARSPhaseOutput:
        from kosmo.contracts.pipeline.phase_contexts import RequirementsRefinePhaseContext
        from kosmo.contracts.pipeline.phase_outputs import RequirementsDocument

        feature_id: FeatureId = FeatureId("")
        feature_number: int = 0
        if isinstance(context, RequirementsRefinePhaseContext):
            feature_id = context.feature.id
            feature_number = context.feature_number

        if isinstance(raw_output, RequirementsDocument):
            raw_output = raw_output.requirements_markdown
        markdown_text = ""

        if isinstance(raw_output, str):
            markdown_text = raw_output.strip()
        elif isinstance(raw_output, dict):
            output_value: object = raw_output.get("output", "")  # type: ignore[reportUnknownVariableType]
            if isinstance(output_value, str) and output_value.strip():
                markdown_text = output_value.strip()

        if markdown_text:
            return EARSPhaseOutput(
                feature_id=feature_id,
                feature_number=feature_number,
                requirements=[],
                requirements_markdown=markdown_text,
                validation_result=validation_result,
                generation_metadata=metadata,
            )

        from kosmo.contracts.sdd.document import AcceptanceCriterion
        from kosmo.contracts.sdd.ears import EARSPattern, EARSRequirement
        from kosmo.contracts.sdd.ids import RequirementId
        from kosmo.domain.sdd.id_generator import IdGenerator

        reqs_data = extract_requirements_list(raw_output)
        requirements: list[EARSRequirement] = []

        for i, item in enumerate(reqs_data, start=1):
            pattern_str = item.get("pattern", "Ubicuo")  # type: ignore[reportUnknownMemberType]
            try:
                pattern = EARSPattern(str(pattern_str))  # type: ignore[reportUnknownArgumentType]
            except ValueError:
                pattern = EARSPattern.ubiquitous

            raw_ac = item.get("acceptance_criteria", [])
            criteria: list[AcceptanceCriterion] = []
            if isinstance(raw_ac, list):
                for ac in cast(list[object], raw_ac):
                    if isinstance(ac, dict):
                        ac_dict = cast(dict[str, object], ac)
                        criteria.append(
                            AcceptanceCriterion(
                                scenario=str(ac_dict.get("scenario", "")),
                                given=str(ac_dict.get("given", "")),
                                when=str(ac_dict.get("when", "")),
                                then=str(ac_dict.get("then", "")),
                            )
                        )

            requirements.append(
                EARSRequirement(
                    id=RequirementId(IdGenerator.generate("requirement")),
                    feature_id=feature_id,
                    feature_number=feature_number,
                    requirement_number=i,
                    title=str(item.get("title", "")),  # type: ignore[reportUnknownArgumentType]
                    pattern=pattern,
                    statement=str(item.get("statement", "")),  # type: ignore[reportUnknownArgumentType]
                    origin=str(item.get("origin", "")),  # type: ignore[reportUnknownArgumentType]
                    acceptance_criteria=criteria,
                )
            )

        markdown_str = requirements_to_markdown(requirements)

        return EARSPhaseOutput(
            feature_id=feature_id,
            feature_number=feature_number,
            requirements=requirements,
            requirements_markdown=markdown_str,
            validation_result=validation_result,
            generation_metadata=metadata,
        )
