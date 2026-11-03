from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from kosmo.contracts.pipeline.consistency_phase_context import ConsistencyPhaseContext
from kosmo.contracts.pipeline.phase_contexts import (
    DirectModificationContext,
    DiscoveryChatContext,
    DiscoveryPhaseContext,
    DiscoveryRefinePhaseContext,
    EARSPhaseContext,
    FeatureChatContext,
    FeaturesPhaseContext,
    RequirementChatContext,
    RequirementsRefinePhaseContext,
    SuggestFeaturesContext,
)
from kosmo.contracts.pipeline.phase_outputs import (
    DirectModificationResult,
    GenerationMetadata,
    ValidationResult,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import AgentMemoryId, ProjectId

if TYPE_CHECKING:
    from kosmo.contracts.ai.chat import MensajeChat


PhaseContext = (
    ConsistencyPhaseContext
    | DirectModificationContext
    | DiscoveryChatContext
    | DiscoveryPhaseContext
    | DiscoveryRefinePhaseContext
    | EARSPhaseContext
    | FeatureChatContext
    | FeaturesPhaseContext
    | RequirementChatContext
    | RequirementsRefinePhaseContext
    | SuggestFeaturesContext
)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)  # type: ignore[reportUnknownVariableType]


@dataclass(frozen=True)
class Skill:
    """Habilidad del agente que encapsula un modo de fase con metadatos.

    Cada skill agrupa un PhaseMode con su nombre, descripcion y fase asociada,
    permitiendo cargar, descargar y resolver habilidades bajo demanda sin
    modificar el nucleo del agente.
    """

    name: str
    description: str
    phase: SpecPhase
    mode: PhaseMode


class PhaseMode(Protocol):
    @property
    def phase_name(self) -> SpecPhase: ...

    @property
    def system_prompt(self) -> str: ...

    @property
    def temperature(self) -> float: ...

    @property
    def max_tokens(self) -> int: ...

    @property
    def output_type(self) -> type[Any]: ...

    def build_user_prompt(
        self,
        context: PhaseContext,
    ) -> str: ...

    def validate_output(self, output: Any, *, context: Any = None) -> ValidationResult: ...

    def build_retry_prompt(
        self,
        original_prompt: str,
        errors: list[str],
        retry_count: int,
    ) -> str: ...

    def build_validation_feedback(self, errors: list[str]) -> str: ...

    def build_output(
        self,
        raw_output: Any,
        validation_result: ValidationResult,
        metadata: GenerationMetadata,
        *,
        context: Any = None,
    ) -> Any: ...


class AgentPort(Protocol):
    async def execute_with_skill(
        self,
        skill_name: str,
        context: PhaseContext,
        *,
        project_id: ProjectId | None = None,
        user_instructions: str | None = None,
    ) -> Any: ...

    async def execute_conversation(
        self,
        skill_name: str,
        messages: list[MensajeChat],
        context: PhaseContext,
        *,
        project_id: ProjectId | None = None,
    ) -> MensajeChat: ...

    async def execute_direct_modification(
        self,
        skill_name: str,
        context: DirectModificationContext,
        *,
        history: list[MensajeChat] | None = None,
        project_id: ProjectId | None = None,
    ) -> DirectModificationResult: ...

    def execute_conversation_stream(
        self,
        skill_name: str,
        messages: list[MensajeChat],
        context: PhaseContext,
        *,
        project_id: ProjectId | None = None,
    ) -> AsyncIterator[Any]: ...

    async def reflect_and_consolidate(
        self,
        *,
        session_id: AgentMemoryId,
        phase: SpecPhase,
        session_type: str,
        is_completed: bool,
        current_iteration: int,
        validation: ValidationResult,
    ) -> None: ...
