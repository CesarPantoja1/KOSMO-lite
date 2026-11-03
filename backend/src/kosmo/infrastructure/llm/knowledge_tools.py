from __future__ import annotations

import json
from typing import Any

from kosmo.contracts.memory.agent_memory import AgentMemoryPort
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.contracts.sdd.repositories import (
    DocumentRepository,
    FeatureRepository,
    RequirementRepository,
)
from kosmo.domain.pipeline.knowledge_tool_registry import KnowledgeToolDef, KnowledgeToolHandler


def build_get_phase_document(
    document_repo: DocumentRepository,
) -> tuple[KnowledgeToolDef, KnowledgeToolHandler]:
    tool_def = KnowledgeToolDef(
        name="get_phase_document",
        description="Recupera el contenido completo de un documento de una fase del proyecto actual",
        parameters={
            "type": "object",
            "properties": {
                "phase": {
                    "type": "string",
                    "enum": [p.value for p in SpecPhase],
                    "description": "Fase del documento a recuperar",
                },
                "project_id": {
                    "type": "string",
                    "description": "ID del proyecto actual",
                },
            },
            "required": ["phase", "project_id"],
        },
    )

    async def handler(input_data: dict[str, Any]) -> str:
        phase_value = input_data.get("phase", "")
        project_id_str = input_data.get("project_id", "")
        try:
            phase = SpecPhase(phase_value)
        except ValueError:
            return f"Error: fase '{phase_value}' no valida. Fases disponibles: {[p.value for p in SpecPhase]}"

        pid = ProjectId(project_id_str)
        from kosmo.domain.sdd.document_converters import document_to_markdown

        if phase == SpecPhase.DESCUBRIMIENTO:
            doc = await document_repo.get_discovery(pid)
        else:
            return (
                f"La fase {phase.value} no tiene documento asociado directamente. "
                "Usa get_downstream_artifacts para caracteristicas y requisitos."
            )

        if doc is None:
            return f"No se encontro documento para la fase {phase.value}"

        return document_to_markdown(doc)

    return tool_def, handler


def build_find_similar_sessions(
    agent_memory: AgentMemoryPort,
    embedder: Any,
) -> tuple[KnowledgeToolDef, KnowledgeToolHandler]:
    tool_def = KnowledgeToolDef(
        name="find_similar_sessions",
        description="Busca sesiones de otros proyectos con contenido similar al tema consultado",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Descripcion del tema o problema a buscar en sesiones previas",
                },
            },
            "required": ["query"],
        },
    )

    async def handler(input_data: dict[str, Any]) -> str:
        query = input_data.get("query", "")
        if not query:
            return "Error: parametro 'query' requerido"

        embedding = await embedder.embed(query)
        if embedding is None:
            return "No se pudo generar embedding para la busqueda"

        sessions = await agent_memory.get_similar_sessions(
            embedding,
            limit=3,
            exclude_project_id=ProjectId(input_data.get("project_id", "")),
        )

        if not sessions:
            return "No se encontraron sesiones similares en otros proyectos"

        lines = ["Sesiones similares encontradas:"]
        for s in sessions:
            lines.append(
                f"- Proyecto {s.project_id}, fase {s.phase.value} ({s.session_type}): "
                f"{'completada' if s.is_completed else 'incompleta'}, "
                f"{s.total_llm_calls} llamadas LLM"
            )
            if s.user_instructions:
                lines.append(f"  Instrucciones: {s.user_instructions}")
        return "\n".join(lines)

    return tool_def, handler


def build_get_downstream_artifacts(
    feature_repo: FeatureRepository,
) -> tuple[KnowledgeToolDef, KnowledgeToolHandler]:
    tool_def = KnowledgeToolDef(
        name="get_downstream_artifacts",
        description=("Recupera artefactos relacionados con una caracteristica (features hijas, requisitos asociados)"),
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
    )

    async def handler(input_data: dict[str, Any]) -> str:

        feature_id_str = input_data.get("feature_id", "")
        if not feature_id_str:
            return "Error: parametro 'feature_id' requerido"

        feature = await feature_repo.by_id(FeatureId(feature_id_str))
        if feature is None:
            return f"No se encontro la caracteristica {feature_id_str}"

        info = {
            "id": str(feature.id),
            "number": feature.number,
            "title": feature.title,
            "description": feature.description,
            "origin": feature.origin,
        }
        return json.dumps(info, ensure_ascii=False, indent=2)

    return tool_def, handler


def build_get_requirements_for_feature(
    requirement_repo: RequirementRepository,
) -> tuple[KnowledgeToolDef, KnowledgeToolHandler]:
    tool_def = KnowledgeToolDef(
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
    )

    async def handler(input_data: dict[str, Any]) -> str:
        feature_id_str = input_data.get("feature_id", "")
        if not feature_id_str:
            return "Error: parametro 'feature_id' requerido"

        markdown = await requirement_repo.by_feature_id(FeatureId(feature_id_str))
        if not markdown:
            return f"No se encontraron requisitos EARS para la caracteristica {feature_id_str}"

        return markdown[:4000]

    return tool_def, handler


def build_get_impact(
    traceability_repo: Any,
) -> tuple[KnowledgeToolDef, KnowledgeToolHandler]:
    tool_def = KnowledgeToolDef(
        name="get_impact",
        description=("Consulta que artefactos dependen de uno dado (features de un requisito, etc.)"),
        parameters={
            "type": "object",
            "properties": {
                "artifact_id": {
                    "type": "string",
                    "description": "ID del artefacto a consultar (ej. feat_01, req_01, dia_01)",
                },
            },
            "required": ["artifact_id"],
        },
    )

    async def handler(input_data: dict[str, Any]) -> str:
        artifact_id = input_data.get("artifact_id", "")
        if not artifact_id:
            return "Error: parametro 'artifact_id' requerido"

        impact = await traceability_repo.get_impact(artifact_id)

        lines: list[str] = [f"Impacto de {artifact_id}:"]
        if impact["upstream"]:
            lines.append("\nArtefactos upstream (de los que depende):")
            for u in impact["upstream"]:
                lines.append(f"- {u['type']}: {u['id']}")
        if impact["downstream"]:
            lines.append("\nArtefactos downstream (que dependen de el):")
            for d in impact["downstream"]:
                lines.append(f"- {d['type']}: {d['id']}")
        if not impact["upstream"] and not impact["downstream"]:
            lines.append("No se encontraron dependencias registradas.")
        return "\n".join(lines)

    return tool_def, handler
