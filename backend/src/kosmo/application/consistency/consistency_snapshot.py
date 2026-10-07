from __future__ import annotations

from kosmo.contracts.sdd.codegen import FeatureImplementationRepository
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.contracts.sdd.repositories import (
    ActivityDiagramRepository,
    DocumentRepository,
    FeatureRepository,
    RequirementRepository,
)
from kosmo.domain.sdd.document_converters import document_to_markdown


def _feature_scope(target_artifact_id: str) -> FeatureId:
    return FeatureId(target_artifact_id.split(":", 1)[0])


async def fetch_snapshot_parts(
    *,
    project_id: ProjectId,
    source_phase: SpecPhase,
    target_phase: SpecPhase,
    target_artifact_id: str,
    artifact_type: str,
    document_repo: DocumentRepository,
    feature_repo: FeatureRepository,
    requirement_repo: RequirementRepository,
    diagram_repo: ActivityDiagramRepository,
    implementation_repo: FeatureImplementationRepository | None = None,
) -> list[str]:
    """Entradas canonicas del hash de frescura: contenido fuente + contenido destino."""
    parts = [source_phase.value, target_phase.value, target_artifact_id, artifact_type]

    if source_phase == SpecPhase.DESCUBRIMIENTO:
        source_doc = await document_repo.get_discovery(project_id)
        parts.append(document_to_markdown(source_doc) if source_doc is not None else "none")
    elif source_phase == SpecPhase.CARACTERISTICAS:
        feature = await feature_repo.by_id(_feature_scope(target_artifact_id))
        parts.append(f"{feature.title}|{feature.description}|{feature.origin}" if feature is not None else "none")
    elif source_phase == SpecPhase.REQUISITOS:
        markdown = await requirement_repo.by_feature_id(_feature_scope(target_artifact_id))
        parts.append(markdown or "none")
    elif source_phase == SpecPhase.MODELO:
        diagram = await diagram_repo.by_feature_id(_feature_scope(target_artifact_id))
        parts.append(diagram.diagram_syntax if diagram is not None else "none")
    else:
        parts.append("none")

    if artifact_type == "Feature":
        feature = await feature_repo.by_id(_feature_scope(target_artifact_id))
        parts.append(f"{feature.title}|{feature.description}|{feature.origin}" if feature is not None else "none")
    elif artifact_type == "EARSRequirement":
        markdown = await requirement_repo.by_feature_id(_feature_scope(target_artifact_id))
        parts.append(markdown or "none")
    elif artifact_type == "ActivityDiagram":
        diagram = await diagram_repo.by_feature_id(_feature_scope(target_artifact_id))
        parts.append(diagram.diagram_syntax if diagram is not None else "none")
    elif artifact_type == "DiscoveryDocument":
        target_doc = await document_repo.get_discovery(project_id)
        parts.append(document_to_markdown(target_doc) if target_doc is not None else "none")
    elif artifact_type == "FeatureImplementation":
        if implementation_repo is not None:
            impl = await implementation_repo.by_feature_id(_feature_scope(target_artifact_id))
            parts.append(f"{impl.status.value}|{','.join(impl.generated_files)}" if impl is not None else "none")
        else:
            parts.append("none")
    else:
        parts.append("none")

    return parts
