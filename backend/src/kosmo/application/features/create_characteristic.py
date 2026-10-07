from __future__ import annotations

import json
from contextlib import suppress
from dataclasses import dataclass

import structlog

from kosmo.contracts.llm.ports import LLMClient, PromptTemplate
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.contracts.sdd.repositories import DocumentRepository, FeatureRepository
from kosmo.domain.codegen.integration_rules import detect_capability_overlap
from kosmo.domain.sdd.document_converters import document_to_markdown, slugify_spanish
from kosmo.domain.sdd.id_generator import IdGenerator

_log = structlog.get_logger(__name__)

_VALIDATE_SYSTEM_PROMPT = (
    "Eres un analista estricto de trazabilidad de software.\n"
    "Tu tarea es analizar un documento de Descubrimiento y una nueva característica "
    "propuesta, realizando DOS tareas en una sola respuesta:\n\n"
    "## 1. DERIVA EL ORIGEN\n\n"
    "Identifica las 2-3 secciones MÁS ESPECÍFICAS del Descubrimiento que fundamentan "
    "esta característica. Debes ser preciso y concreto.\n\n"
    "REGLAS:\n"
    "- MÁXIMO 3 secciones. NO enumeres todas las secciones del documento. Si la "
    "característica se relaciona con muchas, selecciona solo las MÁS ESPECÍFICAS.\n"
    "- Cuando sea posible, cita el contenido concreto de la sección (ej: 'la regla "
    "de precios en moneda local definida en Reglas de negocio').\n"
    "- Si la característica NO tiene relación semántica real con ninguna sección, "
    "usa EXACTAMENTE: 'Sin relación directa con las secciones del descubrimiento.' "
    "y DEBES marcar is_consistent=false explicando por qué no encaja.\n"
    "- No uses la palabra 'Derivado de' al inicio. Usa un formato descriptivo.\n\n"
    "EJEMPLOS BUENOS:\n"
    "- 'Regla de cálculo de impuestos en Reglas de negocio y Actor Administrador en Actores.'\n"
    "- 'Meta Reducción de errores en Metas del producto y la descripción del problema "
    "de errores manuales en Espacio del problema.'\n"
    "- 'Sin relación directa con las secciones del descubrimiento.'\n\n"
    "EJEMPLOS MALOS (NUNCA hagas esto):\n"
    "- 'Derivado de Actores, Propuesta de valor, Metas, Reglas de negocio, Visión y Alcance.' "
    "(demasiado genérico, no aporta trazabilidad real)\n"
    "- 'Derivado del descubrimiento.' (no especifica secciones)\n\n"
    "## 2. VERIFICA COHERENCIA\n\n"
    "Determina si la característica es CONSISTENTE con el contenido de TODAS las "
    "secciones del Descubrimiento. Sé EXIGENTE:\n\n"
    "- Si la característica introduce conceptos, tecnologías, actores o reglas que "
    "NO aparecen en ninguna sección del descubrimiento, NO es consistente.\n"
    "- Si la característica contradice una regla de negocio explícita, NO es "
    "consistente.\n"
    "- Si la característica amplía el alcance más allá de lo declarado, NO es "
    "consistente.\n"
    "- Solo si la característica encaja naturalmente en el contexto del "
    "descubrimiento sin contradicciones, es consistente.\n"
    "- Si marcas is_consistent=false, el campo 'reason' DEBE explicar "
    "CONCRETAMENTE qué contradicción encontraste y en qué sección.\n\n"
    "## REGLAS DE REDACCIÓN Y ORTOGRAFÍA\n\n"
    "- Redacta en español formal y profesional con impecable ortografía, gramática y acentuación.\n"
    "- Usa obligatoriamente todas las tildes normativas en mayúsculas y minúsculas (á, é, í, ó, ú, Á, É, Í, Ó, Ú), "
    "diéresis (ü) y eñes (ñ).\n"
    "- Presta especial atención a palabras clave: 'característica', 'descripción', 'sección', 'relación', "
    "'semántica', 'propósito', 'inyección', 'además', 'amplía', 'más allá', 'explícita', 'contradicción'.\n"
    "- Emplea puntuación correcta: inicia con mayúscula y concluye con punto final.\n\n"
    "## FORMATO DE SALIDA\n\n"
    "Responde ÚNICAMENTE con JSON. Sin markdown, sin texto adicional.\n\n"
    "Si es consistente:\n"
    '{"origin": "<origen preciso, máx 3 secciones>", "is_consistent": true, "reason": ""}\n\n'
    "Si NO es consistente:\n"
    '{"origin": "<origen preciso>", "is_consistent": false, '
    '"reason": "<explicación concreta de la contradicción con redacción y ortografía impecables>"}\n\n'
    "IMPORTANTE: Siempre incluye el campo origin. No uses guion largo (—). Sé estricto."
)


@dataclass(frozen=True)
class CreateCharacteristicInput:
    project_id: ProjectId
    title: str
    description: str
    origin: str = ""


@dataclass(frozen=True)
class CreateCharacteristicOutput:
    is_saved: bool
    characteristic: Feature | None = None
    origin: str = ""
    is_consistent: bool = True
    inconsistency_reason: str = ""
    warnings: tuple[str, ...] = ()


class CreateCharacteristicUseCase:
    def __init__(
        self,
        feature_repo: FeatureRepository,
        document_repo: DocumentRepository | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self._feature_repo = feature_repo
        self._document_repo = document_repo
        self._llm_client = llm_client

    async def execute(self, input_data: CreateCharacteristicInput) -> CreateCharacteristicOutput:
        if not input_data.title.strip():
            raise ValueError("El titulo de la caracteristica no puede estar vacio")
        if len(input_data.title) > 50:
            raise ValueError(
                f"El titulo de la caracteristica no puede exceder los 50 caracteres (actual: {len(input_data.title)})"
            )
        if len(input_data.description) > 500:
            raise ValueError(
                f"La descripcion de la caracteristica no puede exceder los 500 caracteres "
                f"(actual: {len(input_data.description)})"
            )

        origin = input_data.origin.strip()

        if not origin and self._document_repo is not None and self._llm_client is not None:
            derived = await self._derive_origin(input_data.project_id, input_data.title, input_data.description)
            origin = str(derived.get("origin", ""))
            if not bool(derived.get("is_consistent", True)):
                return CreateCharacteristicOutput(
                    is_saved=False,
                    origin=origin,
                    is_consistent=False,
                    inconsistency_reason=str(derived.get("reason", "")),
                )

        if not origin:
            origin = "Definicion manual"

        existing_features = await self._feature_repo.list_by_project(input_data.project_id)
        next_number = await self._feature_repo.next_number(input_data.project_id)

        feature = Feature(
            id=FeatureId(IdGenerator.generate("feature")),
            project_id=input_data.project_id,
            number=next_number,
            title=input_data.title.strip(),
            slug=slugify_spanish(input_data.title) or f"feature-{next_number}",
            description=input_data.description,
            origin=origin,
        )

        overlaps = detect_capability_overlap(feature, existing_features)
        warnings = tuple(o.message for o in overlaps if o.message)

        saved = await self._feature_repo.save(feature)
        return CreateCharacteristicOutput(
            is_saved=True,
            characteristic=saved,
            origin=origin,
            warnings=warnings,
        )

    async def _derive_origin(self, project_id: ProjectId, title: str, description: str) -> dict[str, object]:
        doc = await self._document_repo.get_discovery(project_id)  # type: ignore[union-attr]
        if doc is None:
            return {"origin": "Definicion manual — sin discovery disponible", "is_consistent": True, "reason": ""}

        discovery_md = document_to_markdown(doc)
        user_prompt = (
            f"### Documento de Descubrimiento:\n{discovery_md[:20000]}\n\n"
            f"### Nueva característica propuesta:\n"
            f"Título: {title}\n"
            f"Descripción: {description}\n"
        )

        try:
            response = await self._llm_client.complete_json(  # type: ignore[union-attr]
                prompt=PromptTemplate(
                    system_prompt=_VALIDATE_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                ),
                temperature=0.2,
                max_tokens=2048,
            )
            data: dict[str, object] = {}
            with suppress(json.JSONDecodeError):
                data = json.loads(response.text)
            return data
        except Exception:
            _log.warning("create_char.llm_failed", project_id=str(project_id), exc_info=True)
            return {"origin": "Definicion manual", "is_consistent": True, "reason": ""}
