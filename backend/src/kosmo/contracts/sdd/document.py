from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from kosmo.contracts.sdd.ids import FeatureId


class MarkType(StrEnum):
    bold = "bold"
    italic = "italic"
    code = "code"
    link = "link"
    underline = "underline"
    strikethrough = "strikethrough"


@dataclass(frozen=True)
class TextMark:
    type: MarkType
    attrs: dict[str, Any] = field(default_factory=dict)  # type: ignore[reportUnknownVariableType]


@dataclass(frozen=True)
class SectionHeading:
    text: str
    level: int = 2
    slug: str = ""


@dataclass(frozen=True)
class DocumentNode:
    type: str
    content: str = ""
    heading: SectionHeading | None = None
    marks: list[TextMark] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    children: list[DocumentNode] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    attrs: dict[str, Any] = field(default_factory=dict)  # type: ignore[reportUnknownVariableType]


@dataclass(frozen=True)
class RichTextDocument:
    nodes: list[DocumentNode] = field(default_factory=list)  # type: ignore[reportUnknownVariableType]

    @property
    def sections(self) -> list[SectionHeading]:
        return [node.heading for node in self.nodes if node.type == "heading" and node.heading is not None]

    @property
    def section_count(self) -> int:
        return len(self.sections)


@dataclass(frozen=True)
class FeatureSelection:
    feature_id: FeatureId
    selected: bool = True


@dataclass(frozen=True)
class AcceptanceCriterion:
    scenario: str
    given: str
    when: str
    then: str


class EARSPattern(StrEnum):
    ubiquitous = "Ubicuo"
    event_driven = "Basado en eventos"
    state_driven = "Determinado por estado"
    optional = "Opcional"
    unwanted = "Comportamiento no deseado"
    complex = "Complejo"


class ProjectPhase(StrEnum):
    descubrimiento = "descubrimiento"
    caracteristicas = "caracteristicas"
    requisitos = "requisitos"
    modelo = "modelo"
    implementacion = "implementacion"


class ProjectStatus(StrEnum):
    en_proceso = "en_proceso"
    finalizado = "finalizado"


class SpecPhase(StrEnum):
    DESCUBRIMIENTO = "descubrimiento"
    CARACTERISTICAS = "caracteristicas"
    REQUISITOS = "requisitos"
    MODELO = "modelo"
    IMPLEMENTACION = "implementacion"


SPEC_TO_API_PHASE: dict[SpecPhase, str] = {
    SpecPhase.DESCUBRIMIENTO: "discovery",
    SpecPhase.CARACTERISTICAS: "features",
    SpecPhase.REQUISITOS: "requirements",
    SpecPhase.MODELO: "model",
    SpecPhase.IMPLEMENTACION: "implementation",
}


class EARSPatternLabel(StrEnum):
    ubiquitous = "Requisitos Ubicuos"
    event_driven = "Requisitos Basados en Eventos"
    state_driven = "Requisitos Determinados por el Estado"
    optional = "Requisitos Opcionales"
    unwanted = "Respuesta ante Comportamiento no Deseado"
    complex = "Requisitos Complejos"


EARSPattern_SYNTAX: dict[EARSPattern, str] = {
    EARSPattern.ubiquitous: "[El sistema] debe [comportamiento]",
    EARSPattern.event_driven: "CUANDO [evento], [el sistema] debe [comportamiento]",
    EARSPattern.state_driven: "MIENTRAS [estado], [el sistema] debe [comportamiento]",
    EARSPattern.optional: "DONDE [opción], [el sistema] debe [comportamiento]",
    EARSPattern.unwanted: ("SI [condición no deseada], [el sistema] debe [comportamiento de mitigación]"),
    EARSPattern.complex: "MIENTRAS [estado] Y [evento], [el sistema] debe [comportamiento]",
}


def __getattr__(name: str) -> Any:
    if name == "SuggestedFeature":
        from kosmo.contracts.pipeline.phase_outputs import SuggestedFeature

        return SuggestedFeature
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
