from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

import structlog
from ulid import ULID

from kosmo.application.consistency.enrich_impact import enrich_impact_items, impact_item_to_dict
from kosmo.contracts import ConsistencyEvaluator
from kosmo.contracts.ai.chat import AppliedChange
from kosmo.contracts.ai.consistency import DOWNSTREAM_TARGETS, ConsistencyStatus
from kosmo.contracts.sdd.document import SPEC_TO_API_PHASE, SpecPhase
from kosmo.contracts.sdd.errors import ProjectNotFoundError
from kosmo.contracts.sdd.ids import ProjectId
from kosmo.contracts.sdd.repositories import (
    ActivityDiagramRepository,
    FeatureRepository,
    ProjectRepository,
    RequirementRepository,
)

_log = structlog.get_logger(__name__)

_ImpactItemDict = dict[str, object]
_ImpactList = list[_ImpactItemDict]


@dataclass(frozen=True)
class CascadingConsistencyOutput:
    report_id: str
    source_type: str
    source_id: str
    downstream_impact: _ImpactList = field(default_factory=list)  # type: ignore[reportUnknownVariableType]
    your_changes: _ImpactList = field(default_factory=list)  # type: ignore[reportUnknownVariableType]


class CascadingConsistencyUseCase:
    def __init__(
        self,
        project_repo: ProjectRepository,
        feature_repo: FeatureRepository,
        requirement_repo: RequirementRepository,
        diagram_repo: ActivityDiagramRepository,
        evaluator: ConsistencyEvaluator,
    ) -> None:
        self._project_repo = project_repo
        self._feature_repo = feature_repo
        self._requirement_repo = requirement_repo
        self._diagram_repo = diagram_repo
        self._evaluator = evaluator

    async def execute(
        self,
        project_id: ProjectId,
        source_phase: SpecPhase,
        applied_changes: list[AppliedChange],
    ) -> CascadingConsistencyOutput:
        report_id = f"cnr_{ULID().hex}"
        project = await self._project_repo.by_id(project_id)
        if project is None:
            raise ProjectNotFoundError(
                project_id=str(project_id),
                instance=f"/api/v1/projects/{project_id}/consistency",
            )

        source_api = SPEC_TO_API_PHASE[source_phase]
        targets = DOWNSTREAM_TARGETS[source_phase]

        async def _eval_and_enrich(target_spec: SpecPhase) -> _ImpactList:
            try:
                result = await self._evaluator.evaluate(
                    source_phase=source_phase,
                    target_phase=target_spec,
                    project_id=project_id,
                    applied_changes=applied_changes,
                )
            except Exception:
                _log.warning(
                    "cascade.evaluate_failed",
                    project_id=str(project_id),
                    target=target_spec.value,
                    exc_info=True,
                )
                return []

            if not result.affected_artifact_ids:
                return []

            try:
                items = await enrich_impact_items(
                    result,
                    target_spec,
                    source_phase,
                    self._feature_repo,
                    self._requirement_repo,
                    self._diagram_repo,
                )
                return [impact_item_to_dict(item) for item in items]
            except Exception:
                _log.warning(
                    "cascade.enrich_failed",
                    project_id=str(project_id),
                    target=target_spec.value,
                    exc_info=True,
                )
                return []

        gathered: list[list[dict[str, object]] | BaseException] = await asyncio.gather(
            *[_eval_and_enrich(t) for t in targets],
            return_exceptions=True,
        )

        downstream: _ImpactList = []
        for items in gathered:
            if isinstance(items, list):
                downstream.extend(items)

        your_changes: list[dict[str, object]] = [
            {
                "change_id": str(c.id),
                "section": c.section,
                "description": c.description,
                "diff": {"before": c.diff.before, "after": c.diff.after},
                "accepted": True,
            }
            for c in applied_changes
        ]

        return CascadingConsistencyOutput(
            report_id=report_id,
            source_type=source_api,
            source_id=str(project_id),
            downstream_impact=downstream,
            your_changes=your_changes,  # type: ignore[reportArgumentType]
        )

    async def execute_stream(
        self,
        project_id: ProjectId,
        source_phase: SpecPhase,
        applied_changes: list[AppliedChange],
    ) -> AsyncGenerator[str]:
        report_id = f"cnr_{ULID().hex}"
        project = await self._project_repo.by_id(project_id)
        if project is None:
            error_event = json.dumps({"type": "error", "message": "Proyecto no encontrado"}, ensure_ascii=False)
            yield f"data: {error_event}\n\n"
            return

        source_api = SPEC_TO_API_PHASE[source_phase]
        targets = DOWNSTREAM_TARGETS[source_phase]

        # Phase 1: show all phases immediately
        for target_spec in targets:
            phase_api = SPEC_TO_API_PHASE[target_spec]
            yield _sse_event(
                "progress",
                phase=phase_api,
                status="evaluating",
                message=f"Evaluando impacto en {_phase_label(target_spec)}...",
            )

        # Phase 2: run all evaluate+enrich tasks in parallel
        async def _eval_and_enrich(target_spec: SpecPhase) -> dict[str, object]:
            phase_api = SPEC_TO_API_PHASE[target_spec]
            label = _phase_label(target_spec)
            try:
                result = await self._evaluator.evaluate(
                    source_phase=source_phase,
                    target_phase=target_spec,
                    project_id=project_id,
                    applied_changes=applied_changes,
                )
            except Exception:
                _log.warning(
                    "cascade.evaluate_failed",
                    project_id=str(project_id),
                    target=target_spec.value,
                    exc_info=True,
                )
                return {"phase": phase_api, "type": "error", "message": f"No se pudo evaluar {label}"}

            if not result.affected_artifact_ids:
                if result.status == ConsistencyStatus.ANALISIS_FALLIDO:
                    return {
                        "phase": phase_api,
                        "type": "failed",
                        "affected_count": 0,
                        "message": f"El analisis de impacto fallo para {label}",
                    }
                return {
                    "phase": phase_api,
                    "type": "no_impact",
                    "affected_count": 0,
                    "message": f"Sin cambios detectados en {label}",
                }

            try:
                items = await enrich_impact_items(
                    result,
                    target_spec,
                    source_phase,
                    self._feature_repo,
                    self._requirement_repo,
                    self._diagram_repo,
                )
            except Exception:
                _log.warning(
                    "cascade.enrich_failed",
                    project_id=str(project_id),
                    target=target_spec.value,
                    exc_info=True,
                )
                return {
                    "phase": phase_api,
                    "type": "failed",
                    "affected_count": 0,
                    "message": f"No se pudo enriquecer el impacto en {label}",
                }

            return {
                "phase": phase_api,
                "type": "done",
                "affected_count": len(items),
                "impact": [impact_item_to_dict(item) for item in items],
                "message": f"{len(items)} artefacto(s) afectado(s) en {label}",
            }

        gathered = await asyncio.gather(*[_eval_and_enrich(t) for t in targets], return_exceptions=True)

        # Phase 3: emit results and collect downstream impacts
        all_downstream: _ImpactList = []
        for entry in gathered:
            if isinstance(entry, BaseException):
                continue
            phase_api_val: object = entry.get("phase", "")
            phase_api = str(phase_api_val) if phase_api_val else ""
            entry_type = str(entry.get("type", ""))
            if entry_type == "done":
                impact_dicts: _ImpactList = entry.get("impact", [])  # type: ignore[assignment]
                all_downstream.extend(impact_dicts)
                affected_raw = entry.get("affected_count", 0)
                affected_count = int(affected_raw) if isinstance(affected_raw, int) else 0  # type: ignore[reportUnknownArgumentType]
                yield _sse_event(
                    "phase_result",
                    phase=phase_api,
                    affected_count=affected_count,
                    impact=impact_dicts,
                    message=str(entry.get("message", "")),
                )
            else:
                yield _sse_event(
                    "phase_result",
                    phase=phase_api,
                    affected_count=0,
                    status=entry_type,
                    message=str(entry.get("message", "")),
                )

        your_changes: list[dict[str, object]] = [
            {
                "change_id": str(c.id),
                "section": c.section,
                "description": c.description,
                "diff": {"before": c.diff.before, "after": c.diff.after},
                "accepted": True,
            }
            for c in applied_changes
        ]

        complete_event = json.dumps(
            {
                "type": "complete",
                "report": {
                    "report_id": report_id,
                    "source_type": source_api,
                    "source_id": str(project_id),
                    "your_changes": your_changes,
                    "downstream_impact": all_downstream,
                },
            },
            ensure_ascii=False,
        )
        yield f"data: {complete_event}\n\n"


def _sse_event(event_type: str, **kwargs: object) -> str:
    payload: dict[str, object] = {"type": event_type, **kwargs}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _phase_label(spec: SpecPhase) -> str:
    labels = {
        SpecPhase.DESCUBRIMIENTO: "Descubrimiento",
        SpecPhase.CARACTERISTICAS: "Características",
        SpecPhase.REQUISITOS: "Requisitos",
        SpecPhase.MODELO: "Modelo",
        SpecPhase.IMPLEMENTACION: "Implementación",
    }
    return labels.get(spec, spec.value)
