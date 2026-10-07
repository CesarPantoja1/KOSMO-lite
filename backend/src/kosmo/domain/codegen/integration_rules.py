from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import ProjectId
from kosmo.contracts.sdd.product_map import (
    ActorRef,
    CapabilityRef,
    DomainEntityRef,
    FeatureDisposition,
    ImplementationDisposition,
    ProductFlow,
    ProductFlowStep,
    ProductMap,
)

_STOPWORDS = frozenset(
    {
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "de",
        "del",
        "al",
        "y",
        "o",
        "e",
        "u",
        "en",
        "para",
        "por",
        "con",
        "sin",
        "sobre",
        "tras",
        "desde",
        "hasta",
        "que",
        "es",
        "son",
        "este",
        "esta",
        "estos",
        "estas",
        "como",
        "quiero",
        "sistema",
        "usuario",
        "permite",
        "debe",
        "poder",
        "funcionalidad",
        "caracteristica",
        "proyecto",
        "gestionar",
        "administrar",
    }
)

_STEP_KEYWORDS = frozenset(
    {
        "terminos",
        "condiciones",
        "consentimiento",
        "confirmacion",
        "politicas",
        "aviso",
        "captcha",
        "verificacion",
    }
)

_COMPOSITION_KEYWORDS = frozenset(
    {
        "dashboard",
        "panel",
        "resumen",
        "metricas",
        "kpi",
        "balance",
        "vista global",
        "estadisticas",
        "consolidado",
    }
)


def _normalize_tokens(text: str) -> set[str]:
    text = text.lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s]", " ", text)
    words = text.split()
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    if not set_a or not set_b:
        return 0.0
    return len(set_a.intersection(set_b)) / len(set_a.union(set_b))


@dataclass(frozen=True)
class OverlapDetection:
    feature_a_id: str
    feature_b_id: str
    similarity: float
    shared_tokens: tuple[str, ...]
    is_subcapability: bool = False
    message: str = ""


def detect_capability_overlap(
    feature: Feature,
    other_features: Iterable[Feature],
) -> tuple[OverlapDetection, ...]:
    """Detecta solapamientos y relaciones de sub-capacidad entre una feature y otras."""
    feat_tokens = _normalize_tokens(f"{feature.title} {feature.description}")
    overlaps: list[OverlapDetection] = []

    for other in other_features:
        if str(other.id) == str(feature.id):
            continue
        other_tokens = _normalize_tokens(f"{other.title} {other.description}")
        shared = tuple(sorted(feat_tokens.intersection(other_tokens)))
        sim = _jaccard_similarity(feat_tokens, other_tokens)

        # Verificar si la feature actual parece una sub-capacidad de la otra
        has_step_kw = bool(feat_tokens.intersection(_STEP_KEYWORDS))
        is_sub = (has_step_kw and bool(shared)) or (has_step_kw and len(feat_tokens) <= len(other_tokens))

        if sim > 0.35 or is_sub:
            overlaps.append(
                OverlapDetection(
                    feature_a_id=str(feature.id),
                    feature_b_id=str(other.id),
                    similarity=sim,
                    shared_tokens=shared,
                    is_subcapability=is_sub,
                    message=(
                        f"La característica '{feature.title}' tiene solapamiento ({sim:.2f}) "
                        f"o actúa como sub-capacidad de '{other.title}'"
                    ),
                )
            )

    return tuple(overlaps)


def extract_actors_from_discovery(discovery_text: str) -> tuple[str, ...]:
    """Extrae los nombres de actores definidos en la sección '## Actores' del Discovery."""
    actors: list[str] = []
    if "## Actores" in discovery_text:
        section = discovery_text.split("## Actores")[1].split("##")[0]
        for line in section.split("\n"):
            line = line.strip()
            if line.startswith("-") or line.startswith("*"):
                clean = line.lstrip("-* ").replace("**", "").strip()
                actor_name = clean.split(":")[0].split(" - ")[0].strip()
                if actor_name and actor_name not in actors:
                    actors.append(actor_name)
    return tuple(actors)


def _strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()


def extract_actors_from_text(
    origin: str,
    description: str,
    discovery_actors: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Infiere todos los actores involucrados a partir de discovery_actors o del texto."""
    combined_clean = _strip_accents(f"{origin} {description}")
    found: list[str] = []

    # 1. Si hay discovery_actors, verificar si alguno se menciona
    if discovery_actors:
        for d_act in discovery_actors:
            d_clean = _strip_accents(d_act)
            if d_clean and d_clean in combined_clean and d_act not in found:
                found.append(d_act)

    # 2. Buscar actores comunes conocidos
    common_actors = [
        ("administrador", "Administrador"),
        ("admin", "Administrador"),
        ("cliente", "Cliente"),
        ("paciente", "Paciente"),
        ("doctor", "Doctor"),
        ("medico", "Médico"),
        ("empleado", "Empleado"),
        ("vendedor", "Vendedor"),
        ("comprador", "Comprador"),
        ("estudiante", "Estudiante"),
        ("profesor", "Profesor"),
        ("participante", "Participante"),
        ("usuario", "Usuario"),
    ]
    for key, label in common_actors:
        if key in combined_clean and label not in found:
            found.append(label)

    if not found:
        return ("General",)
    return tuple(found)


def extract_actor_from_text(
    origin: str,
    description: str,
    discovery_actors: Sequence[str] | None = None,
) -> str:
    """Infiere el actor principal de una feature a partir del origin o la descripción."""
    actors = extract_actors_from_text(origin, description, discovery_actors)
    return actors[0]


def infer_domain_entities(features: Sequence[Feature]) -> tuple[DomainEntityRef, ...]:
    """Infiere entidades de dominio compartidas a partir de sustantivos comunes en los títulos y descripciones."""
    token_feature_map: dict[str, set[str]] = {}
    for feat in features:
        tokens = _normalize_tokens(f"{feat.title} {feat.description}")
        for t in tokens:
            token_feature_map.setdefault(t, set()).add(str(feat.id))

    # Aquellas palabras que aparecen en 2 o más features representan entidades de dominio compartidas
    entities: list[DomainEntityRef] = []
    for token, f_ids in token_feature_map.items():
        if len(f_ids) >= 2 and token not in _STEP_KEYWORDS and token not in _COMPOSITION_KEYWORDS:
            capitalized = token.capitalize()
            entities.append(
                DomainEntityRef(
                    name=capitalized,
                    description=f"Entidad de dominio compartida vinculada a {len(f_ids)} características",
                    table_name=f"{token}s" if not token.endswith("s") else token,
                    feature_ids=tuple(sorted(f_ids)),
                )
            )

    return tuple(sorted(entities, key=lambda e: (-len(e.feature_ids), e.name)))


def determine_feature_disposition(
    feature: Feature,
    existing_features: Sequence[Feature],
    implemented_feature_ids: set[str],
    discovery_actors: Sequence[str] | None = None,
) -> FeatureDisposition:
    """Calcula determinísticamente la disposición de implementación de una feature."""
    f_tokens = _normalize_tokens(f"{feature.title} {feature.description}")
    actors = extract_actors_from_text(feature.origin, feature.description, discovery_actors)
    actor = actors[0]
    nav_group = f"Área {actor}" if actor != "General" else "Navegación"

    # 1. ¿Es una vista de composición agregadora (Dashboard, Reporte)?
    if any(k in f_tokens for k in _COMPOSITION_KEYWORDS):
        return FeatureDisposition(
            feature_id=str(feature.id),
            disposition=ImplementationDisposition.COMPOSE,
            actor=actor,
            actors=actors,
            navigation_group=nav_group,
            reason="Vista compuesta que consolida métricas o información de múltiples fuentes",
        )

    # 2. ¿Es una sub-capacidad que se integra en un flujo existente (e.g. T&C)?
    if any(k in f_tokens for k in _STEP_KEYWORDS):
        # Buscar la feature con la que tiene mayor solapamiento o flujo previo
        for other in existing_features:
            if str(other.id) != str(feature.id):
                other_tokens = _normalize_tokens(f"{other.title} {other.description}")
                if str(other.id) in implemented_feature_ids:
                    return FeatureDisposition(
                        feature_id=str(feature.id),
                        disposition=ImplementationDisposition.INTEGRATE,
                        target_feature_id=str(other.id),
                        actor=actor,
                        actors=actors,
                        navigation_group=nav_group,
                        reason=f"Sub-capacidad que se integra dentro del flujo de '{other.title}'",
                    )

    # 3. ¿Comparte entidades ya implementadas en el proyecto?
    shared_entities: list[str] = []
    for other in existing_features:
        if str(other.id) in implemented_feature_ids and str(other.id) != str(feature.id):
            other_tokens = _normalize_tokens(f"{other.title} {other.description}")
            common = f_tokens.intersection(other_tokens)
            if common:
                shared_entities.extend(sorted(common))

    if shared_entities and implemented_feature_ids:
        return FeatureDisposition(
            feature_id=str(feature.id),
            disposition=ImplementationDisposition.EXTEND,
            shared_entities=tuple(sorted(set(shared_entities))),
            actor=actor,
            actors=actors,
            navigation_group=nav_group,
            reason="Extiende entidades y modelos existentes sin duplicar persistencia",
        )

    # 4. Por defecto, es una creación de feature fundacional
    return FeatureDisposition(
        feature_id=str(feature.id),
        disposition=ImplementationDisposition.CREATE,
        actor=actor,
        actors=actors,
        navigation_group=nav_group,
        reason="Característica fundacional con entidades y rutas primarias propias",
    )


def build_product_map(
    project_id: ProjectId,
    features: Sequence[Feature],
    implemented_feature_ids: set[str] | None = None,
    discovery_actors: Sequence[str] | None = None,
) -> ProductMap:
    """Construye un ProductMap consolidado a partir de la lista de características y descubrimiento."""
    impl_ids = implemented_feature_ids or set()
    entities = infer_domain_entities(features)

    # Actores y grupos de navegación
    actor_feature_map: dict[str, list[str]] = {}
    if discovery_actors:
        for d_act in discovery_actors:
            actor_feature_map[d_act] = []

    for feat in features:
        feat_actors = extract_actors_from_text(feat.origin, feat.description, discovery_actors)
        for act in feat_actors:
            actor_feature_map.setdefault(act, []).append(str(feat.id))

    actors_list: list[ActorRef] = []
    for act_name, f_ids in actor_feature_map.items():
        group_label = f"Área {act_name}" if act_name != "General" else "General"
        actors_list.append(
            ActorRef(
                name=act_name,
                navigation_group=group_label,
                feature_ids=tuple(f_ids),
            )
        )

    # Disposiciones por feature
    dispositions: dict[str, FeatureDisposition] = {}
    for feat in features:
        disp = determine_feature_disposition(
            feature=feat,
            existing_features=features,
            implemented_feature_ids=impl_ids,
            discovery_actors=discovery_actors,
        )
        dispositions[str(feat.id)] = disp

    # Capacidades inferidas
    capabilities: list[CapabilityRef] = []
    for feat in features:
        cap_name = feat.slug.replace("-", "_")
        consumed = tuple(other_id for other_id, d in dispositions.items() if d.target_feature_id == str(feat.id))
        capabilities.append(
            CapabilityRef(
                name=cap_name,
                description=feat.title,
                provided_by_feature_id=str(feat.id),
                consumed_by_feature_ids=consumed,
            )
        )

    # Flujos inferidos por actor
    flows: list[ProductFlow] = []
    for act in actors_list:
        if act.feature_ids:
            steps = tuple(
                ProductFlowStep(
                    step_number=idx + 1,
                    feature_id=fid,
                    description=next((f.title for f in features if str(f.id) == fid), fid),
                    actor=act.name,
                )
                for idx, fid in enumerate(act.feature_ids)
            )
            flows.append(
                ProductFlow(
                    name=f"Flujo de {act.name}",
                    actor=act.name,
                    steps=steps,
                )
            )

    return ProductMap(
        project_id=project_id,
        entities=entities,
        actors=tuple(actors_list),
        capabilities=tuple(capabilities),
        flows=tuple(flows),
        dispositions=dispositions,
    )
