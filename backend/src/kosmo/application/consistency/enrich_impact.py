from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

import structlog
from ulid import ULID

from kosmo.contracts.ai.consistency import (
    ArtifactAction,
    ConsistencyEvaluationOutput,
    ImpactItem,
)
from kosmo.contracts.sdd.document import SPEC_TO_API_PHASE, SpecPhase
from kosmo.contracts.sdd.ears import EARSRequirement
from kosmo.contracts.sdd.ids import FeatureId
from kosmo.contracts.sdd.repositories import (
    ActivityDiagramRepository,
    FeatureRepository,
    RequirementRepository,
)
from kosmo.domain.sdd.requirements_markdown import parse_requirements_markdown
from kosmo.domain.sdd.text_normalizer import normalize_for_match, strip_origin_line

if TYPE_CHECKING:
    from kosmo.contracts.sdd.feature import Feature

_log = structlog.get_logger(__name__)

_LOG_FRAGMENT_LIMIT = 500

_SOURCE_LABEL: dict[SpecPhase, str] = {
    SpecPhase.DESCUBRIMIENTO: "Descubrimiento",
    SpecPhase.CARACTERISTICAS: "Características",
    SpecPhase.REQUISITOS: "Requisitos",
    SpecPhase.MODELO: "Modelo",
    SpecPhase.IMPLEMENTACION: "Implementación",
}


def _find_matching_requirements(
    current_reqs: list[EARSRequirement],
    action: ArtifactAction | None,
) -> list[EARSRequirement]:
    if not current_reqs:
        return []
    if action is None:
        return current_reqs

    field = action.suggested_field or ""
    rationale = action.rationale or ""
    before = action.suggested_before or ""

    matched: list[EARSRequirement] = []
    for r in current_reqs:
        if r.display_id and (r.display_id == field or r.display_id in field):
            matched.append(r)
    if matched:
        return matched

    req_codes = re.findall(r"REQ-\d+\.\d+", rationale)
    if req_codes:
        for r in current_reqs:
            if r.display_id in req_codes:
                matched.append(r)
        if matched:
            return matched

    if before:
        norm_before = normalize_for_match(before)
        for r in current_reqs:
            if (
                norm_before in normalize_for_match(r.statement)
                or norm_before in normalize_for_match(r.title)
                or normalize_for_match(r.statement) in norm_before
            ):
                matched.append(r)
        if matched:
            return matched

    return []


async def enrich_impact_items(
    result: ConsistencyEvaluationOutput,
    target_spec: SpecPhase,
    source_phase: SpecPhase,
    feature_repo: FeatureRepository,
    requirement_repo: RequirementRepository,
    diagram_repo: ActivityDiagramRepository,
) -> list[ImpactItem]:
    items: list[ImpactItem] = []

    action_by_id: dict[str, ArtifactAction] = {}
    for a in result.actions:
        action_by_id[a.artifact_id] = a

    source_label = _SOURCE_LABEL.get(source_phase, source_phase.value)

    if target_spec == SpecPhase.DESCUBRIMIENTO:
        for artifact_id in result.affected_artifact_ids:
            action = action_by_id.get(artifact_id)
            per_rationale = action.rationale if action else result.rationale
            per_action = action.action if action else "update"

            diff: dict[str, object] | None = None
            if action and action.suggested_before and action.suggested_after:
                diff = {
                    "field": action.suggested_field or "content",
                    "before": action.suggested_before,
                    "after": action.suggested_after,
                }

            items.append(
                ImpactItem(
                    id=f"imp_{ULID().hex}",
                    phase=SPEC_TO_API_PHASE[target_spec],
                    target_id=artifact_id,
                    artifact_type="DiscoveryDocument",
                    target_display_id="Documento",
                    target_title="Documento de Descubrimiento",
                    section=action.suggested_field if action else "content",
                    rationale=per_rationale or f"El cambio en {source_label} afecta el documento de Descubrimiento.",
                    diff=diff,
                    action=per_action,
                )
            )
        return items

    unique_fids = list(dict.fromkeys(result.affected_artifact_ids))
    raw_features = await asyncio.gather(*(feature_repo.by_id(FeatureId(fid)) for fid in unique_fids))
    feature_by_id: dict[str, Feature] = {
        fid_str: feat for fid_str, feat in zip(unique_fids, raw_features, strict=False) if feat is not None
    }

    req_md_by_feature_id: dict[FeatureId, str] = {}
    if target_spec == SpecPhase.REQUISITOS and feature_by_id:
        found_features = list(feature_by_id.values())
        raw_reqs = await asyncio.gather(*(requirement_repo.by_feature_id(f.id) for f in found_features))
        req_md_by_feature_id = {f.id: md for f, md in zip(found_features, raw_reqs, strict=False) if md is not None}

    diagram_exists_by_feature_id: dict[FeatureId, bool] = {}
    if target_spec == SpecPhase.MODELO and feature_by_id:
        found_features = list(feature_by_id.values())
        raw_exists = await asyncio.gather(*(diagram_repo.exists(f.id) for f in found_features))
        diagram_exists_by_feature_id = {f.id: exists for f, exists in zip(found_features, raw_exists, strict=False)}

    for fid_str in result.affected_artifact_ids:
        feature = feature_by_id.get(fid_str)
        if feature is None:
            continue

        action = action_by_id.get(fid_str)
        per_rationale = action.rationale if action else result.rationale
        per_action = action.action if action else "update"

        diff: dict[str, object] | None = None
        if action and action.suggested_before and action.suggested_after:
            # El origen es metadato interno: no se muestra al usuario en el diff
            before = strip_origin_line(action.suggested_before)
            after = strip_origin_line(action.suggested_after)
            diff = {
                "field": action.suggested_field or "description",
                "before": before,
                "after": after,
            }

        item_id = f"imp_{ULID().hex}"

        if target_spec == SpecPhase.CARACTERISTICAS:
            items.append(
                ImpactItem(
                    id=item_id,
                    phase=SPEC_TO_API_PHASE[target_spec],
                    target_id=fid_str,
                    artifact_type="Feature",
                    target_display_id=feature.display_id,
                    target_title=feature.title,
                    section=action.suggested_field if action else "title",
                    rationale=per_rationale
                    or (
                        "Esta característica ya no aplica al estado actual."
                        if per_action == "delete"
                        else f"El cambio en {source_label} afecta esta característica."
                    ),
                    diff=diff,
                    action=per_action,
                )
            )
        elif target_spec == SpecPhase.REQUISITOS:
            req_md = req_md_by_feature_id.get(feature.id)
            if req_md is None:
                continue

            current_reqs = parse_requirements_markdown(req_md, feature.id, feature.number)
            current_by_id = {r.display_id: r for r in current_reqs}

            if action and action.suggested_field and action.suggested_field in current_by_id:
                target_req = current_by_id[action.suggested_field]
                diff: dict[str, object] | None = None
                if action.suggested_before and action.suggested_after:
                    diff = {
                        "field": "statement",
                        "before": action.suggested_before,
                        "after": action.suggested_after,
                    }
                items.append(
                    ImpactItem(
                        id=f"imp_{ULID().hex}",
                        phase=SPEC_TO_API_PHASE[target_spec],
                        target_id=fid_str,
                        artifact_type="EARSRequirement",
                        target_display_id=target_req.display_id,
                        target_title=target_req.title,
                        section="statement",
                        rationale=per_rationale or f"El cambio en {source_label} afecta este requisito.",
                        diff=diff,
                        action=per_action,
                    )
                )
            elif action and action.suggested_before and action.suggested_after:
                before_reqs = parse_requirements_markdown(action.suggested_before, feature.id, feature.number)
                after_reqs = parse_requirements_markdown(action.suggested_after, feature.id, feature.number)
                if not before_reqs or not after_reqs:
                    _log.warning(
                        "consistency.enrich_parse_empty",
                        artifact_id=str(feature.id),
                        before_requirements=len(before_reqs),
                        after_requirements=len(after_reqs),
                        suggested_before=action.suggested_before[:_LOG_FRAGMENT_LIMIT],
                        suggested_after=action.suggested_after[:_LOG_FRAGMENT_LIMIT],
                    )

                if before_reqs and after_reqs:
                    before_by_id = {r.display_id: r for r in before_reqs}
                    after_by_id = {r.display_id: r for r in after_reqs}
                    all_ids = sorted(set(before_by_id.keys()) | set(after_by_id.keys()))

                    for req_display_id in all_ids:
                        before_req = before_by_id.get(req_display_id)
                        after_req = after_by_id.get(req_display_id)

                        if before_req and after_req:
                            diff_statement_before = (
                                before_req.statement
                                if before_req.statement != after_req.statement
                                else action.suggested_before
                            )
                            diff_statement_after = (
                                after_req.statement
                                if before_req.statement != after_req.statement
                                else action.suggested_after
                            )
                            per_diff: dict[str, object] | None = {
                                "field": "statement",
                                "before": diff_statement_before,
                                "after": diff_statement_after,
                            }
                            req_action = "update"
                        elif before_req and not after_req:
                            per_diff = None
                            req_action = "delete"
                        elif not before_req and after_req:
                            per_diff = {
                                "field": "statement",
                                "before": "",
                                "after": after_req.statement,
                            }
                            req_action = "create"
                        else:
                            per_diff = None
                            req_action = per_action

                        target_req = before_req or after_req
                        req_title = target_req.title if target_req else req_display_id
                        items.append(
                            ImpactItem(
                                id=f"imp_{ULID().hex}",
                                phase=SPEC_TO_API_PHASE[target_spec],
                                target_id=fid_str,
                                artifact_type="EARSRequirement",
                                target_display_id=req_display_id,
                                target_title=req_title,
                                section="statement",
                                rationale=per_rationale
                                or (
                                    "Se eliminará en cascada al eliminar la característica."
                                    if req_action == "delete"
                                    else f"El cambio en {source_label} afecta este requisito."
                                ),
                                diff=per_diff,
                                action=req_action,
                            )
                        )
                else:
                    matched_reqs = _find_matching_requirements(current_reqs, action)
                    if not matched_reqs and current_reqs:
                        matched_reqs = [current_reqs[0]]

                    if matched_reqs:
                        for req in matched_reqs:
                            items.append(
                                ImpactItem(
                                    id=f"imp_{ULID().hex}",
                                    phase=SPEC_TO_API_PHASE[target_spec],
                                    target_id=fid_str,
                                    artifact_type="EARSRequirement",
                                    target_display_id=req.display_id,
                                    target_title=req.title,
                                    section="statement",
                                    rationale=per_rationale or f"El cambio en {source_label} afecta este requisito.",
                                    diff={
                                        "field": "statement",
                                        "before": action.suggested_before,
                                        "after": action.suggested_after,
                                    },
                                    action=per_action,
                                )
                            )
                    else:
                        items.append(
                            ImpactItem(
                                id=f"imp_{ULID().hex}",
                                phase=SPEC_TO_API_PHASE[target_spec],
                                target_id=fid_str,
                                artifact_type="EARSRequirement",
                                target_display_id=feature.display_id,
                                target_title=f"Requisitos de {feature.title}",
                                section="statement",
                                rationale=per_rationale or f"El cambio en {source_label} afecta este requisito.",
                                diff={
                                    "field": "statement",
                                    "before": action.suggested_before,
                                    "after": action.suggested_after,
                                },
                                action=per_action,
                            )
                        )
            else:
                if per_action == "delete":
                    if current_reqs:
                        for req in current_reqs:
                            items.append(
                                ImpactItem(
                                    id=f"imp_{ULID().hex}",
                                    phase=SPEC_TO_API_PHASE[target_spec],
                                    target_id=fid_str,
                                    artifact_type="EARSRequirement",
                                    target_display_id=req.display_id,
                                    target_title=req.title,
                                    section="statement",
                                    rationale=per_rationale or "Se eliminará en cascada al eliminar la característica.",
                                    diff=None,
                                    action="delete",
                                )
                            )
                    else:
                        items.append(
                            ImpactItem(
                                id=f"imp_{ULID().hex}",
                                phase=SPEC_TO_API_PHASE[target_spec],
                                target_id=fid_str,
                                artifact_type="EARSRequirement",
                                target_display_id=feature.display_id,
                                target_title=f"Requisitos de {feature.title}",
                                section="statement",
                                rationale=per_rationale or "Se eliminará en cascada al eliminar la característica.",
                                diff=None,
                                action="delete",
                            )
                        )
                else:
                    target_display = current_reqs[0].display_id if current_reqs else feature.display_id
                    target_title = current_reqs[0].title if current_reqs else f"Requisitos de {feature.title}"
                    items.append(
                        ImpactItem(
                            id=f"imp_{ULID().hex}",
                            phase=SPEC_TO_API_PHASE[target_spec],
                            target_id=fid_str,
                            artifact_type="EARSRequirement",
                            target_display_id=target_display,
                            target_title=target_title,
                            section="statement",
                            rationale=per_rationale or f"El cambio en {source_label} afecta este requisito.",
                            diff=None,
                            action=per_action,
                        )
                    )
        elif target_spec == SpecPhase.MODELO:
            exists = diagram_exists_by_feature_id.get(feature.id, False)
            if exists:
                items.append(
                    ImpactItem(
                        id=item_id,
                        phase=SPEC_TO_API_PHASE[target_spec],
                        target_id=fid_str,
                        artifact_type="ActivityDiagram",
                        target_display_id=feature.display_id,
                        target_title=f"Diagrama de {feature.title}",
                        section=action.suggested_field if action else "estructura UML",
                        rationale=per_rationale or "El cambio podría requerir actualizar el diagrama de actividad.",
                        diff=diff,
                        action=per_action,
                    )
                )
        elif target_spec == SpecPhase.IMPLEMENTACION:
            items.append(
                ImpactItem(
                    id=item_id,
                    phase=SPEC_TO_API_PHASE[target_spec],
                    target_id=fid_str,
                    artifact_type="FeatureImplementation",
                    target_display_id=feature.display_id,
                    target_title=f"Código de {feature.title}",
                    section=action.suggested_field if action else "código",
                    rationale=per_rationale
                    or f"Los cambios en {source_label} requieren regenerar el código de esta característica.",
                    diff=None,
                    action=per_action,
                )
            )

    return items


def impact_item_to_dict(item: ImpactItem) -> dict[str, object]:
    return {
        "id": item.id,
        "phase": item.phase,
        "targetId": item.target_id,
        "artifact_type": item.artifact_type,
        "targetDisplayId": item.target_display_id,
        "targetTitle": item.target_title,
        "section": item.section,
        "rationale": item.rationale,
        "diff": item.diff,
        "action": item.action,
    }
