from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from kosmo.contracts.sdd.document import RichTextDocument
from kosmo.contracts.sdd.ears import EARSRequirement
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId


@dataclass(frozen=True)
class GenerationMetadata:
    llm_calls: int = 0
    total_tokens: int = 0
    retry_count: int = 0
    reasoning_log: list[str] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    tool_results: list[dict[str, Any]] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    generation_time_ms: int = 0
    model_used: str = ""


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    warnings: list[str] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    quality_score: float | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class DiscoveryPhaseOutput:
    discovery_document: RichTextDocument
    validation_result: ValidationResult
    generation_metadata: GenerationMetadata


@dataclass(frozen=True)
class FeaturesPhaseOutput:
    features: list[Feature]
    validation_result: ValidationResult
    generation_metadata: GenerationMetadata


@dataclass(frozen=True)
class SuggestFeaturesOutput:
    suggestions: list[SuggestedFeature]
    excluded_titles: list[str]
    domain_inferred: str


@dataclass(frozen=True)
class SuggestedFeature:
    number: int
    title: str
    description: str
    origin: str = ""


@dataclass(frozen=True)
class EARSPhaseOutput:
    feature_id: FeatureId
    feature_number: int
    requirements: list[EARSRequirement]
    requirements_markdown: str
    validation_result: ValidationResult
    generation_metadata: GenerationMetadata


# ── Modelos de salida estructurada del LLM (pydantic-ai output_type) ──


class DiscoveryDocument(BaseModel):
    document: str = Field(description="Documento de descubrimiento completo en markdown")


class FeatureSpec(BaseModel):
    number: int
    title: str
    description: str
    origin: str


class FeatureSet(BaseModel):
    features: list[FeatureSpec] = Field(description="Lista de caracteristicas generadas")


class AcceptanceCriterionSpec(BaseModel):
    scenario: str
    given: str
    when: str
    then: str


class EARSRequirementSpec(BaseModel):
    code: str
    title: str
    pattern: str
    statement: str
    origin: str
    acceptance_criteria: list[AcceptanceCriterionSpec]


class EARSSet(BaseModel):
    requirements: list[EARSRequirementSpec]


class RequirementsDocument(BaseModel):
    requirements_markdown: str = Field(description="Documento de requisitos completo en markdown")


class ConsistencyAction(BaseModel):
    artifact_id: str
    action: str = "update"
    rationale: str = ""
    suggested_field: str = ""
    suggested_before: str = ""
    suggested_after: str = ""


class ConsistencyReport(BaseModel):
    actions: list[ConsistencyAction] = Field(default_factory=list[ConsistencyAction])
    overall_rationale: str = ""


class ConsistencyDetectionAction(BaseModel):
    artifact_id: str
    action: str = "update"
    rationale: str = ""
    suggested_field: str = ""


class ConsistencyDetectionReport(BaseModel):
    actions: list[ConsistencyDetectionAction] = Field(default_factory=list[ConsistencyDetectionAction])
    overall_rationale: str = ""


class ConsistencyCorrection(BaseModel):
    suggested_field: str = ""
    suggested_before: str = ""
    suggested_after: str = ""


class ResolvedSection(BaseModel):
    section_markdown: str = Field(description="Sección completa reescrita con todos los cambios aplicados")


class DirectModificationResult(BaseModel):
    applied: bool = Field(description="True si la modificación fue aplicada al documento")
    modified_document: str = Field(default="", description="Documento completo actualizado en markdown")
    modified_section: str = Field(default="", description="Nombre de la sección modificada")
    change_description: str = Field(default="", description="Descripción breve del cambio aplicado")
    clarification_message: str = Field(
        default="",
        description="Mensaje solicitando detalle cuando la instrucción es ambigua (solo si applied=false)",
    )
