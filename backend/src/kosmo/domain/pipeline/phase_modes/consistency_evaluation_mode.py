from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from kosmo.contracts.pipeline.consistency_phase_context import ConsistencyPhaseContext
from kosmo.contracts.pipeline.orchestrator_ports import ToolDefinition
from kosmo.contracts.pipeline.phase_outputs import (
    ConsistencyCorrection,
    ConsistencyDetectionReport,
    GenerationMetadata,
    ValidationResult,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.domain.sdd.validators.activity_diagram_validator import (
    validate_activity_diagram_syntax,
    wrap_diagram_fragment,
)

# ═══════════════════════════════════════════════════════════════════
# Bloques compartidos del builder de prompts
# ═══════════════════════════════════════════════════════════════════

_ROLE = "Eres un analista experto en trazabilidad de requisitos de software. "

_FIDELITY_RULES = (
    "## REGLAS DE ANALISIS\n\n"
    "1. LEE el documento fuente COMPLETO y cada artefacto destino.\n"
    "2. Para cada artefacto, determina una UNICA accion:\n"
    '   - "update": el cambio afecta el contenido del artefacto.\n'
    '   - "delete": el concepto del que depende el artefacto fue ELIMINADO. '
    "El artefacto ya no tiene razon de existir.\n"
    '   - "keep": el artefacto NO esta relacionado con ningun cambio. '
    "NO lo incluyas en la respuesta.\n\n"
    "3. SOLO DETECTAS el impacto: NO debes generar ni sugerir el texto "
    "corregido. Otra fase se encarga de redactar la correccion exacta.\n"
    "4. ANALISIS SEMANTICO: no busques coincidencia literal entre el documento "
    "fuente y los artefactos. Evalua el significado.\n"
    "5. CAMBIOS COSMETICOS (ortografia, formato) que no alteran el significado "
    "NO generan impacto.\n"
    "6. Si el cambio modifica NOMENCLATURA o TERMINOLOGIA (nombres de actores, "
    "roles, entidades, conceptos del dominio), TODOS los artefactos que "
    "mencionen el termino anterior deben marcarse como 'update' con el nuevo "
    "termino. Este es un cambio semantico, no cosmetico.\n"
    "7. Si el cambio modifica una REGLA DE NEGOCIO o ALCANCE FUNCIONAL, TODOS "
    "los artefactos que implementan esa regla estan afectados.\n"
    "8. Prohibido usar el caracter guion largo. Usa punto, coma o dos puntos.\n"
    "9. ORTOGRAFIA: escribe en español correcto. Usa TODAS las tildes "
    "(á, é, í, ó, ú), dieresis (ü) y eñes (ñ). Revisa especialmente: "
    "descripción, característica, término, análisis, único, especifico, "
    "después, automático, método, código, acción, sección, razón, lógica, "
    "ortografía, número, género, ámbito, artículo.\n"
    "10. Usa signos de puntuacion correctos: punto final en cada oracion, "
    "comas donde corresponda, mayuscula inicial.\n\n"
)

_DIRECTION_DOWNSTREAM = {
    "Descubrimiento": (
        "Tu tarea es analizar CAMBIOS aplicados al documento de Descubrimiento "
        "y determinar si los artefactos de fases posteriores necesitan actualizarse "
        "para mantenerse fieles a la vision, alcance y reglas de negocio.\n\n"
    ),
    "Caracteristicas": (
        "Tu tarea es analizar CAMBIOS aplicados a las Caracteristicas y determinar "
        "si los artefactos de fases posteriores necesitan actualizarse.\n\n"
    ),
    "Requisitos": (
        "Tu tarea es analizar CAMBIOS aplicados a los Requisitos EARS y determinar "
        "si los artefactos de fases posteriores necesitan actualizarse.\n\n"
    ),
}

_DIRECTION_UPSTREAM = {
    "Caracteristicas": (
        "Tu tarea es analizar CAMBIOS aplicados a las Caracteristicas y determinar "
        "si contradicen la Vision, Alcance o reglas del documento de Descubrimiento. "
        "Evalua SOLO a nivel de negocio y alcance. NO documentes detalles tecnicos "
        "o de UI en el Descubrimiento. La accion 'delete' NO aplica: el Descubrimiento "
        "nunca debe eliminarse por cambios en caracteristicas.\n\n"
    ),
    "Requisitos": (
        "Tu tarea es analizar CAMBIOS aplicados a los Requisitos EARS y determinar "
        "si contradicen la Vision, Alcance o reglas del documento de Descubrimiento. "
        "Los requisitos refinan el comportamiento: solo un cambio de regla de negocio "
        "fundamental justifica modificar el Descubrimiento. NO documentes detalles "
        "tecnicos o sintaxis EARS en el Descubrimiento. La accion 'delete' NO aplica: "
        "el Descubrimiento nunca debe eliminarse por cambios en requisitos.\n\n"
    ),
    "RequisitosFeatures": (
        "Tu tarea es analizar CAMBIOS aplicados a los Requisitos EARS de una "
        "caracteristica y determinar si modifican el alcance, intencion o "
        "comportamiento esperado de la CARACTERISTICA PADRE.\n\n"
        "Para la caracteristica padre, determina una UNICA accion:\n"
        '   - "update": el cambio en los requisitos modifica el alcance, titulo '
        "o descripcion de la caracteristica (ej: un requisito agrega una "
        "funcionalidad no contemplada). DEBES sugerir el texto corregido.\n"
        '   - "keep": los cambios son detalles de implementacion que NO afectan '
        "el alcance. NO lo incluyas.\n\n"
    ),
}

_LEVEL_RULES_FEATURES = (
    "## NIVEL DE ANALISIS: Caracteristicas\n\n"
    "Las caracteristicas representan capacidades del producto. El campo 'Origen' "
    "de cada caracteristica contiene la cadena de derivacion declarada "
    "(ej: 'Se deriva de C01 y Reglas de negocio'). Usala como evidencia primaria "
    "de trazabilidad ANTES de inferir por semantica.\n\n"
)

_LEVEL_RULES_REQUIREMENTS = (
    "## NIVEL DE ANALISIS: Requisitos EARS\n\n"
    "Los requisitos representan comportamientos especificos en formato EARS. "
    "Identifica los codigos REQ-X.Y afectados e incluyelos en la rationale. "
    "Si un requisito cambia 'procesar pagos con tarjeta' por 'procesar pagos "
    "con cualquier metodo', la caracteristica padre amplio su alcance. "
    "Si el cambio solo refina criterios de aceptacion sin alterar la intencion "
    "general, la caracteristica NO esta afectada.\n\n"
)

_LEVEL_RULES_REQUIREMENTS_DOWNSTREAM = (
    "## NIVEL DE ANALISIS: Requisitos EARS (Destino)\n\n"
    "Los requisitos representan comportamientos especificos del sistema en formato EARS. "
    "1. CAMBIO O ELIMINACION DE ACTORES O ROLES: Si en el documento fuente se elimina, "
    "renombra o modifica un actor o rol (ej: se elimina 'colaborador de tienda', 'cajero', "
    "'administrador'), TODOS los requisitos EARS que mencionen o dependan de dicho actor "
    "en sus disparadores o condiciones (ej: 'CUANDO el colaborador de tienda confirma...', "
    "'MIENTRAS el colaborador...') o en sus criterios de aceptacion DEBEN marcarse como 'update' "
    "para adaptar el actor o disparador del evento, o 'delete' si el requisito completo "
    "pierde razon de ser.\n"
    "2. CAMBIO DE REGLAS DE NEGOCIO O CONDICIONES: Si una regla de negocio o condicion cambia en "
    "la fuente, identifica los codigos REQ-X.Y afectados e incluyelos en la rationale.\n"
    "3. El artifact_id en la respuesta DEBE ser el ID de la feature a la que pertenecen los "
    "requisitos afectados (tal como aparece en la lista de artefactos).\n\n"
)

_REQUIREMENTS_DOWNSTREAM_EXAMPLES = (
    "## EJEMPLOS DE EVALUACION DE REQUISITOS EARS\n\n"
    "Ejemplo 1 — Eliminacion o cambio de actor:\n"
    '  Cambio: se elimina el actor "Colaborador de tienda" del documento de Descubrimiento\n'
    "  Artefacto: Requisitos de Gestion de pedidos (id: feat_01...) con "
    '"REQ-6.1 Descuento automatico de stock: CUANDO el colaborador de tienda confirma un pedido..."\n'
    '  → accion: "update", artifact_id: "feat_01...", '
    "razon: \"El actor 'colaborador de tienda' fue eliminado del alcance; REQ-6.1 debe actualizar el actor.\"\n\n"
    "Ejemplo 2 — Modificacion de regla de negocio:\n"
    '  Cambio: "el descuento maximo pasa de 10% a 15%"\n'
    '  Artefacto: Requisitos de Promociones (id: feat_02...) con "REQ-2.1 Aplicar descuento..."\n'
    '  → accion: "update", artifact_id: "feat_02...", '
    'razon: "REQ-2.1 debe actualizar el porcentaje maximo de descuento a 15%."\n\n'
    "Ejemplo 3 — Eliminacion de capacidad:\n"
    "  Cambio: se elimina el modulo de facturacion electronica\n"
    "  Artefacto: Requisitos de Facturacion (id: feat_03...)\n"
    '  → accion: "delete", artifact_id: "feat_03...", '
    'razon: "La funcionalidad de facturacion electronica fue eliminada."\n\n'
)

_LEVEL_RULES_MODEL = (
    "## NIVEL DE ANALISIS: Diagramas de Actividad\n\n"
    "Los diagramas representan flujos de proceso (actores, pasos, decisiones). "
    "Analiza a nivel de flujo, no de formato PlantUML. Si cambia el numero de "
    "pasos o la logica de un proceso, el diagrama esta afectado. Si el cambio "
    "es cosmetico o solo afecta criterios de aceptacion, el diagrama NO esta "
    "afectado.\n\n"
)

_LEVEL_RULES_DISCOVERY = (
    "## NIVEL DE ANALISIS: Descubrimiento\n\n"
    "El Descubrimiento define vision, alcance y reglas de negocio. Evalua "
    "si el cambio contradice o amplia el alcance declarado. Solo 'update' "
    "es valido para este artefacto.\n\n"
)


def _output_schema(target_artifact: str) -> str:
    schemas = {
        "Feature": (
            '    {{"artifact_id": "<id exacto de la caracteristica>", '
            '"action": "update" | "delete", '
            '"rationale": "<explicacion en español>", '
            '"suggested_field": "<title o description>"}}'
        ),
        "EARSRequirement": (
            '    {{"artifact_id": "<id exacto de la feature, tal como aparece en la lista>", '
            '"action": "update" | "delete", '
            '"rationale": "<explicacion. Incluye codigos REQ-X.Y afectados>"}}'
        ),
        "ActivityDiagram": (
            '    {{"artifact_id": "<id exacto de la feature>", '
            '"action": "update" | "delete", '
            '"rationale": "<explicacion en español>"}}'
        ),
        "DiscoveryDocument": (
            '    {{"artifact_id": "<id EXACTO del documento, tal como aparece en la lista de artefactos>", '
            '"action": "update", '
            '"rationale": "<explicacion en español>", '
            '"suggested_field": "<titulo de la seccion: ## Vision, ## Alcance, etc.>"}}'
        ),
    }
    return schemas.get(target_artifact, schemas["Feature"])


_EMPTY_FALLBACK = (
    "Si ningun artefacto esta afectado, devuelve: "
    '{"actions": [], "overall_rationale": "Ningun artefacto requiere cambios."}'
)


def build_consistency_prompt(
    direction: str,
    source_label: str,
    target_artifact: str,
    extra_rules: str = "",
) -> str:
    if direction == "downstream":
        task = _DIRECTION_DOWNSTREAM.get(source_label, _DIRECTION_DOWNSTREAM["Descubrimiento"])
    elif direction == "upstream_features":
        task = _DIRECTION_UPSTREAM.get("Caracteristicas", "")
    elif direction == "upstream_requirements":
        task = _DIRECTION_UPSTREAM.get("Requisitos", "")
    elif direction == "upstream_requirements_features":
        task = _DIRECTION_UPSTREAM.get("RequisitosFeatures", "")
    else:
        task = ""
    schema = _output_schema(target_artifact)
    return (
        _ROLE
        + task
        + _FIDELITY_RULES
        + extra_rules
        + "## FORMATO DE SALIDA (JSON estricto)\n\n"
        + "Responde UNICAMENTE con el siguiente JSON, sin markdown ni texto adicional:\n"
        + "{\n"
        + '  "actions": [\n'
        + schema
        + "\n"
        + "  ],\n"
        + '  "overall_rationale": "<resumen general del analisis en español>"\n'
        + "}\n\n"
        + _EMPTY_FALLBACK
    )


# ═══════════════════════════════════════════════════════════════════
# Prompts generados por el builder (1 variable por skill registrado)
# ═══════════════════════════════════════════════════════════════════

_DISCOVERY_EXAMPLES = (
    "## EJEMPLOS\n\n"
    "Ejemplo 1 — Cambio de unidad:\n"
    '  Cambio: "peso en kilogramos" → "peso en libras"\n'
    '  Feature "Calculo de peso total" → accion: "update", '
    'razon: "La unidad de medida cambio de kg a lb, la feature debe reflejar libras."\n\n'
    "Ejemplo 2 — Eliminacion de concepto:\n"
    '  Cambio: se elimina la seccion "Gestion de Inventario" del documento fuente\n'
    '  Feature "Control de stock" → accion: "delete", '
    'razon: "El concepto de inventario ya no existe en el descubrimiento."\n\n'
    "Ejemplo 3 — Cambio cosmetico:\n"
    '  Cambio: se corrige una tilde en "Vision"\n'
    '  Feature "Dashboard de metricas" → NO incluir (accion "keep" implicita).\n\n'
)

_CONSISTENCY_SYSTEM_PROMPT = build_consistency_prompt(
    direction="downstream",
    source_label="Descubrimiento",
    target_artifact="Feature",
    extra_rules=_DISCOVERY_EXAMPLES,
)

CONSISTENCY_UPSTREAM_SYSTEM_PROMPT = build_consistency_prompt(
    direction="upstream_features",
    source_label="Caracteristicas",
    target_artifact="DiscoveryDocument",
    extra_rules="El artifact_id del documento de Descubrimiento es EXACTAMENTE "
    "el que aparece en la lista de artefactos. Copialo literalmente.\n\n",
)

CONSISTENCY_REQUIREMENTS_DOWNSTREAM_SYSTEM_PROMPT = build_consistency_prompt(
    direction="upstream_requirements_features",
    source_label="Requisitos",
    target_artifact="Feature",
    extra_rules=_LEVEL_RULES_REQUIREMENTS,
)

CONSISTENCY_REQUIREMENTS_UPSTREAM_SYSTEM_PROMPT = build_consistency_prompt(
    direction="upstream_requirements",
    source_label="Requisitos",
    target_artifact="DiscoveryDocument",
    extra_rules="El artifact_id del documento de Descubrimiento es EXACTAMENTE "
    "el que aparece en la lista de artefactos. Copialo literalmente.\n\n",
)

CONSISTENCY_FEATURES_DOWNSTREAM_SYSTEM_PROMPT = build_consistency_prompt(
    direction="downstream",
    source_label="Caracteristicas",
    target_artifact="EARSRequirement",
    extra_rules=_LEVEL_RULES_REQUIREMENTS_DOWNSTREAM + _REQUIREMENTS_DOWNSTREAM_EXAMPLES,
)

CONSISTENCY_REQUIREMENTS_MODEL_SYSTEM_PROMPT = build_consistency_prompt(
    direction="downstream",
    source_label="Requisitos",
    target_artifact="ActivityDiagram",
    extra_rules=_LEVEL_RULES_MODEL,
)

CONSISTENCY_DISCOVERY_REQUIREMENTS_PROMPT = build_consistency_prompt(
    direction="downstream",
    source_label="Descubrimiento",
    target_artifact="EARSRequirement",
    extra_rules=_LEVEL_RULES_REQUIREMENTS_DOWNSTREAM + _REQUIREMENTS_DOWNSTREAM_EXAMPLES,
)

CONSISTENCY_DISCOVERY_MODEL_PROMPT = build_consistency_prompt(
    direction="downstream",
    source_label="Descubrimiento",
    target_artifact="ActivityDiagram",
    extra_rules=_LEVEL_RULES_MODEL,
)

CONSISTENCY_FEATURES_MODEL_PROMPT = build_consistency_prompt(
    direction="downstream",
    source_label="Caracteristicas",
    target_artifact="ActivityDiagram",
    extra_rules=_LEVEL_RULES_MODEL,
)

CONSISTENCY_VALIDATE_CREATE_FEATURE_PROMPT = (
    "Eres un analista de trazabilidad de software.\n"
    "Tu tarea es analizar un documento de Descubrimiento completo y una nueva "
    "característica propuesta, realizando DOS tareas en una sola respuesta:\n\n"
    "1. DERIVA EL ORIGEN: identifica las secciones del Descubrimiento que "
    "fundamentan esta característica. Recorre todas las secciones del documento "
    "(Visión, Espacio del problema, Actores, Propuesta de valor, Metas del "
    "producto, Alcance, Reglas de negocio y cualquier otra presente). "
    "Devuelve una cadena de trazabilidad en el campo 'origin' con el formato:\n"
    '   "Derivado de [sección(es)] del descubrimiento."\n'
    "   Si la característica no se relaciona claramente con ninguna sección, usa:\n"
    '   "Sin relación directa con las secciones del descubrimiento."\n\n'
    "2. VERIFICA COHERENCIA: determina si la característica es consistente con "
    "el contenido de TODAS las secciones del Descubrimiento. Si la característica "
    "contradice explícitamente la visión, el alcance declarado, los actores "
    "identificados, las metas definidas o cualquier regla de negocio, indica "
    "is_consistent=false y explica el motivo en el campo 'reason'.\n\n"
    "REGLAS DE REDACCIÓN Y ORTOGRAFÍA:\n"
    "- Redacta en español formal con impecable ortografía, gramática y todas las tildes normativas.\n"
    "- Presta especial atención a: 'característica', 'descripción', 'sección', "
    "'relación', 'semántica', 'propósito', 'inyección', 'además', 'amplía', 'más allá'.\n\n"
    "Responde ÚNICAMENTE con el siguiente JSON, sin markdown ni texto adicional:\n"
    "{\n"
    '  "origin": "<cadena de trazabilidad derivada>",\n'
    '  "is_consistent": true,\n'
    '  "reason": ""\n'
    "}\n\n"
    "Si la característica NO es consistente:\n"
    "{\n"
    '  "origin": "<cadena de trazabilidad derivada>",\n'
    '  "is_consistent": false,\n'
    '  "reason": "<explicación clara de la contradicción, en español con ortografía y tildes correctas>"\n'
    "}\n\n"
    "IMPORTANTE: Siempre incluye el campo origin. No uses el carácter guion largo (—)."
)


class ConsistencyEvaluationMode:
    def __init__(
        self,
        phase_name: SpecPhase = SpecPhase.DESCUBRIMIENTO,
        system_prompt: str | None = None,
    ) -> None:
        self._phase_name = phase_name
        self._system_prompt = system_prompt or _CONSISTENCY_SYSTEM_PROMPT

    @property
    def requires_enrichment(self) -> bool:
        return False

    @property
    def requires_tool_consultation(self) -> bool:
        return True

    @property
    def phase_name(self) -> SpecPhase:
        return self._phase_name

    @property
    def temperature(self) -> float:
        return 0.2

    @property
    def max_tokens(self) -> int:
        return 16384

    @property
    def output_type(self) -> type[BaseModel]:
        return ConsistencyDetectionReport

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @property
    def available_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="get_requirements_for_feature",
                description="Recupera los requisitos EARS en markdown de una caracteristica",
                parameters={
                    "type": "object",
                    "properties": {
                        "feature_id": {
                            "type": "string",
                            "description": "ID de la caracteristica a consultar (ej. feat_01KT...)",
                        },
                    },
                    "required": ["feature_id"],
                },
            ),
            ToolDefinition(
                name="get_diagram_for_feature",
                description="Recupera el diagrama de actividad PlantUML de una caracteristica",
                parameters={
                    "type": "object",
                    "properties": {
                        "feature_id": {
                            "type": "string",
                            "description": "ID de la caracteristica a consultar (ej. feat_01KT...)",
                        },
                    },
                    "required": ["feature_id"],
                },
            ),
        ]

    def build_user_prompt(self, context: ConsistencyPhaseContext) -> str:
        changes_text = "\n".join(
            f"### Cambio en '{c.section}'\n"
            f"**Descripcion:** {c.description}\n"
            f"**Antes:**\n{c.diff.before}\n"
            f"**Despues:**\n{c.diff.after}\n"
            for c in context.applied_changes
        )
        artifacts_text = "\n".join(
            f'- [{a.artifact_type}] id={a.artifact_id}, titulo="{a.title}", descripcion="{a.description}"'
            for a in context.downstream_artifacts
        )
        source_doc = context.source_content or "(no disponible)"

        return (
            f"## Fase origen: {context.source_phase.value}\n"
            f"## Fase destino: {context.target_phase.value}\n\n"
            f"### Documento fuente actual:\n{source_doc}\n\n"
            f"### Cambios aplicados:\n{changes_text}\n\n"
            f"### Artefactos actuales en la fase destino:\n{artifacts_text}\n\n"
            "## Instrucciones\n\n"
            "Analiza cada artefacto contra los cambios aplicados y el documento fuente actual. "
            "Determina que accion requiere cada uno (update, delete, o keep). "
            "SOLO detectas el impacto: NO generes el texto corregido. "
            "La correccion exacta la redacta otra fase con el contenido completo del artefacto.\n\n"
            "Usa ortografia correcta en español con TODAS las tildes "
            "(á, é, í, ó, ú), eñes (ñ), signos de puntuacion y mayusculas "
            "iniciales donde corresponda.\n\n"
            "Responde UNICAMENTE en el formato JSON especificado."
        )

    def validate_output(self, output: Any, *, context: Any = None) -> ValidationResult:  # noqa: ARG002
        errors: list[str] = []
        if not isinstance(output, ConsistencyDetectionReport):
            errors.append("El output debe ser un ConsistencyDetectionReport.")
            return ValidationResult(is_valid=False, errors=errors)
        if output.actions:
            for idx, action in enumerate(output.actions):
                if not action.artifact_id:
                    errors.append(f"actions[{idx}] falta 'artifact_id'.")
                if not action.rationale:
                    errors.append(f"actions[{idx}] falta 'rationale'.")
                if action.action not in ("update", "delete"):
                    errors.append(f"actions[{idx}] accion invalida '{action.action}'. Usa 'update' o 'delete'.")
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def build_validation_feedback(self, errors: list[str]) -> str:
        error_list = "\n".join(f"- {e}" for e in errors)
        return f"## Errores de validacion\n\n{error_list}\n\nCorrige los errores y genera una nueva respuesta."

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
            "Genera una nueva respuesta en el formato JSON especificado."
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


def _render_changes(context: ConsistencyPhaseContext) -> str:
    return "\n".join(
        f"### Cambio en '{c.section}'\n"
        f"**Descripcion:** {c.description}\n"
        f"**Antes:**\n{c.diff.before}\n"
        f"**Despues:**\n{c.diff.after}\n"
        for c in context.applied_changes
    )


def _render_source(context: ConsistencyPhaseContext) -> str:
    return context.source_content or "(no disponible)"


_CORRECTION_SYSTEM_PROMPT = """Eres un analista experto en trazabilidad de requisitos de software.
Tu UNICA responsabilidad es generar la correccion textual EXACTA para UN artefacto
que fue marcado como afectado por cambios aplicados en una fase anterior.

## Reglas
1. COPIA VERBATIM: 'suggested_before' debe ser una copia EXACTA y LITERAL de un
   fragmento del contenido actual del artefacto. No parafrasees. Si el texto no
   existe exactamente en el artefacto, la correccion no se podra aplicar.
2. 'suggested_after' contiene SOLO el texto corregido del mismo fragmento.
3. Tipo de artefacto:
   - Feature: 'suggested_field' debe ser 'title' o 'description'. 'suggested_after'
     contiene SOLO el nuevo valor del campo, no la feature completa.
   - EARSRequirement: 'suggested_field' debe ser el codigo del requisito (ej. 'REQ-6.1')
     o 'statement'. 'suggested_before'/'suggested_after' son fragmentos del markdown
     EARS (enunciado, clausula o bloque de requisito). Copia el texto exacto tal como
     aparece en el artefacto. Manten los codigos REQ-X.Y y el formato original.
   - ActivityDiagram: fragmentos PlantUML. Preserva la sintaxis: @startuml/@enduml,
     balance de if/endif y fork/end merge.
   - DiscoveryDocument: 'suggested_field' es el titulo de la seccion
     (ej. '## Vision'). 'suggested_before'/'suggested_after' son el contenido
     de la seccion a modificar.
4. Prohibido usar el caracter guion largo. Usa punto, coma o dos puntos.
5. ORTOGRAFIA: escribe en español correcto con TODAS las tildes (á, é, í, ó, ú),
   dieresis (ü) y eñes (ñ). Usa signos de puntuacion correctos.

## FORMATO DE SALIDA (JSON estricto)
Responde UNICAMENTE con el siguiente JSON, sin markdown ni texto adicional:
{
  "suggested_field": "<campo o seccion, segun el tipo de artefacto>",
  "suggested_before": "<fragmento EXACTO del artefacto actual>",
  "suggested_after": "<fragmento corregido>"
}
"""


def _is_diagram_context(context: object) -> bool:
    return (
        isinstance(context, ConsistencyPhaseContext)
        and bool(context.downstream_artifacts)
        and context.downstream_artifacts[0].artifact_type == "ActivityDiagram"
    )


class ConsistencyCorrectionMode:
    @property
    def requires_enrichment(self) -> bool:
        return False

    @property
    def phase_name(self) -> SpecPhase:
        return SpecPhase.DESCUBRIMIENTO

    @property
    def temperature(self) -> float:
        return 0.2

    @property
    def max_tokens(self) -> int:
        return 8192

    @property
    def output_type(self) -> type[BaseModel]:
        return ConsistencyCorrection

    @property
    def system_prompt(self) -> str:
        return _CORRECTION_SYSTEM_PROMPT

    @property
    def available_tools(self) -> list[ToolDefinition]:
        return []

    def build_user_prompt(self, context: ConsistencyPhaseContext) -> str:
        artifacts = context.downstream_artifacts
        artifact_text = "(no disponible)"
        if artifacts:
            a = artifacts[0]
            artifact_text = (
                f'- [{a.artifact_type}] id={a.artifact_id}, titulo="{a.title}"\n'
                f"### Contenido actual COMPLETO del artefacto:\n{a.description}\n"
            )

        return (
            f"## Fase origen: {context.source_phase.value}\n"
            f"## Fase destino: {context.target_phase.value}\n\n"
            f"### Documento fuente actual:\n{_render_source(context)}\n\n"
            f"### Cambios aplicados:\n{_render_changes(context)}\n\n"
            f"### Artefacto afectado:\n{artifact_text}\n\n"
            "## Instrucciones\n\n"
            "Genera la correccion exacta para el artefacto afectado: copia VERBATIM "
            "el fragmento actual del artefacto en 'suggested_before' y escribe el texto "
            "corregido en 'suggested_after'. Responde UNICAMENTE con el JSON especificado."
        )

    def validate_output(self, output: Any, *, context: Any = None) -> ValidationResult:
        errors: list[str] = []
        if isinstance(output, ConsistencyCorrection):
            before = output.suggested_before
            after = output.suggested_after
        elif isinstance(output, dict):
            correction_dict: dict[str, object] = output  # type: ignore[reportUnknownVariableType]
            before = str(correction_dict.get("suggested_before", ""))
            after = str(correction_dict.get("suggested_after", ""))
        else:
            errors.append("El output debe ser un ConsistencyCorrection.")
            return ValidationResult(is_valid=False, errors=errors)
        if not before and not after:
            errors.append("La correccion debe incluir 'suggested_before' o 'suggested_after'.")
        if after and _is_diagram_context(context):
            diagram_validation = validate_activity_diagram_syntax(wrap_diagram_fragment(after))
            if not diagram_validation.is_valid:
                errors.append("El fragmento PlantUML sugerido no es valido: " + "; ".join(diagram_validation.errors))
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def build_validation_feedback(self, errors: list[str]) -> str:
        error_list = "\n".join(f"- {e}" for e in errors)
        return f"## Errores de validacion\n\n{error_list}\n\nCorrige los errores y genera una nueva respuesta."

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
            "Genera una nueva respuesta en el formato JSON especificado."
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
