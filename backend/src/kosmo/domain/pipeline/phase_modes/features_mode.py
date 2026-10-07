from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel

from kosmo.contracts.memory.user_preference import UserPreference
from kosmo.contracts.pipeline.orchestrator_ports import ToolDefinition
from kosmo.contracts.pipeline.phase_contexts import (
    DiscoveryPhaseContext,
    EARSPhaseContext,
    FeaturesPhaseContext,
    SuggestFeaturesContext,
)
from kosmo.contracts.pipeline.phase_outputs import (
    FeaturesPhaseOutput,
    GenerationMetadata,
    ValidationResult,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.guardrails import DISCOVERY_SECTIONS
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.domain.pipeline._dict_utils import dict_str_keys
from kosmo.domain.sdd.document_converters import slugify_spanish
from kosmo.domain.sdd.id_generator import IdGenerator

FIRST_GENERATION_COUNT = 5

_FEATURES_SYSTEM_PROMPT = (
    "Eres un diseñador de producto experto.\n"
    "Las Características operan a nivel de usuario: cada característica expresa "
    "lo que el usuario desea lograr, no lo que el software hace. En este nivel "
    "no existe todavía un sistema ni una aplicación.\n\n"
    "Genera características con EXACTAMENTE cuatro campos:\n\n"
    "### 1. Código\n"
    "Identificador correlativo con formato C seguido de dos dígitos (C01, C02, C03). "
    "Se representa como 'number' (entero secuencial desde 1).\n\n"
    "### 2. Título\n"
    "Máximo seis palabras que expresan la intención de interacción del usuario "
    "con el futuro producto. Se redacta como una acción que el usuario desea "
    "realizar. Evita nomenclatura de software y terminología de negocio abstracta.\n\n"
    "### 3. Descripción\n"
    "Párrafo de una a dos oraciones que describe cómo el usuario interactuaría "
    "con el producto para lograr el propósito del título. Se construye desde "
    "la perspectiva del usuario, sin mencionar componentes de software, "
    "mecanismos técnicos ni conceptos de negocio abstractos.\n\n"
    "### 4. Origen\n"
    "Unifica la justificación de existencia de la característica y las secciones "
    "del Descubrimiento de las cuales se deriva. Explica en una a dos oraciones "
    "por qué resulta esencial y enumera las secciones del Descubrimiento que la "
    "fundamentan.\n\n"
    "Secciones válidas del Descubrimiento para trazabilidad:\n"
    + "\n".join(f"- {s}" for s in DISCOVERY_SECTIONS)
    + "\n\n"
    "REGLAS CRÍTICAS DE CALIDAD:\n"
    "1. NIVEL DE USUARIO: Las características expresan lo que el usuario desea "
    "lograr, no lo que el software hace. PROHIBIDO: API, base de datos, "
    "microservicios, endpoints, servidores, lenguajes, frameworks, protocolos, "
    "arquitectura, deployment, Docker, cloud, SQL, HTTP, REST, GraphQL, backend, "
    "frontend, cache, Redis, MongoDB, PostgreSQL, Kubernetes, AWS, GCP, Azure, "
    "plataforma, sistema, software, web, aplicación, aplicaciones.\n"
    "2. SIN TERMINOLOGÍA DE NEGOCIO ABSTRACTA: PROHIBIDO usar términos como: "
    "propuesta de valor, modelo de negocio, ventaja competitiva, diferenciador, "
    "monetización, ROI, KPI, stakeholder, oportunidad de mercado, segmento de "
    "mercado, caso de negocio, estrategia comercial. El origin puede mencionar "
    "nombres de secciones del Descubrimiento, pero el título y la descripción "
    "no deben contenerlos.\n"
    "3. NO DUPLICADOS: Las características generadas deben ser distintas entre sí "
    "y no presentar solapamiento o redundancia semántica.\n"
    "4. TÍTULO MÁXIMO SEIS PALABRAS: El título no puede exceder seis palabras.\n"
    "5. TRAZABILIDAD: El campo origin debe mencionar al menos una sección del "
    "Descubrimiento de la lista anterior.\n"
    "6. IDIOMA: Todo el contenido debe estar en español con acentuación y "
    "ortografía correctas.\n"
    "7. CANTIDAD: En la primera generación (sin características previas), genera "
    "EXACTAMENTE 5 características. En generaciones posteriores, el número puede "
    "variar.\n\n"
    "FORMATO DE SALIDA:\n"
    "Debes responder ÚNICAMENTE con un objeto JSON válido con la siguiente "
    "estructura, sin texto de introducción ni de conclusión:\n"
    "```json\n"
    "{\n"
    '  "features": [\n'
    "    {\n"
    '      "number": 1,\n'
    '      "title": "Registrar gastos entre participantes",\n'
    '      "description": "Cualquier participante del grupo indica el monto de "\n'
    '        "un gasto, selecciona a las personas involucradas.",\n'
    '      "origin": "Se deriva de la meta Gestión financiera de gastos. "\n'
    '        "Se traza a Metas del producto, Actores y Reglas de negocio."\n'
    "    }\n"
    "  ]\n"
    "}\n"
    "```"
)


class FeaturesMode:
    requires_tool_consultation = False

    @property
    def phase_name(self) -> SpecPhase:
        return SpecPhase.CARACTERISTICAS

    @property
    def temperature(self) -> float:
        return 0.4

    @property
    def max_tokens(self) -> int:
        return 8192

    @property
    def output_type(self) -> type[BaseModel]:
        from kosmo.contracts.pipeline.phase_outputs import FeatureSet

        return FeatureSet

    @property
    def system_prompt(self) -> str:
        base = _FEATURES_SYSTEM_PROMPT
        from kosmo.domain.sdd.few_shot.loader import load_example

        example = load_example(SpecPhase.CARACTERISTICAS)
        if example:
            header = "\n\n## Ejemplo de referencia (no copies literalmente; adapta al contexto del usuario)\n\n"
            base += header + example
        return base

    @property
    def available_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="validate_feature_structure",
                description=(
                    "Verifica que las características tengan los cuatro campos requeridos "
                    "(number, title, description, origin), el título no exceda seis palabras "
                    "y el origin incluya trazabilidad al descubrimiento"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "features": {
                            "type": "array",
                            "description": "Lista de características a validar",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "number": {"type": "integer"},
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "origin": {"type": "string"},
                                },
                            },
                        }
                    },
                    "required": ["features"],
                },
            ),
            ToolDefinition(
                name="validate_feature_uniqueness",
                description="Verifica que no existan redundancias ni duplicados entre características",
                parameters={
                    "type": "object",
                    "properties": {
                        "features": {
                            "type": "array",
                            "description": "Lista de características a validar",
                            "items": {"type": "object"},
                        }
                    },
                    "required": ["features"],
                },
            ),
        ]

    def build_user_prompt(
        self,
        context: DiscoveryPhaseContext | FeaturesPhaseContext | EARSPhaseContext | SuggestFeaturesContext,
    ) -> str:
        from kosmo.domain.sdd.document_converters import document_to_markdown

        discovery_md = ""
        existing_titles_list: list[str] = []
        user_prefs: list[Any] = []

        if isinstance(context, (FeaturesPhaseContext, SuggestFeaturesContext)):
            discovery_md = document_to_markdown(context.discovery_document)
            existing_titles_list = context.existing_feature_titles
            user_prefs = context.user_preferences
        elif isinstance(context, EARSPhaseContext):
            discovery_md = document_to_markdown(context.discovery_document)
            user_prefs = context.user_preferences
        else:
            user_prefs = context.user_preferences

        parts = [
            "## Documento de Descubrimiento de Producto\n",
            discovery_md,
        ]

        if existing_titles_list:
            existing_list = "\n".join(f"- {title}" for title in existing_titles_list)
            parts.append(
                f"\n## Características Existentes (NO DUPLICAR NI REPETIR ESTAS CARACTERÍSTICAS):\n\n{existing_list}"
            )
        elif isinstance(context, FeaturesPhaseContext):
            parts.append(f"\n## Cantidad requerida\n\nGenera EXACTAMENTE {FIRST_GENERATION_COUNT} características.")

        if user_prefs:
            pref_strings: list[str] = []
            for p in user_prefs:
                if isinstance(p, UserPreference):
                    pref_strings.append(p.rule_text)
            if pref_strings:
                prefs = "\n".join(f"- {text}" for text in pref_strings)
                parts.append(f"\n## Preferencias del usuario:\n\n{prefs}")

        return "\n".join(parts)

    def validate_output(self, output: Any, *, context: Any = None) -> ValidationResult:
        from kosmo.contracts.pipeline.phase_contexts import FeaturesPhaseContext, SuggestFeaturesContext
        from kosmo.contracts.pipeline.phase_outputs import FeatureSet
        from kosmo.domain.pipeline.phase_validators.features_validator import (
            validate_feature_structure,
            validate_feature_uniqueness,
        )

        existing_titles: list[str] = []
        if isinstance(context, (FeaturesPhaseContext, SuggestFeaturesContext)):
            existing_titles = context.existing_feature_titles

        features_list: list[dict[str, Any]] = []

        if isinstance(output, FeatureSet):
            features_list = [
                {"number": f.number, "title": f.title, "description": f.description, "origin": f.origin}
                for f in output.features
            ]
        elif isinstance(output, dict):
            output_dict = cast(dict[str, object], output)
            if "features" in output_dict:
                raw_features = output_dict["features"]
                if isinstance(raw_features, list):
                    for item in cast(list[object], raw_features):
                        if isinstance(item, dict):
                            feat_dict = dict_str_keys(item)
                            features_list.append(feat_dict)
            elif "raw_text" in output_dict:
                try:
                    text = str(output_dict["raw_text"])
                    if "```json" in text:
                        text = text.split("```json")[1].split("```")[0].strip()
                    elif "```" in text:
                        text = text.split("```")[1].split("```")[0].strip()
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        parsed_dict = cast(dict[str, object], parsed)
                        if "features" in parsed_dict:
                            raw_features = parsed_dict["features"]
                            if isinstance(raw_features, list):
                                for item in cast(list[object], raw_features):
                                    if isinstance(item, dict):
                                        feat_dict = dict_str_keys(item)
                                        features_list.append(feat_dict)
                    elif isinstance(parsed, list):
                        for item in cast(list[object], parsed):
                            if isinstance(item, dict):
                                feat_dict = dict_str_keys(item)
                                features_list.append(feat_dict)
                except Exception:
                    return ValidationResult(
                        is_valid=False,
                        errors=["El formato de salida no es un JSON válido con la clave 'features'."],
                    )
            else:
                return ValidationResult(
                    is_valid=False,
                    errors=["El formato de salida no contiene la clave 'features'."],
                )
        elif isinstance(output, list):
            for item in cast(list[object], output):
                if isinstance(item, dict):
                    feat_dict = dict_str_keys(item)
                    features_list.append(feat_dict)
        else:
            return ValidationResult(
                is_valid=False,
                errors=["El formato de salida debe ser un JSON válido."],
            )

        struct_result = validate_feature_structure(features_list)
        uniq_result = validate_feature_uniqueness(features_list, existing_titles)

        all_errors = struct_result.errors + uniq_result.errors
        all_warnings = struct_result.warnings + uniq_result.warnings

        if not existing_titles:
            count = len(features_list)
            if count != FIRST_GENERATION_COUNT:
                all_errors.append(
                    f"La primera generación debe contener EXACTAMENTE {FIRST_GENERATION_COUNT} "
                    f"características; se generaron {count}."
                )

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            warnings=all_warnings,
        )

    def build_validation_feedback(self, errors: list[str]) -> str:
        error_list = "\n".join(f"- {e}" for e in errors)
        return (
            "## Feedback de validacion\n\n"
            f"La generacion de caracteristicas tiene los siguientes problemas:\n\n{error_list}\n\n"
            "Corrige estos problemas y vuelve a generar la lista completa de caracteristicas."
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
            f"La generación de características tiene los siguientes problemas:\n\n"
            f"{error_list}\n\n"
            f"Corrige estos problemas y vuelve a generar la lista completa de características "
            f"en formato JSON válido con los cuatro campos: number, title, description, origin."
        )

    def build_output(
        self,
        raw_output: Any,
        validation_result: ValidationResult,
        metadata: GenerationMetadata,
        *,
        context: Any = None,
    ) -> FeaturesPhaseOutput:
        from kosmo.contracts.pipeline.phase_contexts import FeaturesPhaseContext
        from kosmo.contracts.pipeline.phase_outputs import FeatureSet
        from kosmo.contracts.sdd.feature import Feature

        project_id = ProjectId("")
        if isinstance(context, FeaturesPhaseContext) and context.project_id is not None:
            project_id = context.project_id

        if isinstance(raw_output, FeatureSet):
            raw_output = {"features": [f.model_dump() for f in raw_output.features]}
        features_list = self._extract_features_list(raw_output)
        features: list[Feature] = []
        for item in features_list:
            title = str(item.get("title", ""))
            features.append(
                Feature(
                    id=FeatureId(IdGenerator.generate("feature")),
                    number=int(item.get("number", 0)),
                    title=title,
                    slug=slugify_spanish(title) or f"feature-{item.get('number', 0)}",
                    description=str(item.get("description", "")),
                    project_id=project_id,
                    origin=str(item.get("origin", "")),
                )
            )
        return FeaturesPhaseOutput(
            features=features,
            validation_result=validation_result,
            generation_metadata=metadata,
        )

    @staticmethod
    def _extract_features_list(content: Any) -> list[dict[str, Any]]:
        if isinstance(content, list):
            result: list[dict[str, Any]] = []
            for item in cast(list[object], content):
                if isinstance(item, dict):
                    feat_dict = dict_str_keys(item)
                    result.append(feat_dict)
            return result
        if isinstance(content, dict):
            raw = cast(dict[str, object], content).get("features", [])
            if isinstance(raw, list):
                result: list[dict[str, Any]] = []
                for item in cast(list[object], raw):
                    if isinstance(item, dict):
                        feat_dict = dict_str_keys(item)
                        result.append(feat_dict)
                return result
        return []
