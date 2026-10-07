from __future__ import annotations

import structlog
from ulid import ULID

from kosmo.contracts.ai.chat import AppliedChange
from kosmo.contracts.ai.consistency import (
    ArtifactAction,
    ConsistencyEvaluationOutput,
    ConsistencyStatus,
)
from kosmo.contracts.pipeline.consistency_phase_context import (
    ConsistencyPhaseContext,
    DownstreamArtifact,
)
from kosmo.contracts.pipeline.orchestrator_ports import AgentPort
from kosmo.contracts.pipeline.phase_outputs import (
    ConsistencyCorrection,
    ConsistencyDetectionAction,
    ConsistencyDetectionReport,
    ConsistencyReport,
)
from kosmo.contracts.sdd.codegen import (
    FeatureImplementationRepository,
    FeatureImplementationStatus,
)
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.contracts.sdd.repositories import (
    ActivityDiagramRepository,
    DocumentRepository,
    FeatureRepository,
    RequirementRepository,
)
from kosmo.domain.sdd.consistency_filter import filter_downstream_artifacts
from kosmo.domain.sdd.discovery_diff import ChangeClass, diff_discovery_versions
from kosmo.domain.sdd.document_converters import document_to_markdown
from kosmo.domain.sdd.plan_diffs import merge_changes_with_diffs
from kosmo.domain.sdd.text_normalizer import normalize_for_match

_log = structlog.get_logger(__name__)

_LOG_FRAGMENT_LIMIT = 500


def _has_only_cosmetic_changes(changes: list[AppliedChange]) -> bool:
    return bool(changes) and all(c.change_class == ChangeClass.COSMETIC.value for c in changes)


def _validate_action(
    artifact_id: str,
    action: str,
    suggested_before: str,
    suggested_after: str,
    artifact_desc: str,
    artifact_type: str,
) -> bool:
    if action == "delete" and artifact_type == "DiscoveryDocument":
        _log.warning("consistency.delete_discovery_blocked", artifact_id=artifact_id)
        return False
    if suggested_before == suggested_after:
        _log.warning("consistency.noop_action", artifact_id=artifact_id, action=action)
        return False
    # Si el artefacto fue truncado para la evaluación del LLM, omitir validación estricta de contención
    if "[…contenido truncado…]" in artifact_desc:
        return True
    if suggested_before and normalize_for_match(suggested_before) not in normalize_for_match(artifact_desc):
        _log.warning(
            "consistency.before_mismatch",
            artifact_id=artifact_id,
            action=action,
            before=suggested_before[:_LOG_FRAGMENT_LIMIT],
            artifact_desc=artifact_desc[:_LOG_FRAGMENT_LIMIT],
            before_length=len(suggested_before),
            artifact_desc_length=len(artifact_desc),
        )
        return False
    return True


class EvaluateConsistencyUseCase:
    def __init__(
        self,
        agent: AgentPort,
        feature_repo: FeatureRepository,
        requirement_repo: RequirementRepository,
        diagram_repo: ActivityDiagramRepository,
        document_repo: DocumentRepository,
        implementation_repo: FeatureImplementationRepository | None = None,
    ) -> None:
        self._agent = agent
        self._feature_repo = feature_repo
        self._requirement_repo = requirement_repo
        self._diagram_repo = diagram_repo
        self._document_repo = document_repo
        self._implementation_repo = implementation_repo

    async def evaluate(
        self,
        *,
        source_phase: SpecPhase,
        target_phase: SpecPhase,
        project_id: ProjectId,
        applied_changes: list[AppliedChange],
    ) -> ConsistencyEvaluationOutput:
        report_id = f"cnr_{ULID().hex}"
        artifacts = await self._fetch_downstream_artifacts(target_phase, project_id)

        if not artifacts:
            return ConsistencyEvaluationOutput(report_id=report_id, status=ConsistencyStatus.ANALIZADO_SIN_IMPACTO)

        applied_changes = await self._resolve_changes(source_phase, project_id, applied_changes)

        if not applied_changes:
            return ConsistencyEvaluationOutput(report_id=report_id, status=ConsistencyStatus.ANALIZADO_SIN_IMPACTO)

        if _has_only_cosmetic_changes(applied_changes):
            _log.info(
                "consistency.cosmetic_only_skipped",
                report_id=report_id,
                target=target_phase.value,
                changes=len(applied_changes),
            )
            return ConsistencyEvaluationOutput(
                report_id=report_id,
                status=ConsistencyStatus.ANALIZADO_SIN_IMPACTO,
                rationale="Solo hay cambios cosmeticos; no se requiere evaluacion.",
            )

        prefiltered = filter_downstream_artifacts(artifacts, applied_changes)
        if len(prefiltered) != len(artifacts):
            _log.info(
                "consistency.prefilter_applied",
                target=target_phase.value,
                total=len(artifacts),
                kept=len(prefiltered),
            )
        artifacts = prefiltered

        source_content = await self._fetch_source_content(source_phase, project_id)

        context = ConsistencyPhaseContext(
            source_phase=source_phase,
            target_phase=target_phase,
            applied_changes=applied_changes,
            downstream_artifacts=artifacts,
            source_content=source_content,
        )

        skill_name = self._detection_skill_name(source_phase, target_phase)

        try:
            detection_raw = await self._agent.execute_with_skill(
                skill_name=skill_name,
                context=context,
                project_id=project_id,
            )
        except Exception:
            _log.warning(
                "consistency.evaluate_failed",
                source=source_phase.value,
                target=target_phase.value,
                project_id=str(project_id),
                exc_info=True,
            )
            return ConsistencyEvaluationOutput(
                report_id=report_id,
                status=ConsistencyStatus.ANALISIS_FALLIDO,
                failure_reason=f"El agente LLM fallo al evaluar {source_phase.value} → {target_phase.value}",
            )

        detections, candidate_count, overall_rationale = self._parse_detection(detection_raw, artifacts)

        artifact_by_id = {a.artifact_id: a for a in artifacts}
        actions: list[ArtifactAction] = []
        affected_ids: list[str] = []

        for detection in detections:
            if detection.action == "delete":
                actions.append(
                    ArtifactAction(
                        artifact_id=detection.artifact_id,
                        action="delete",
                        rationale=detection.rationale,
                    )
                )
                affected_ids.append(detection.artifact_id)
                continue

            art = artifact_by_id[detection.artifact_id]
            if art.artifact_type == "FeatureImplementation":
                actions.append(
                    ArtifactAction(
                        artifact_id=detection.artifact_id,
                        action="update",
                        rationale=detection.rationale,
                        suggested_field="status",
                        suggested_before="",
                        suggested_after="requires_review",
                    )
                )
                affected_ids.append(detection.artifact_id)
                continue

            full_content = await self._fetch_full_artifact_content(target_phase, project_id, detection.artifact_id)
            if full_content is None:
                _log.warning(
                    "consistency.full_artifact_missing",
                    artifact_id=detection.artifact_id,
                    target=target_phase.value,
                )
                continue

            art = artifact_by_id[detection.artifact_id]
            correction_context = ConsistencyPhaseContext(
                source_phase=source_phase,
                target_phase=target_phase,
                applied_changes=applied_changes,
                downstream_artifacts=[
                    DownstreamArtifact(
                        artifact_id=art.artifact_id,
                        artifact_type=art.artifact_type,
                        title=art.title,
                        description=full_content,
                    )
                ],
                source_content=source_content,
            )

            try:
                correction_raw = await self._agent.execute_with_skill(
                    skill_name="consistency_correct",
                    context=correction_context,
                    project_id=project_id,
                )
            except Exception:
                _log.warning(
                    "consistency.correction_failed",
                    artifact_id=detection.artifact_id,
                    exc_info=True,
                )
                continue

            field, before, after = self._parse_correction(correction_raw, detection.artifact_id)
            if not _validate_action(
                detection.artifact_id,
                "update",
                before,
                after,
                full_content,
                art.artifact_type,
            ):
                continue

            actions.append(
                ArtifactAction(
                    artifact_id=detection.artifact_id,
                    action="update",
                    rationale=detection.rationale,
                    suggested_field=field or detection.suggested_field,
                    suggested_before=before,
                    suggested_after=after,
                )
            )
            affected_ids.append(detection.artifact_id)

        if len(actions) < candidate_count:
            _log.warning(
                "consistency.actions_discarded",
                report_id=report_id,
                total_candidates=candidate_count,
                accepted=len(actions),
                discarded=candidate_count - len(actions),
            )

        status = ConsistencyStatus.ANALIZADO_CON_IMPACTO if affected_ids else ConsistencyStatus.ANALIZADO_SIN_IMPACTO
        return ConsistencyEvaluationOutput(
            report_id=report_id,
            status=status,
            affected_artifact_ids=affected_ids,
            rationale=overall_rationale,
            actions=actions,
        )

    @staticmethod
    def _detection_skill_name(source_phase: SpecPhase, target_phase: SpecPhase) -> str:
        if target_phase == SpecPhase.IMPLEMENTACION:
            if source_phase == SpecPhase.DESCUBRIMIENTO:
                return "consistency_evaluate_discovery_implementation"
            if source_phase == SpecPhase.CARACTERISTICAS:
                return "consistency_evaluate_features_implementation"
            if source_phase == SpecPhase.REQUISITOS:
                return "consistency_evaluate_requirements_implementation"
            if source_phase == SpecPhase.MODELO:
                return "consistency_evaluate_model_implementation"
            return "consistency_evaluate_implementation"
        if source_phase == SpecPhase.REQUISITOS and target_phase == SpecPhase.CARACTERISTICAS:
            return "consistency_evaluate_requirements"
        if source_phase == SpecPhase.REQUISITOS and target_phase == SpecPhase.DESCUBRIMIENTO:
            return "consistency_evaluate_requirements_upstream"
        if source_phase == SpecPhase.REQUISITOS and target_phase == SpecPhase.MODELO:
            return "consistency_evaluate_requirements_model"
        if source_phase == SpecPhase.CARACTERISTICAS and target_phase == SpecPhase.REQUISITOS:
            return "consistency_evaluate_features_downstream"
        if source_phase == SpecPhase.CARACTERISTICAS and target_phase == SpecPhase.MODELO:
            return "consistency_evaluate_features_model"
        if source_phase == SpecPhase.DESCUBRIMIENTO and target_phase == SpecPhase.CARACTERISTICAS:
            return "consistency_evaluate_discovery_features"
        if source_phase == SpecPhase.DESCUBRIMIENTO and target_phase == SpecPhase.REQUISITOS:
            return "consistency_evaluate_discovery_requirements"
        if source_phase == SpecPhase.DESCUBRIMIENTO and target_phase == SpecPhase.MODELO:
            return "consistency_evaluate_discovery_model"
        if target_phase == SpecPhase.DESCUBRIMIENTO:
            return "consistency_evaluate_upstream"
        return "consistency_evaluate"

    @staticmethod
    def _parse_detection(
        raw_output: object,
        artifacts: list[DownstreamArtifact],
    ) -> tuple[list[ConsistencyDetectionAction], int, str]:
        items: list[ConsistencyDetectionAction] = []
        overall_rationale = ""

        if isinstance(raw_output, ConsistencyDetectionReport):
            items = list(raw_output.actions)
            overall_rationale = raw_output.overall_rationale
        elif isinstance(raw_output, ConsistencyReport):
            items = [
                ConsistencyDetectionAction(
                    artifact_id=a.artifact_id,
                    action=a.action,
                    rationale=a.rationale,
                    suggested_field=a.suggested_field,
                )
                for a in raw_output.actions
            ]
            overall_rationale = raw_output.overall_rationale
        elif isinstance(raw_output, dict):
            report_dict: dict[str, object] = raw_output  # type: ignore[reportUnknownVariableType]
            actions_raw: object = report_dict.get("actions", [])
            if isinstance(actions_raw, list):
                for item in actions_raw:  # type: ignore[reportUnknownVariableType]
                    if not isinstance(item, dict):
                        continue
                    item_dict: dict[str, object] = item  # type: ignore[reportUnknownVariableType]
                    items.append(
                        ConsistencyDetectionAction(
                            artifact_id=str(item_dict.get("artifact_id", "")),
                            action=str(item_dict.get("action", "update")),
                            rationale=str(item_dict.get("rationale", "")),
                            suggested_field=str(item_dict.get("suggested_field", "")),
                        )
                    )
            overall_rationale = str(report_dict.get("overall_rationale", ""))

        candidate_count = len(items)
        artifact_ids_set = {a.artifact_id for a in artifacts}
        artifact_by_id = {a.artifact_id: a for a in artifacts}
        detections: list[ConsistencyDetectionAction] = []
        seen: set[str] = set()

        for item in items:
            if item.artifact_id not in artifact_ids_set:
                continue
            if item.action not in ("update", "delete"):
                continue
            if item.artifact_id in seen:
                continue
            art = artifact_by_id[item.artifact_id]
            if item.action == "delete" and art.artifact_type == "DiscoveryDocument":
                _log.warning("consistency.delete_discovery_blocked", artifact_id=item.artifact_id)
                continue
            detections.append(item)
            seen.add(item.artifact_id)

        return detections, candidate_count, overall_rationale

    @staticmethod
    def _parse_correction(raw_output: object, artifact_id: str) -> tuple[str, str, str]:
        if isinstance(raw_output, ConsistencyCorrection):
            return raw_output.suggested_field, raw_output.suggested_before, raw_output.suggested_after
        if isinstance(raw_output, dict):
            correction_dict: dict[str, object] = raw_output  # type: ignore[reportUnknownVariableType]
            actions_raw: object = correction_dict.get("actions")
            if isinstance(actions_raw, list):
                for item in actions_raw:  # type: ignore[reportUnknownVariableType]
                    if not isinstance(item, dict):
                        continue
                    item_dict: dict[str, object] = item  # type: ignore[reportUnknownVariableType]
                    if str(item_dict.get("artifact_id", "")) == artifact_id:
                        return (
                            str(item_dict.get("suggested_field", "")),
                            str(item_dict.get("suggested_before", "")),
                            str(item_dict.get("suggested_after", "")),
                        )
                return "", "", ""
            return (
                str(correction_dict.get("suggested_field", "")),
                str(correction_dict.get("suggested_before", "")),
                str(correction_dict.get("suggested_after", "")),
            )
        if isinstance(raw_output, ConsistencyReport):
            for action in raw_output.actions:
                if action.artifact_id == artifact_id:
                    return action.suggested_field, action.suggested_before, action.suggested_after
            return "", "", ""
        return "", "", ""

    async def _fetch_full_artifact_content(
        self,
        target_phase: SpecPhase,
        project_id: ProjectId,
        artifact_id: str,
    ) -> str | None:
        if target_phase == SpecPhase.DESCUBRIMIENTO:
            doc = await self._document_repo.get_discovery(project_id)
            return document_to_markdown(doc) if doc is not None else None
        if target_phase == SpecPhase.CARACTERISTICAS:
            feature = await self._feature_repo.by_id(FeatureId(artifact_id))
            if feature is None:
                return None
            desc = feature.description + (f"\nOrigen: {feature.origin}" if feature.origin else "")
            return f"Título: {feature.title}\nDescripción: {desc}"
        if target_phase == SpecPhase.REQUISITOS:
            return await self._requirement_repo.by_feature_id(FeatureId(artifact_id))
        if target_phase == SpecPhase.MODELO:
            diagram = await self._diagram_repo.by_feature_id(FeatureId(artifact_id))
            return diagram.diagram_syntax if diagram is not None else None
        if target_phase == SpecPhase.IMPLEMENTACION:
            if self._implementation_repo is None:
                return None
            impl = await self._implementation_repo.by_feature_id(FeatureId(artifact_id))
            if impl is None:
                return None
            files_str = ", ".join(impl.generated_files) if impl.generated_files else "Sin archivos"
            return f"Estado: {impl.status.value}\nArchivos: {files_str}"
        return None

    async def _fetch_source_content(self, source_phase: SpecPhase, project_id: ProjectId) -> str:
        if source_phase == SpecPhase.DESCUBRIMIENTO:
            doc = await self._document_repo.get_discovery(project_id)
            if doc is not None:
                return document_to_markdown(doc)
        elif source_phase == SpecPhase.CARACTERISTICAS:
            features = await self._feature_repo.list_by_project(project_id)
            if features:
                items: list[str] = []
                for f in features:
                    item_str = f"### Feature: {f.title} (ID: {f.id})\n- Descripción: {f.description}"
                    if f.origin:
                        item_str += f"\n- Origen: {f.origin}"
                    items.append(item_str)
                return "\n\n".join(items)
        elif source_phase == SpecPhase.REQUISITOS:
            features = await self._feature_repo.list_by_project(project_id)
            parts: list[str] = []
            for f in features:
                req_md = await self._requirement_repo.by_feature_id(f.id)
                if req_md:
                    parts.append(f"## Requisitos de '{f.title}' (Feature {f.id})\n\n{req_md}")
            return "\n\n".join(parts)
        return ""

    async def _resolve_changes(
        self,
        source_phase: SpecPhase,
        project_id: ProjectId,
        plan_changes: list[AppliedChange],
    ) -> list[AppliedChange]:
        if source_phase != SpecPhase.DESCUBRIMIENTO:
            return plan_changes

        # Si ya vienen diffs específicos con before no vacío, usarlos directamente
        if any(c.diff.before.strip() for c in plan_changes):
            return plan_changes

        try:
            previous_md = await self._document_repo.get_latest_version(project_id, SpecPhase.DESCUBRIMIENTO)
        except Exception:
            _log.debug("evaluate_consistency.prev_version_fetch_failed", project_id=str(project_id), exc_info=True)
            previous_md = None

        if previous_md is None:
            return plan_changes

        current_doc = await self._document_repo.get_discovery(project_id)
        if current_doc is None:
            return plan_changes
        current_md = document_to_markdown(current_doc)

        section_changes = diff_discovery_versions(previous_md, current_md)
        if not section_changes:
            return plan_changes

        return merge_changes_with_diffs(plan_changes, section_changes)

    async def _fetch_downstream_artifacts(
        self, target_phase: SpecPhase, project_id: ProjectId
    ) -> list[DownstreamArtifact]:
        if target_phase == SpecPhase.DESCUBRIMIENTO:
            doc = await self._document_repo.get_discovery(project_id)
            if doc is not None:
                return [
                    DownstreamArtifact(
                        artifact_id=str(project_id),
                        artifact_type="DiscoveryDocument",
                        title="Documento de Descubrimiento",
                        description=document_to_markdown(doc),
                    )
                ]
            return []
        if target_phase == SpecPhase.CARACTERISTICAS:
            return await self._fetch_features(project_id)
        if target_phase == SpecPhase.REQUISITOS:
            return await self._fetch_requirements(project_id)
        if target_phase == SpecPhase.MODELO:
            return await self._fetch_models(project_id)
        if target_phase == SpecPhase.IMPLEMENTACION:
            return await self._fetch_implementations(project_id)
        return []

    async def _fetch_features(self, project_id: ProjectId) -> list[DownstreamArtifact]:
        features = await self._feature_repo.list_by_project(project_id)
        return [
            DownstreamArtifact(
                artifact_id=str(f.id),
                artifact_type="Feature",
                title=f.title,
                description=f.description + (f"\nOrigen: {f.origin}" if f.origin else ""),
            )
            for f in features
        ]

    async def _fetch_requirements(self, project_id: ProjectId) -> list[DownstreamArtifact]:
        features = await self._feature_repo.list_by_project(project_id)
        artifacts: list[DownstreamArtifact] = []
        for f in features:
            req_md = await self._requirement_repo.by_feature_id(f.id)
            if req_md is not None:
                artifacts.append(
                    DownstreamArtifact(
                        artifact_id=str(f.id),
                        artifact_type="EARSRequirement",
                        title=f"Requisitos de {f.title}",
                        description=req_md,
                    )
                )
        return artifacts

    async def _fetch_models(self, project_id: ProjectId) -> list[DownstreamArtifact]:
        features = await self._feature_repo.list_by_project(project_id)
        artifacts: list[DownstreamArtifact] = []
        for f in features:
            diagram_exists = await self._diagram_repo.exists(f.id)
            if diagram_exists:
                diagram = await self._diagram_repo.by_feature_id(f.id)
                syntax = diagram.diagram_syntax[:8000] if diagram else ""
                if diagram and len(diagram.diagram_syntax) > 8000:
                    syntax += "\n[…contenido truncado…]"
                artifacts.append(
                    DownstreamArtifact(
                        artifact_id=str(f.id),
                        artifact_type="ActivityDiagram",
                        title=f"Diagrama de {f.title}",
                        description=syntax,
                    )
                )
        return artifacts

    async def _fetch_implementations(self, project_id: ProjectId) -> list[DownstreamArtifact]:
        if self._implementation_repo is None:
            return []
        implementations = await self._implementation_repo.list_by_project(project_id)
        artifacts: list[DownstreamArtifact] = []
        for impl in implementations:
            if impl.status not in (
                FeatureImplementationStatus.IMPLEMENTED,
                FeatureImplementationStatus.REQUIRES_REVIEW,
                FeatureImplementationStatus.IN_PROGRESS,
            ):
                continue
            feature = await self._feature_repo.by_id(impl.feature_id)
            if feature is None:
                continue
            files_str = ", ".join(impl.generated_files) if impl.generated_files else "Sin archivos"
            desc = f"Implementación de '{feature.title}'. Estado: {impl.status.value}. Archivos: {files_str}."
            if impl.plan and impl.plan.summary:
                desc += f" Resumen: {impl.plan.summary}"
            artifacts.append(
                DownstreamArtifact(
                    artifact_id=str(impl.feature_id),
                    artifact_type="FeatureImplementation",
                    title=f"Código de {feature.title}",
                    description=desc,
                )
            )
        return artifacts
