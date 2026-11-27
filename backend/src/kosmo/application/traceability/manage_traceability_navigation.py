from __future__ import annotations

from dataclasses import dataclass

from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.errors import FeatureNotFoundError
from kosmo.contracts.sdd.ids import FeatureId
from kosmo.contracts.sdd.repositories import FeatureRepository


@dataclass(frozen=True)
class TraceabilityNavigationInput:
    entity_id: str
    level: SpecPhase


@dataclass(frozen=True)
class TraceabilityNavigationOutput:
    permitted: bool
    redirect_message: str | None = None
    source_entity_name: str | None = None
    source_entity_id: str | None = None
    source_level: str | None = None


class ManageTraceabilityNavigationUseCase:
    def __init__(self, feature_repo: FeatureRepository) -> None:
        self._feature_repo = feature_repo

    async def execute(self, input_data: TraceabilityNavigationInput) -> TraceabilityNavigationOutput:
        if input_data.level in (SpecPhase.DESCUBRIMIENTO, SpecPhase.CARACTERISTICAS):
            return TraceabilityNavigationOutput(permitted=True)

        feature = await self._feature_repo.by_id(FeatureId(input_data.entity_id))
        if feature is None:
            raise FeatureNotFoundError(feature_id=input_data.entity_id)

        if input_data.level == SpecPhase.REQUISITOS:
            return TraceabilityNavigationOutput(
                permitted=False,
                redirect_message=(
                    f"El requisito pertenece a la característica '{feature.title}'. "
                    "Para editarlo, dirígete a la vista de características."
                ),
                source_entity_name=feature.title,
                source_entity_id=str(feature.id),
                source_level=SpecPhase.CARACTERISTICAS.value,
            )

        if input_data.level == SpecPhase.IMPLEMENTACION:
            return TraceabilityNavigationOutput(
                permitted=False,
                redirect_message=(
                    f"La implementación de '{feature.title}' se genera a partir de sus requisitos. "
                    "Para editarlo, dirígete a la vista de requisitos."
                ),
                source_entity_name=feature.title,
                source_entity_id=str(feature.id),
                source_level=SpecPhase.REQUISITOS.value,
            )

        return TraceabilityNavigationOutput(permitted=True)
