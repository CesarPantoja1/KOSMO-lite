from __future__ import annotations

from dataclasses import dataclass, field

from kosmo.contracts.memory.user_preference import UserPreference
from kosmo.contracts.sdd.document import RichTextDocument, SpecPhase
from kosmo.contracts.sdd.ears import EARSRequirement
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId


@dataclass(frozen=True)
class DiscoveryPhaseContext:
    project_name: str
    project_description: str
    user_preferences: list[UserPreference] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


@dataclass(frozen=True)
class DiscoveryRefinePhaseContext:
    current_document: RichTextDocument
    user_instructions: str
    user_preferences: list[UserPreference] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


@dataclass(frozen=True)
class FeaturesPhaseContext:
    discovery_document: RichTextDocument
    existing_feature_titles: list[str] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    project_id: ProjectId | None = None
    user_preferences: list[UserPreference] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


@dataclass(frozen=True)
class EARSPhaseContext:
    discovery_document: RichTextDocument
    feature: Feature
    feature_number: int
    user_preferences: list[UserPreference] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


@dataclass(frozen=True)
class SuggestFeaturesContext:
    discovery_document: RichTextDocument
    existing_feature_titles: list[str] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    next_feature_number: int = 1
    user_preferences: list[UserPreference] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


@dataclass(frozen=True)
class RequirementsRefinePhaseContext:
    feature: Feature
    feature_number: int
    current_requirements_markdown: str
    user_instructions: str
    user_preferences: list[UserPreference] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


@dataclass(frozen=True)
class ModeloPhaseContext:
    feature_id: FeatureId
    ears_requirements: str
    user_preferences: list[UserPreference] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


@dataclass(frozen=True)
class DiscoveryChatContext:
    current_document: RichTextDocument
    user_preferences: list[UserPreference] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


@dataclass(frozen=True)
class FeatureChatContext:
    feature: Feature
    discovery_document: RichTextDocument
    user_preferences: list[UserPreference] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    other_features: tuple[Feature, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RequirementChatContext:
    requirement: EARSRequirement
    feature: Feature
    discovery_document: RichTextDocument
    requirements_markdown: str = ""
    user_preferences: list[UserPreference] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


@dataclass(frozen=True)
class DirectModificationContext:
    current_document: str
    instruction: str
    document_type: SpecPhase


@dataclass(frozen=True)
class ImplementationPhaseContext:
    feature: Feature
    requirements_markdown: str
    workspace_manifest: tuple[str, ...] = field(default_factory=tuple)  # type: ignore[reportUnknownVariableType]
    user_preferences: list[UserPreference] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]

    @property
    def ears_requirements(self) -> str:
        return self.requirements_markdown

    @property
    def manifest_files(self) -> tuple[str, ...]:
        return self.workspace_manifest


ImplementationContext = ImplementationPhaseContext
