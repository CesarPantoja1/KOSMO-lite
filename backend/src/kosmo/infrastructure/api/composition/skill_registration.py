from __future__ import annotations

from kosmo.contracts.pipeline.orchestrator_ports import Skill
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.domain.pipeline.phase_modes.consistency_evaluation_mode import (
    CONSISTENCY_DISCOVERY_MODEL_PROMPT,
    CONSISTENCY_DISCOVERY_REQUIREMENTS_PROMPT,
    CONSISTENCY_FEATURES_DOWNSTREAM_SYSTEM_PROMPT,
    CONSISTENCY_FEATURES_MODEL_PROMPT,
    CONSISTENCY_REQUIREMENTS_DOWNSTREAM_SYSTEM_PROMPT,
    CONSISTENCY_REQUIREMENTS_MODEL_SYSTEM_PROMPT,
    CONSISTENCY_REQUIREMENTS_UPSTREAM_SYSTEM_PROMPT,
    CONSISTENCY_UPSTREAM_SYSTEM_PROMPT,
    ConsistencyCorrectionMode,
    ConsistencyEvaluationMode,
)
from kosmo.domain.pipeline.phase_modes.direct_modification_mode import (
    DirectModificationMode,
)
from kosmo.domain.pipeline.phase_modes.discovery_chat_mode import DiscoveryChatMode
from kosmo.domain.pipeline.phase_modes.discovery_mode import DiscoveryMode
from kosmo.domain.pipeline.phase_modes.discovery_refine_mode import (
    DiscoveryRefineMode,
)
from kosmo.domain.pipeline.phase_modes.ears_mode import EARSMode
from kosmo.domain.pipeline.phase_modes.features_chat_mode import FeaturesChatMode
from kosmo.domain.pipeline.phase_modes.features_mode import FeaturesMode
from kosmo.domain.pipeline.phase_modes.modelo_mode import ModeloMode
from kosmo.domain.pipeline.phase_modes.requirements_chat_mode import RequirementsChatMode
from kosmo.domain.pipeline.phase_modes.requirements_refine_mode import (
    RequirementsRefineMode,
)
from kosmo.domain.pipeline.skill_registry import SkillRegistry


def build_skill_registry() -> SkillRegistry:
    skill_registry = SkillRegistry()
    skill_registry.register(
        Skill(
            name="discovery_generate",
            description="Genera el documento de descubrimiento desde cero",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=DiscoveryMode(),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="discovery_refine",
            description="Refina el documento de descubrimiento existente",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=DiscoveryRefineMode(),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="features_generate",
            description="Genera caracteristicas a partir del descubrimiento",
            phase=SpecPhase.CARACTERISTICAS,
            mode=FeaturesMode(),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="ears_generate",
            description="Genera requisitos EARS para una caracteristica",
            phase=SpecPhase.REQUISITOS,
            mode=EARSMode(),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="requirements_refine",
            description="Refina requisitos EARS existentes",
            phase=SpecPhase.REQUISITOS,
            mode=RequirementsRefineMode(),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="modelo_generate",
            description="Genera diagrama de actividad UML desde requisitos EARS",
            phase=SpecPhase.MODELO,
            mode=ModeloMode(),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="discovery_chat",
            description="Chat conversacional de descubrimiento a nivel de negocio",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=DiscoveryChatMode(),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="features_chat",
            description="Chat conversacional de característica a nivel de usuario",
            phase=SpecPhase.CARACTERISTICAS,
            mode=FeaturesChatMode(),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="requirements_chat",
            description="Chat conversacional de requisito EARS a nivel de software",
            phase=SpecPhase.REQUISITOS,
            mode=RequirementsChatMode(),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate",
            description="Evalua consistencia entre fases y determina artefactos afectados downstream",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=ConsistencyEvaluationMode(),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate_upstream",
            description="Evalua consistencia desde características hacia el documento de descubrimiento (upstream)",
            phase=SpecPhase.CARACTERISTICAS,
            mode=ConsistencyEvaluationMode(
                phase_name=SpecPhase.CARACTERISTICAS, system_prompt=CONSISTENCY_UPSTREAM_SYSTEM_PROMPT
            ),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate_requirements",
            description="Evalua consistencia desde requisitos EARS hacia la característica padre (downstream)",
            phase=SpecPhase.REQUISITOS,
            mode=ConsistencyEvaluationMode(
                phase_name=SpecPhase.REQUISITOS,
                system_prompt=CONSISTENCY_REQUIREMENTS_DOWNSTREAM_SYSTEM_PROMPT,
            ),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate_requirements_upstream",
            description="Evalua consistencia desde requisitos EARS hacia el documento de descubrimiento (upstream)",
            phase=SpecPhase.REQUISITOS,
            mode=ConsistencyEvaluationMode(
                phase_name=SpecPhase.REQUISITOS,
                system_prompt=CONSISTENCY_REQUIREMENTS_UPSTREAM_SYSTEM_PROMPT,
            ),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate_features_downstream",
            description="Evalua consistencia desde características hacia requisitos EARS (downstream)",
            phase=SpecPhase.CARACTERISTICAS,
            mode=ConsistencyEvaluationMode(
                phase_name=SpecPhase.CARACTERISTICAS,
                system_prompt=CONSISTENCY_FEATURES_DOWNSTREAM_SYSTEM_PROMPT,
            ),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate_features_model",
            description="Evalua consistencia desde características hacia diagramas de actividad (downstream)",
            phase=SpecPhase.CARACTERISTICAS,
            mode=ConsistencyEvaluationMode(
                phase_name=SpecPhase.CARACTERISTICAS,
                system_prompt=CONSISTENCY_FEATURES_MODEL_PROMPT,
            ),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate_discovery_requirements",
            description="Evalua consistencia desde descubrimiento hacia requisitos EARS (downstream)",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=ConsistencyEvaluationMode(
                phase_name=SpecPhase.DESCUBRIMIENTO,
                system_prompt=CONSISTENCY_DISCOVERY_REQUIREMENTS_PROMPT,
            ),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate_discovery_model",
            description="Evalua consistencia desde descubrimiento hacia diagramas de actividad (downstream)",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=ConsistencyEvaluationMode(
                phase_name=SpecPhase.DESCUBRIMIENTO,
                system_prompt=CONSISTENCY_DISCOVERY_MODEL_PROMPT,
            ),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate_discovery_features",
            description="Evalua consistencia desde descubrimiento hacia características (downstream)",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=ConsistencyEvaluationMode(
                phase_name=SpecPhase.DESCUBRIMIENTO,
            ),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate_discovery_implementation",
            description="Evalua impacto de descubrimiento en implementaciones de código (downstream)",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=ConsistencyEvaluationMode(
                phase_name=SpecPhase.DESCUBRIMIENTO,
            ),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate_features_implementation",
            description="Evalua impacto de características en implementaciones de código (downstream)",
            phase=SpecPhase.CARACTERISTICAS,
            mode=ConsistencyEvaluationMode(
                phase_name=SpecPhase.CARACTERISTICAS,
            ),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate_requirements_implementation",
            description="Evalua impacto de requisitos en implementaciones de código (downstream)",
            phase=SpecPhase.REQUISITOS,
            mode=ConsistencyEvaluationMode(
                phase_name=SpecPhase.REQUISITOS,
            ),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate_requirements_model",
            description="Evalua consistencia desde requisitos EARS hacia el diagrama de actividad (downstream)",
            phase=SpecPhase.REQUISITOS,
            mode=ConsistencyEvaluationMode(
                phase_name=SpecPhase.REQUISITOS,
                system_prompt=CONSISTENCY_REQUIREMENTS_MODEL_SYSTEM_PROMPT,
            ),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_evaluate_model_implementation",
            description="Evalua impacto de modelo/diagrama en implementaciones de código (downstream)",
            phase=SpecPhase.MODELO,
            mode=ConsistencyEvaluationMode(
                phase_name=SpecPhase.MODELO,
            ),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="consistency_correct",
            description="Genera la correccion textual exacta de un artefacto afectado por un cambio de consistencia",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=ConsistencyCorrectionMode(),  # type: ignore[reportArgumentType]
        )
    )
    skill_registry.register(
        Skill(
            name="direct_modification",
            description="Modifica documentos directamente desde instrucciones del chat sin fase de plan",
            phase=SpecPhase.DESCUBRIMIENTO,
            mode=DirectModificationMode(),  # type: ignore[reportArgumentType]
        )
    )
    return skill_registry
