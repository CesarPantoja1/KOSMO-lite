from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from kosmo.contracts.sdd.ids import FeatureId, ProjectId


class ImplementationDisposition(StrEnum):
    """Disposición de implementación asignada a una característica en el contexto del producto."""

    CREATE = "create"  # Característica fundacional: crea slice, página y entidades propias
    EXTEND = "extend"  # Extiende entidades/capacidades existentes con nueva funcionalidad o pantalla
    INTEGRATE = "integrate"  # Sub-capacidad integrada en un flujo/página existente (no pantalla aislada)
    COMPOSE = "compose"  # Vista agregadora que compone múltiples entidades y capacidades existentes
    SKIP = "skip"  # Capacidad ya satisfecha por otra característica implementada (idempotente)


@dataclass(frozen=True)
class DomainEntityRef:
    """Referencia a una entidad de dominio compartida entre características."""

    name: str
    description: str = ""
    table_name: str = ""
    feature_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ActorRef:
    """Actor del producto y su rol en la interacción y navegación."""

    name: str
    description: str = ""
    navigation_group: str = ""
    feature_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CapabilityRef:
    """Capacidad funcional provista o consumida por características."""

    name: str
    description: str = ""
    provided_by_feature_id: str = ""
    consumed_by_feature_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProductFlowStep:
    """Paso individual dentro de un flujo de usuario."""

    step_number: int
    feature_id: str
    description: str
    actor: str = ""


@dataclass(frozen=True)
class ProductFlow:
    """Flujo de interacción de usuario de extremo a extremo."""

    name: str
    description: str = ""
    actor: str = ""
    steps: tuple[ProductFlowStep, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FeatureDisposition:
    """Disposición de integración para una característica específica."""

    feature_id: str
    disposition: ImplementationDisposition = ImplementationDisposition.CREATE
    target_feature_id: str | None = None
    target_path: str | None = None
    shared_entities: tuple[str, ...] = field(default_factory=tuple)
    shared_capabilities: tuple[str, ...] = field(default_factory=tuple)
    actor: str | None = None
    actors: tuple[str, ...] = field(default_factory=tuple)
    navigation_group: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class ProductMap:
    """Mapa integral del producto que representa relaciones entre características, entidades, actores y flujos."""

    project_id: ProjectId
    entities: tuple[DomainEntityRef, ...] = field(default_factory=tuple)
    actors: tuple[ActorRef, ...] = field(default_factory=tuple)
    capabilities: tuple[CapabilityRef, ...] = field(default_factory=tuple)
    flows: tuple[ProductFlow, ...] = field(default_factory=tuple)
    dispositions: dict[str, FeatureDisposition] = field(default_factory=lambda: dict[str, FeatureDisposition]())
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def get_disposition(self, feature_id: FeatureId | str) -> FeatureDisposition:
        """Obtiene la disposición asignada a una característica o retorna CREATE por defecto."""
        key = str(feature_id)
        return self.dispositions.get(
            key,
            FeatureDisposition(feature_id=key, disposition=ImplementationDisposition.CREATE),
        )

    def get_entities_for_feature(self, feature_id: FeatureId | str) -> tuple[DomainEntityRef, ...]:
        """Retorna las entidades de dominio asociadas a una característica."""
        f_id = str(feature_id)
        return tuple(e for e in self.entities if f_id in e.feature_ids)

    def get_actor_for_feature(self, feature_id: FeatureId | str) -> ActorRef | None:
        """Retorna el actor principal asociado a una característica si existe."""
        f_id = str(feature_id)
        for actor in self.actors:
            if f_id in actor.feature_ids:
                return actor
        return None

    def get_actors_for_feature(self, feature_id: FeatureId | str) -> tuple[ActorRef, ...]:
        """Retorna todos los actores asociados a una característica."""
        f_id = str(feature_id)
        return tuple(actor for actor in self.actors if f_id in actor.feature_ids)
