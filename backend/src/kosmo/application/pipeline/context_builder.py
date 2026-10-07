from __future__ import annotations

from kosmo.contracts.pipeline.phase_contexts import (
    DiscoveryChatContext,
    DiscoveryRefinePhaseContext,
    FeatureChatContext,
    ImplementationPhaseContext,
    RequirementChatContext,
)
from kosmo.contracts.pipeline.phase_errors import PhaseTransitionError
from kosmo.contracts.sdd.errors import FeatureNotFoundError
from kosmo.contracts.sdd.ids import FeatureId, ProjectId, RequirementId
from kosmo.contracts.sdd.repositories import (
    DocumentRepository,
    FeatureRepository,
    ProjectRepository,
    RequirementRepository,
)
from kosmo.domain.sdd.requirements_markdown import parse_requirement_from_markdown


class ContextBuilder:
    def __init__(
        self,
        document_repo: DocumentRepository,
        project_repo: ProjectRepository,
        feature_repo: FeatureRepository | None = None,
        requirement_repo: RequirementRepository | None = None,
    ) -> None:
        self._document_repo = document_repo
        self._project_repo = project_repo
        self._feature_repo = feature_repo
        self._requirement_repo = requirement_repo

    async def build_discovery_refine_context(
        self,
        project_id: ProjectId,
        user_instructions: str,
    ) -> DiscoveryRefinePhaseContext:
        current_document = await self._document_repo.get_discovery(project_id)
        if current_document is None:
            raise PhaseTransitionError(
                detail="No existe un documento de descubrimiento previo para refinar.",
                instance="/pipeline/discovery/refine",
            )

        return DiscoveryRefinePhaseContext(
            current_document=current_document,
            user_instructions=user_instructions,
        )

    async def build_discovery_chat_context(
        self,
        project_id: ProjectId,
    ) -> DiscoveryChatContext:
        current_document = await self._document_repo.get_discovery(project_id)
        if current_document is None:
            raise PhaseTransitionError(
                detail="No existe un documento de descubrimiento para el chat.",
                instance="/pipeline/discovery/chat",
            )

        return DiscoveryChatContext(current_document=current_document)

    async def build_feature_chat_context(
        self,
        feature_id: FeatureId,
    ) -> FeatureChatContext:
        if self._feature_repo is None:
            raise ValueError("ContextBuilder no tiene FeatureRepository configurado.")

        feature = await self._feature_repo.by_id(feature_id)
        if feature is None:
            raise FeatureNotFoundError(
                feature_id=str(feature_id),
                instance=f"/api/v1/features/{feature_id}/chat",
            )

        discovery_doc = await self._document_repo.get_discovery(feature.project_id)
        if discovery_doc is None:
            raise PhaseTransitionError(
                detail="No existe un documento de descubrimiento para el proyecto.",
                instance=f"/api/v1/features/{feature_id}/chat",
            )

        all_features = await self._feature_repo.list_by_project(feature.project_id)
        other_features = tuple(f for f in all_features if f.id != feature.id)

        return FeatureChatContext(
            feature=feature,
            discovery_document=discovery_doc,
            other_features=other_features,
        )

    async def build_requirement_chat_context(
        self,
        feature_id: FeatureId,
    ) -> RequirementChatContext:
        if self._feature_repo is None:
            raise ValueError("ContextBuilder no tiene FeatureRepository configurado.")
        if self._requirement_repo is None:
            raise ValueError("ContextBuilder no tiene RequirementRepository configurado.")

        feature = await self._feature_repo.by_id(feature_id)
        if feature is None:
            raise FeatureNotFoundError(
                feature_id=str(feature_id),
                instance="/pipeline/requirements/chat",
            )

        discovery_doc = await self._document_repo.get_discovery(feature.project_id)
        if discovery_doc is None:
            raise PhaseTransitionError(
                detail="No existe un documento de descubrimiento para el proyecto.",
                instance="/pipeline/requirements/chat",
            )

        full_markdown = await self._requirement_repo.by_feature_id(feature_id) or ""
        rid = RequirementId(f"req_{feature_id}_chat")
        requirement = parse_requirement_from_markdown(full_markdown, feature_id, feature.number, rid)

        if requirement is None:
            from kosmo.contracts.sdd.ears import EARSPattern, EARSRequirement

            requirement = EARSRequirement(
                id=rid,
                feature_id=feature_id,
                feature_number=feature.number,
                requirement_number=1,
                title=feature.title,
                pattern=EARSPattern.ubiquitous,
                statement=feature.description or "",
                origin=feature.origin or "",
            )

        return RequirementChatContext(
            requirement=requirement,
            feature=feature,
            discovery_document=discovery_doc,
            requirements_markdown=full_markdown,
        )

    async def build_implementation_context(
        self,
        feature_id: FeatureId,
        workspace_manifest: tuple[str, ...] | list[str] = (),
    ) -> ImplementationPhaseContext:
        if self._feature_repo is None:
            raise ValueError("ContextBuilder no tiene FeatureRepository configurado.")
        if self._requirement_repo is None:
            raise ValueError("ContextBuilder no tiene RequirementRepository configurado.")

        feature = await self._feature_repo.by_id(feature_id)
        if feature is None:
            raise FeatureNotFoundError(
                feature_id=str(feature_id),
                instance=f"/pipeline/implementation/{feature_id}",
            )

        requirements_markdown = await self._requirement_repo.by_feature_id(feature_id) or ""

        return ImplementationPhaseContext(
            feature=feature,
            requirements_markdown=requirements_markdown,
            workspace_manifest=tuple(workspace_manifest),
        )
