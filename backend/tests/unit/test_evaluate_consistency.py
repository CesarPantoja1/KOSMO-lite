from __future__ import annotations

import pytest

from kosmo.application.consistency.evaluate_consistency import EvaluateConsistencyUseCase
from kosmo.contracts import AppliedChange, DiffCambio
from kosmo.contracts.ai.consistency import ConsistencyEvaluationOutput
from kosmo.contracts.pipeline.orchestrator_ports import AgentPort
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId, UserId
from kosmo.contracts.sdd.project import Project
from kosmo.contracts.sdd.repositories import (
    ActivityDiagramRepository,
    DocumentRepository,
    FeatureRepository,
    RequirementRepository,
)
from tests.unit.fakes import (
    InMemoryActivityDiagramRepository,
    InMemoryDocumentRepository,
    InMemoryFeatureRepository,
    InMemoryProjectRepository,
    InMemoryRequirementRepository,
)


class StubConsistencyAgent:
    def __init__(self, *, affected_ids: list[str] | None = None, should_fail: bool = False) -> None:
        self._affected_ids = affected_ids or []
        self._should_fail = should_fail
        self.last_context: object | None = None
        self.last_skill_name: str | None = None
        self.skill_names: list[str] = []

    async def execute_with_skill(  # noqa: ARG002
        self,
        skill_name: str,
        context: object,
        *,
        project_id: object | None = None,
        user_instructions: str | None = None,
    ) -> object:
        self.last_context = context
        self.last_skill_name = skill_name
        self.skill_names.append(skill_name)
        if self._should_fail:
            raise RuntimeError("Stub agent failure")
        return {
            "actions": [
                {
                    "artifact_id": aid,
                    "action": "update",
                    "rationale": f"Stub rationale for {aid}",
                    "suggested_field": "description",
                    "suggested_before": "",
                    "suggested_after": "stub_suggested_fix",
                }
                for aid in self._affected_ids
            ],
            "overall_rationale": "Stub evaluation",
        }

    async def execute_conversation(
        self,
        skill_name: str,
        messages: list[object],
        context: object,
        **kwargs: object,  # noqa: ARG002
    ) -> object:
        raise NotImplementedError("Not used in consistency tests")


def _make_project(project_id: str = "prj_test") -> Project:
    return Project(
        id=ProjectId(project_id),
        name="Test Project",
        slug="test-project",
        description="Test",
        owner_id=UserId("usr_test"),
    )


def _make_feature(feature_id: str, project_id: str, title: str, number: int = 1) -> Feature:
    return Feature(
        id=FeatureId(feature_id),
        number=number,
        title=title,
        slug=title.lower().replace(" ", "-"),
        description=f"Descripción de {title}",
        project_id=ProjectId(project_id),
        origin="Derivado de Descubrimiento",
    )


def _applied_change(cid: str, before: str = "old", after: str = "new") -> AppliedChange:
    return AppliedChange(
        id=cid,
        section="Alcance",
        description="Cambio de alcance",
        diff=DiffCambio(before=before, after=after),
    )


def _make_uc(
    agent: AgentPort,
    feature_repo: FeatureRepository,
    requirement_repo: RequirementRepository,
    diagram_repo: ActivityDiagramRepository,
    document_repo: DocumentRepository,
) -> EvaluateConsistencyUseCase:
    return EvaluateConsistencyUseCase(
        agent=agent,
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        diagram_repo=diagram_repo,
        document_repo=document_repo,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_identifies_affected_features() -> None:
    # Arrange
    project = _make_project("prj_001")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_01", "prj_001", "Gestión de catálogo", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    agent = StubConsistencyAgent(affected_ids=["feat_01"])
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_01", before="Alcance original", after="Alcance LATAM")

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_001"),
        applied_changes=[change],
    )

    # Assert
    assert isinstance(result, ConsistencyEvaluationOutput)
    assert result.report_id.startswith("cnr_")
    assert result.affected_artifact_ids == ["feat_01"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_agent_failure_returns_empty() -> None:
    # Arrange
    project = _make_project("prj_002")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_02", "prj_002", "Feature Test", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    agent = StubConsistencyAgent(should_fail=True)
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_01")

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_002"),
        applied_changes=[change],
    )

    # Assert
    assert result.affected_artifact_ids == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_no_downstream_artifacts_returns_empty() -> None:
    # Arrange
    project = _make_project("prj_003")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    agent = StubConsistencyAgent(affected_ids=["should_not_appear"])
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_01")

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_003"),
        applied_changes=[change],
    )

    # Assert: sin features registradas, el evaluador devuelve vacío sin llamar al agente
    assert result.affected_artifact_ids == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_filters_out_unknown_ids() -> None:
    # Arrange
    project = _make_project("prj_004")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_04", "prj_004", "Feature Real", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    agent = StubConsistencyAgent(affected_ids=["feat_04", "feat_fantasma"])
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_01")

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_004"),
        applied_changes=[change],
    )

    # Assert: solo devuelve IDs que corresponden a artefactos reales
    assert result.affected_artifact_ids == ["feat_04"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_deduplicates_repeated_artifact_ids() -> None:
    # Arrange: el LLM devuelve dos acciones para el mismo artifact
    project = _make_project("prj_dedup")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_01", "prj_dedup", "Feature Duplicada", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    agent = StubConsistencyAgent(affected_ids=["feat_01", "feat_01"])
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_01")

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_dedup"),
        applied_changes=[change],
    )

    # Assert: el id repetido se deduplica, una sola accion
    assert result.affected_artifact_ids == ["feat_01"]
    assert len(result.actions) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_fetch_source_content_for_features() -> None:
    from kosmo.contracts.pipeline.consistency_phase_context import ConsistencyPhaseContext
    from kosmo.domain.sdd.document_converters import markdown_to_document

    project = _make_project("prj_005")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_05", "prj_005", "Gestión de inventario", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()
    document_repo.discovery_docs["prj_005"] = markdown_to_document("## Visión\n\nVisión original.")

    agent = StubConsistencyAgent(affected_ids=["prj_005"])
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_01")

    _result = await uc.evaluate(
        source_phase=SpecPhase.CARACTERISTICAS,
        target_phase=SpecPhase.DESCUBRIMIENTO,
        project_id=ProjectId("prj_005"),
        applied_changes=[change],
    )

    assert isinstance(agent.last_context, ConsistencyPhaseContext)
    assert "Gestión de inventario" in agent.last_context.source_content
    assert "feat_05" in agent.last_context.source_content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_requirements_to_features_uses_correct_skill() -> None:
    """REQUISITOS → CARACTERISTICAS debe usar el skill consistency_evaluate_requirements."""
    # Arrange
    project = _make_project("prj_r2f")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_r2f", "prj_r2f", "Gestión de pagos", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    agent = StubConsistencyAgent(affected_ids=["feat_r2f"])
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change(
        "chg_r2f", before="procesar pagos con tarjeta", after="procesar pagos con cualquier método"
    )

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.REQUISITOS,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_r2f"),
        applied_changes=[change],
    )

    # Assert
    assert result.affected_artifact_ids == ["feat_r2f"]
    assert "consistency_evaluate_requirements" in agent.skill_names


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_fetch_source_content_for_requirements() -> None:
    """Verifica que _fetch_source_content devuelva los requisitos para la fase REQUISITOS."""
    from kosmo.contracts.pipeline.consistency_phase_context import ConsistencyPhaseContext

    project = _make_project("prj_srcr")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_srcr", "prj_srcr", "Gestión de inventario", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    await requirement_repo.save(
        FeatureId("feat_srcr"),
        "### REQ-1.1\n\nEl sistema shall procesar inventario en tiempo real.\n",
    )
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    agent = StubConsistencyAgent(affected_ids=["feat_srcr"])
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_srcr", before="procesar inventario", after="procesar inventario en tiempo real")

    # Act
    _result = await uc.evaluate(
        source_phase=SpecPhase.REQUISITOS,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_srcr"),
        applied_changes=[change],
    )

    # Assert
    assert isinstance(agent.last_context, ConsistencyPhaseContext)
    assert "REQ-1.1" in agent.last_context.source_content
    assert "procesar inventario" in agent.last_context.source_content
    assert agent.last_context.source_phase == SpecPhase.REQUISITOS
    assert agent.last_context.target_phase == SpecPhase.CARACTERISTICAS


@pytest.mark.unit
def test_consistency_requirements_downstream_prompt_exists() -> None:
    """Verifica que el nuevo prompt para requisitos→features esté definido y exportado."""
    from kosmo.domain.pipeline.phase_modes.consistency_evaluation_mode import (
        CONSISTENCY_REQUIREMENTS_DOWNSTREAM_SYSTEM_PROMPT,
    )

    assert isinstance(CONSISTENCY_REQUIREMENTS_DOWNSTREAM_SYSTEM_PROMPT, str)
    assert "Requisitos EARS" in CONSISTENCY_REQUIREMENTS_DOWNSTREAM_SYSTEM_PROMPT
    assert "CARACTERISTICA" in CONSISTENCY_REQUIREMENTS_DOWNSTREAM_SYSTEM_PROMPT.upper()
    assert "JSON" in CONSISTENCY_REQUIREMENTS_DOWNSTREAM_SYSTEM_PROMPT


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_requirements_to_discovery_uses_upstream_skill() -> None:
    """REQUISITOS → DESCUBRIMIENTO debe usar el skill consistency_evaluate_requirements_upstream."""
    from kosmo.domain.sdd.document_converters import markdown_to_document

    project = _make_project("prj_r2d")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_r2d", "prj_r2d", "Gestión de usuarios", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()
    document_repo.discovery_docs["prj_r2d"] = markdown_to_document("## Visión\n\nVisión original.")

    agent = StubConsistencyAgent(affected_ids=["prj_r2d"])
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_r2d")

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.REQUISITOS,
        target_phase=SpecPhase.DESCUBRIMIENTO,
        project_id=ProjectId("prj_r2d"),
        applied_changes=[change],
    )

    # Assert
    assert result.affected_artifact_ids == ["prj_r2d"]
    assert "consistency_evaluate_requirements_upstream" in agent.skill_names


@pytest.mark.unit
def test_consistency_requirements_upstream_prompt_exists() -> None:
    """Verifica que el prompt para requisitos→descubrimiento esté definido y exportado."""
    from kosmo.domain.pipeline.phase_modes.consistency_evaluation_mode import (
        CONSISTENCY_REQUIREMENTS_UPSTREAM_SYSTEM_PROMPT,
    )

    assert isinstance(CONSISTENCY_REQUIREMENTS_UPSTREAM_SYSTEM_PROMPT, str)
    assert "Requisitos EARS" in CONSISTENCY_REQUIREMENTS_UPSTREAM_SYSTEM_PROMPT
    assert "Descubrimiento" in CONSISTENCY_REQUIREMENTS_UPSTREAM_SYSTEM_PROMPT
    assert "JSON" in CONSISTENCY_REQUIREMENTS_UPSTREAM_SYSTEM_PROMPT


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_empty_changes_uses_automatic_diff() -> None:
    """applied_changes vacío con diff real entre versiones de Discovery debe evaluar igualmente."""
    from kosmo.contracts.pipeline.consistency_phase_context import ConsistencyPhaseContext
    from kosmo.domain.sdd.document_converters import markdown_to_document

    # Arrange
    project = _make_project("prj_diff")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_diff", "prj_diff", "Gestión de catálogo", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()
    await document_repo.save_version(
        ProjectId("prj_diff"),
        SpecPhase.DESCUBRIMIENTO,
        "## Alcance\n\nEl sistema tendrá el producto X.",
        [],
    )
    document_repo.discovery_docs["prj_diff"] = markdown_to_document(
        "## Alcance\n\nEl sistema ya no tendrá el producto X."
    )

    agent = StubConsistencyAgent(affected_ids=["feat_diff"])
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_diff"),
        applied_changes=[],
    )

    # Assert: el diff automático se usó y la evaluación se ejecutó
    assert result.affected_artifact_ids == ["feat_diff"]
    assert any(s in agent.skill_names for s in ("consistency_evaluate_discovery_features", "consistency_evaluate"))
    assert isinstance(agent.last_context, ConsistencyPhaseContext)
    assert len(agent.last_context.applied_changes) == 1
    assert "producto X" in agent.last_context.applied_changes[0].diff.before


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_empty_changes_without_previous_version_returns_no_impact() -> None:
    """applied_changes vacío sin versión previa guardada debe retornar sin impacto sin llamar al agente."""
    from kosmo.contracts.ai.consistency import ConsistencyStatus

    # Arrange
    project = _make_project("prj_noversion")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_nov", "prj_noversion", "Gestión de catálogo", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    agent = StubConsistencyAgent(affected_ids=["feat_nov"])
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_noversion"),
        applied_changes=[],
    )

    # Assert
    assert result.status == ConsistencyStatus.ANALIZADO_SIN_IMPACTO
    assert agent.last_skill_name is None


class _DictOutputAgent:
    """Stub que devuelve un dict crudo con acciones mezcladas (válidas y descartables)."""

    def __init__(self, actions: list[dict[str, str]]) -> None:
        self._actions = actions
        self.last_skill_name: str | None = None
        self.last_context: object | None = None
        self.skill_names: list[str] = []

    async def execute_with_skill(  # noqa: ARG002
        self,
        skill_name: str,
        context: object,
        *,
        project_id: object | None = None,
        user_instructions: str | None = None,
    ) -> object:
        self.last_skill_name = skill_name
        self.last_context = context
        self.skill_names.append(skill_name)
        return {"actions": self._actions, "overall_rationale": "Stub"}

    async def execute_conversation(self, *args: object, **kwargs: object) -> object:  # noqa: ARG002
        raise NotImplementedError


class _TwoPhaseAgent:
    """Stub con comportamiento distinto por fase: detección y corrección."""

    def __init__(
        self,
        detection_report: dict[str, object],
        corrections: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._detection_report = detection_report
        self._corrections = corrections or {}
        self.skill_names: list[str] = []
        self.contexts: list[object] = []
        self.call_count = 0

    async def execute_with_skill(
        self,
        skill_name: str,
        context: object,
        *,
        project_id: object | None = None,
        user_instructions: str | None = None,
    ) -> object:
        self.skill_names.append(skill_name)
        self.contexts.append(context)
        self.call_count += 1
        if skill_name == "consistency_correct":
            from kosmo.contracts.pipeline.consistency_phase_context import ConsistencyPhaseContext

            assert isinstance(context, ConsistencyPhaseContext)
            artifact_id = context.downstream_artifacts[0].artifact_id
            return self._corrections.get(artifact_id, {"suggested_before": "", "suggested_after": ""})
        return self._detection_report

    async def execute_conversation(self, *args: object, **kwargs: object) -> object:  # noqa: ARG002
        raise NotImplementedError


@pytest.mark.unit
def test_validate_action_logs_before_mismatch_with_context() -> None:
    """Un mismatch de suggested_before debe loguearse con contexto suficiente para diagnosticar."""
    from structlog.testing import capture_logs

    from kosmo.application.consistency.evaluate_consistency import _validate_action

    # Arrange
    before = "REQ-1.1: El sistema debe registrar el producto X" + " relleno" * 60
    artifact_desc = "## Requisitos\n\nREQ-1.1: El sistema debe registrar el catálogo."

    # Act
    with capture_logs() as logs:
        accepted = _validate_action(
            "feat_01",
            "update",
            before,
            "corregido",
            artifact_desc,
            "EARSRequirement",
        )

    # Assert
    assert accepted is False
    mismatch_events = [e for e in logs if e.get("event") == "consistency.before_mismatch"]
    assert len(mismatch_events) == 1
    event = mismatch_events[0]
    assert event["artifact_id"] == "feat_01"
    assert event["action"] == "update"
    assert event["before_length"] == len(before)
    assert event["artifact_desc_length"] == len(artifact_desc)
    assert len(event["before"]) == 500
    assert len(event["artifact_desc"]) == len(artifact_desc)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_logs_actions_discarded_summary() -> None:
    """Las acciones descartadas deben quedar contabilizadas en un log de resumen."""
    from structlog.testing import capture_logs

    # Arrange
    project = _make_project("prj_sum")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    await feature_repo.save(_make_feature("feat_ok", "prj_sum", "Feature Válida", number=1))
    await feature_repo.save(_make_feature("feat_bad", "prj_sum", "Feature con Mismatch", number=2))

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    agent = _DictOutputAgent(
        actions=[
            {
                "artifact_id": "feat_ok",
                "action": "update",
                "rationale": "válida",
                "suggested_before": "",
                "suggested_after": "corrección",
            },
            {
                "artifact_id": "feat_ghost",
                "action": "update",
                "rationale": "id desconocido",
                "suggested_before": "",
                "suggested_after": "x",
            },
            {
                "artifact_id": "feat_bad",
                "action": "update",
                "rationale": "mismatch",
                "suggested_before": "texto que no existe",
                "suggested_after": "corrección",
            },
        ]
    )
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_sum")

    # Act
    with capture_logs() as logs:
        result = await uc.evaluate(
            source_phase=SpecPhase.CARACTERISTICAS,
            target_phase=SpecPhase.CARACTERISTICAS,
            project_id=ProjectId("prj_sum"),
            applied_changes=[change],
        )

    # Assert
    assert result.affected_artifact_ids == ["feat_ok"]
    summary_events = [e for e in logs if e.get("event") == "consistency.actions_discarded"]
    assert len(summary_events) == 1
    assert summary_events[0]["total_candidates"] == 3
    assert summary_events[0]["accepted"] == 1
    assert summary_events[0]["discarded"] == 2
    assert any(e.get("event") == "consistency.before_mismatch" for e in logs)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_impact_logs_when_ears_parsing_fails() -> None:
    """Si parse_requirements_markdown no puede parsear el suggested_before, debe loguearse."""
    from structlog.testing import capture_logs

    from kosmo.application.consistency.enrich_impact import enrich_impact_items
    from kosmo.contracts.ai.consistency import (
        ArtifactAction,
        ConsistencyEvaluationOutput,
        ConsistencyStatus,
    )

    # Arrange
    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_enr", "prj_enr", "Gestión de catálogo", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    await requirement_repo.save(
        FeatureId("feat_enr"),
        "### REQ-1.1\n\nEl sistema shall registrar el catálogo.\n",
    )
    diagram_repo = InMemoryActivityDiagramRepository()

    result = ConsistencyEvaluationOutput(
        report_id="cnr_enr",
        status=ConsistencyStatus.ANALIZADO_CON_IMPACTO,
        affected_artifact_ids=["feat_enr"],
        actions=[
            ArtifactAction(
                artifact_id="feat_enr",
                action="update",
                rationale="Impacto en requisitos",
                suggested_before="Este texto no es markdown EARS",
                suggested_after="Este tampoco lo es",
            )
        ],
    )

    # Act
    with capture_logs() as logs:
        await enrich_impact_items(
            result,
            SpecPhase.REQUISITOS,
            SpecPhase.DESCUBRIMIENTO,
            feature_repo,
            requirement_repo,
            diagram_repo,
        )

    # Assert
    parse_events = [e for e in logs if e.get("event") == "consistency.enrich_parse_empty"]
    assert len(parse_events) == 1
    assert parse_events[0]["artifact_id"] == "feat_enr"
    assert parse_events[0]["before_requirements"] == 0
    assert parse_events[0]["after_requirements"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_detection_keeps_impact_despite_mismatched_before() -> None:
    """Un before incoherente en la detección no debe descartar el impacto: la corrección lo resuelve."""
    # Arrange
    project = _make_project("prj_p1")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_p1", "prj_p1", "Gestión de catálogo", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    agent = _TwoPhaseAgent(
        detection_report={
            "actions": [
                {
                    "artifact_id": "feat_p1",
                    "action": "update",
                    "rationale": "El producto X fue eliminado del descubrimiento.",
                    "suggested_before": "fragmento que no existe en el artefacto truncado",
                    "suggested_after": "x",
                }
            ],
            "overall_rationale": "Impacto real",
        },
        corrections={
            "feat_p1": {
                "suggested_field": "description",
                "suggested_before": "Descripción de Gestión de catálogo",
                "suggested_after": "Descripción sin el producto X",
            }
        },
    )
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_p1")

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_p1"),
        applied_changes=[change],
    )

    # Assert: el impacto se conserva y la corrección validada proviene de la fase 2
    assert result.affected_artifact_ids == ["feat_p1"]
    assert len(result.actions) == 1
    assert result.actions[0].suggested_before == "Descripción de Gestión de catálogo"
    assert result.actions[0].suggested_after == "Descripción sin el producto X"
    assert "consistency_correct" in agent.skill_names


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_delete_action_skips_correction_call() -> None:
    """Una acción delete no necesita fase de corrección: se conserva sin before/after."""
    # Arrange
    project = _make_project("prj_del")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_del", "prj_del", "Gestión de inventario", number=1)
    await feature_repo.save(feat)

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    agent = _TwoPhaseAgent(
        detection_report={
            "actions": [
                {
                    "artifact_id": "feat_del",
                    "action": "delete",
                    "rationale": "El concepto de inventario ya no existe.",
                }
            ],
            "overall_rationale": "Eliminación",
        }
    )
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_del")

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_del"),
        applied_changes=[change],
    )

    # Assert
    assert result.affected_artifact_ids == ["feat_del"]
    assert len(result.actions) == 1
    assert result.actions[0].action == "delete"
    assert result.actions[0].suggested_before == ""
    assert agent.call_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_correction_receives_full_artifact_content() -> None:
    """La fase de corrección recibe el contenido COMPLETO del artefacto, sin truncamiento."""
    from kosmo.contracts.pipeline.consistency_phase_context import ConsistencyPhaseContext

    # Arrange
    project = _make_project("prj_full")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_full", "prj_full", "Flujo complejo", number=1)
    await feature_repo.save(feat)

    diagram_repo = InMemoryActivityDiagramRepository()
    from kosmo.contracts.sdd.activity_diagram import DiagramaActividad
    from kosmo.contracts.sdd.ids import ActivityDiagramId

    long_syntax = "@startuml\nstart\n" + (":procesar paso;\n" * 700) + "stop\n@enduml"
    await diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("feat_full"),
            feature_id=FeatureId("feat_full"),
            diagram_syntax=long_syntax,
        )
    )

    requirement_repo = InMemoryRequirementRepository()
    document_repo = InMemoryDocumentRepository()

    agent = _TwoPhaseAgent(
        detection_report={
            "actions": [
                {
                    "artifact_id": "feat_full",
                    "action": "update",
                    "rationale": "El flujo cambió.",
                }
            ],
            "overall_rationale": "Cambio de flujo",
        },
        corrections={
            "feat_full": {
                "suggested_before": "stop\n@enduml",
                "suggested_after": "fin\n@enduml",
            }
        },
    )
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_full")

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.REQUISITOS,
        target_phase=SpecPhase.MODELO,
        project_id=ProjectId("prj_full"),
        applied_changes=[change],
    )

    # Assert: el contexto de corrección trae el diagrama completo (sin marca de truncado)
    assert result.affected_artifact_ids == ["feat_full"]
    correction_ctx = agent.contexts[1]
    assert isinstance(correction_ctx, ConsistencyPhaseContext)
    full_description = correction_ctx.downstream_artifacts[0].description
    assert len(full_description) > 8000
    assert "[…contenido truncado…]" not in full_description
    assert full_description.endswith("stop\n@enduml")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_prefilters_artifacts_before_detection() -> None:
    """Solo los artefactos que mencionan los términos del cambio se envían a la detección."""
    from kosmo.contracts.pipeline.consistency_phase_context import ConsistencyPhaseContext

    # Arrange
    project = _make_project("prj_pref")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    await feature_repo.save(_make_feature("feat_pref", "prj_pref", "Registro de productos", number=1))
    await feature_repo.save(_make_feature("feat_other", "prj_pref", "Gestión de pagos", number=2))

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    agent = _TwoPhaseAgent(
        detection_report={
            "actions": [{"artifact_id": "feat_pref", "action": "update", "rationale": "El producto X cambió."}],
            "overall_rationale": "Impacto",
        },
        corrections={
            "feat_pref": {
                "suggested_before": "Descripción de Registro de productos",
                "suggested_after": "Descripción actualizada",
            }
        },
    )
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_pref", before="se elimina el producto X", after="se elimina el producto Y")

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_pref"),
        applied_changes=[change],
    )

    # Assert: la detección solo vio el artefacto candidato
    detection_ctx = agent.contexts[0]
    assert isinstance(detection_ctx, ConsistencyPhaseContext)
    assert [a.artifact_id for a in detection_ctx.downstream_artifacts] == ["feat_pref"]
    assert result.affected_artifact_ids == ["feat_pref"]


@pytest.mark.unit
def test_consistency_evaluation_mode_exposes_knowledge_tools() -> None:
    """El modo de consistencia debe exponer tools de conocimiento y habilitar la pre-consulta."""
    from kosmo.domain.pipeline.phase_modes.consistency_evaluation_mode import ConsistencyEvaluationMode

    # Arrange
    mode = ConsistencyEvaluationMode()

    # Act
    tool_names = [t.name for t in mode.available_tools]

    # Assert
    assert "get_requirements_for_feature" in tool_names
    assert "get_diagram_for_feature" in tool_names
    assert getattr(mode, "requires_tool_consultation", True) is True
    assert mode.requires_enrichment is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_skips_when_only_cosmetic_changes() -> None:
    """Cambios solo cosméticos no deben disparar evaluación LLM."""
    from kosmo.contracts.ai.consistency import ConsistencyStatus
    from kosmo.domain.sdd.document_converters import markdown_to_document

    # Arrange
    project = _make_project("prj_cos")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    await feature_repo.save(_make_feature("feat_cos", "prj_cos", "Gestión de catálogo", number=1))

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()
    await document_repo.save_version(
        ProjectId("prj_cos"),
        SpecPhase.DESCUBRIMIENTO,
        "## Visión\n\nVisión original.",
        [],
    )
    document_repo.discovery_docs["prj_cos"] = markdown_to_document("## Visión\n\nVisión  original.")

    agent = StubConsistencyAgent(affected_ids=["feat_cos"])
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_cos"),
        applied_changes=[],
    )

    # Assert
    assert result.status == ConsistencyStatus.ANALIZADO_SIN_IMPACTO
    assert agent.skill_names == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_runs_with_chat_change_despite_cosmetic_diff() -> None:
    """Un cambio del chat sin clasificar (no cosmético) evalúa normalmente."""
    from kosmo.domain.sdd.document_converters import markdown_to_document

    # Arrange
    project = _make_project("prj_cos2")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    await feature_repo.save(_make_feature("feat_cos2", "prj_cos2", "Gestión de catálogo", number=1))

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()
    document_repo.discovery_docs["prj_cos2"] = markdown_to_document("## Visión\n\nVisión original.")

    agent = StubConsistencyAgent(affected_ids=["feat_cos2"])
    uc = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)

    change = _applied_change("chg_cos2", before="visión original", after="visión ampliada")

    # Act
    result = await uc.evaluate(
        source_phase=SpecPhase.DESCUBRIMIENTO,
        target_phase=SpecPhase.CARACTERISTICAS,
        project_id=ProjectId("prj_cos2"),
        applied_changes=[change],
    )

    # Assert
    assert result.affected_artifact_ids == ["feat_cos2"]
    assert any(s in agent.skill_names for s in ("consistency_evaluate_discovery_features", "consistency_evaluate"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_impact_requirements_with_statement_fragment() -> None:
    """Un fragmento de statement sin ### debe enriquecerse con display_id y título."""
    from kosmo.application.consistency.enrich_impact import enrich_impact_items
    from kosmo.contracts.ai.consistency import (
        ArtifactAction,
        ConsistencyEvaluationOutput,
        ConsistencyStatus,
    )

    # Arrange
    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_pedidos", "prj_01", "Gestión de pedidos", number=6)
    await feature_repo.save(feat)

    req_md = (
        "### REQ-6.1 Descuento automático de stock\n\n"
        "**Basado en eventos**\n\n"
        "CUANDO el colaborador de tienda confirma un pedido, el sistema debe descontar automáticamente "
        "las cantidades de cada producto del inventario disponible.\n"
    )
    requirement_repo = InMemoryRequirementRepository()
    await requirement_repo.save(FeatureId("feat_pedidos"), req_md)
    diagram_repo = InMemoryActivityDiagramRepository()

    result = ConsistencyEvaluationOutput(
        report_id="cnr_req_test",
        status=ConsistencyStatus.ANALIZADO_CON_IMPACTO,
        affected_artifact_ids=["feat_pedidos"],
        actions=[
            ArtifactAction(
                artifact_id="feat_pedidos",
                action="update",
                rationale="El actor colaborador de tienda fue eliminado del alcance.",
                suggested_field="REQ-6.1",
                suggested_before=(
                    "CUANDO el colaborador de tienda confirma un pedido, el sistema debe descontar "
                    "automáticamente las cantidades de cada producto del inventario disponible."
                ),
                suggested_after=(
                    "CUANDO el sistema recibe un pedido confirmado, debe descontar "
                    "automáticamente las cantidades de cada producto del inventario disponible."
                ),
            )
        ],
    )

    # Act
    items = await enrich_impact_items(
        result,
        SpecPhase.REQUISITOS,
        SpecPhase.DESCUBRIMIENTO,
        feature_repo,
        requirement_repo,
        diagram_repo,
    )

    # Assert
    assert len(items) == 1
    item = items[0]
    assert item.target_id == "feat_pedidos"
    assert item.artifact_type == "EARSRequirement"
    assert item.target_display_id == "REQ-6.1"
    assert item.target_title == "Descuento automático de stock"
    assert item.section == "statement"
    assert item.action == "update"
    assert item.diff is not None
    assert "colaborador de tienda" in str(item.diff.get("before"))
    assert "el sistema recibe" in str(item.diff.get("after"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_impact_requirements_with_actor_subphrase_fragment() -> None:
    """Un fragmento corto como el nombre del actor debe correlacionarse con el requisito que lo contiene."""
    from kosmo.application.consistency.enrich_impact import enrich_impact_items
    from kosmo.contracts.ai.consistency import (
        ArtifactAction,
        ConsistencyEvaluationOutput,
        ConsistencyStatus,
    )

    # Arrange
    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_pedidos2", "prj_01", "Gestión de pedidos", number=6)
    await feature_repo.save(feat)

    req_md = (
        "### REQ-6.1 Descuento automático de stock\n\n"
        "**Basado en eventos**\n\n"
        "CUANDO el colaborador de tienda confirma un pedido, "
        "el sistema debe descontar automáticamente las cantidades.\n\n"
        "### REQ-6.2 Notificación al cliente\n\n"
        "**Ubicuo**\n\n"
        "El sistema debe notificar al cliente cuando el pedido se envíe.\n"
    )
    requirement_repo = InMemoryRequirementRepository()
    await requirement_repo.save(FeatureId("feat_pedidos2"), req_md)
    diagram_repo = InMemoryActivityDiagramRepository()

    result = ConsistencyEvaluationOutput(
        report_id="cnr_req_test2",
        status=ConsistencyStatus.ANALIZADO_CON_IMPACTO,
        affected_artifact_ids=["feat_pedidos2"],
        actions=[
            ArtifactAction(
                artifact_id="feat_pedidos2",
                action="update",
                rationale="Se eliminó el actor colaborador de tienda.",
                suggested_before="el colaborador de tienda",
                suggested_after="el encargado de despacho",
            )
        ],
    )

    # Act
    items = await enrich_impact_items(
        result,
        SpecPhase.REQUISITOS,
        SpecPhase.DESCUBRIMIENTO,
        feature_repo,
        requirement_repo,
        diagram_repo,
    )

    # Assert
    assert len(items) == 1
    item = items[0]
    assert item.target_display_id == "REQ-6.1"
    assert item.target_title == "Descuento automático de stock"
    assert item.action == "update"
    assert item.diff == {
        "field": "statement",
        "before": "el colaborador de tienda",
        "after": "el encargado de despacho",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_impact_requirements_direct_match_by_display_id() -> None:
    """Cuando suggested_field coincide con el display_id (REQ-X.Y), se asocia directamente."""
    from kosmo.application.consistency.enrich_impact import enrich_impact_items
    from kosmo.contracts.ai.consistency import (
        ArtifactAction,
        ConsistencyEvaluationOutput,
        ConsistencyStatus,
    )

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_pedidos3", "prj_01", "Gestión de pedidos", number=6)
    await feature_repo.save(feat)

    req_md = (
        "### REQ-6.1 Descuento automático de stock\n\n"
        "**Basado en eventos**\n\n"
        "CUANDO el colaborador de tienda confirma un pedido, "
        "el sistema debe descontar automáticamente las cantidades.\n\n"
        "### REQ-6.2 Notificación al cliente\n\n"
        "**Ubicuo**\n\n"
        "El sistema debe notificar al cliente cuando el pedido se envíe.\n"
    )
    requirement_repo = InMemoryRequirementRepository()
    await requirement_repo.save(FeatureId("feat_pedidos3"), req_md)
    diagram_repo = InMemoryActivityDiagramRepository()

    result = ConsistencyEvaluationOutput(
        report_id="cnr_req_direct",
        status=ConsistencyStatus.ANALIZADO_CON_IMPACTO,
        affected_artifact_ids=["feat_pedidos3"],
        actions=[
            ArtifactAction(
                artifact_id="feat_pedidos3",
                action="update",
                rationale="Renombrar actor en requisito REQ-6.1",
                suggested_field="REQ-6.1",
                suggested_before="CUANDO el colaborador de tienda confirma un pedido",
                suggested_after="CUANDO Milkventario confirma un pedido",
            )
        ],
    )

    items = await enrich_impact_items(
        result,
        SpecPhase.REQUISITOS,
        SpecPhase.DESCUBRIMIENTO,
        feature_repo,
        requirement_repo,
        diagram_repo,
    )

    assert len(items) == 1
    item = items[0]
    assert item.target_display_id == "REQ-6.1"
    assert item.target_title == "Descuento automático de stock"
    assert item.action == "update"
    assert item.diff == {
        "field": "statement",
        "before": "CUANDO el colaborador de tienda confirma un pedido",
        "after": "CUANDO Milkventario confirma un pedido",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_impact_feature_diff_no_muestra_origen() -> None:
    """El diff de una feature no expone el 'Origen:' interno al usuario final."""
    from kosmo.application.consistency.enrich_impact import enrich_impact_items
    from kosmo.contracts.ai.consistency import (
        ArtifactAction,
        ConsistencyEvaluationOutput,
        ConsistencyStatus,
    )

    # Arrange
    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_pedidos", "prj_01", "Gestión de pedidos", number=6)
    feat.description = "El repartidor del barrio marca el avance del pedido en cada etapa."
    await feature_repo.save(feat)

    result = ConsistencyEvaluationOutput(
        report_id="cnr_feat_origen",
        status=ConsistencyStatus.ANALIZADO_CON_IMPACTO,
        affected_artifact_ids=["feat_pedidos"],
        actions=[
            ArtifactAction(
                artifact_id="feat_pedidos",
                action="update",
                rationale="El actor Repartidor del barrio fue eliminado del descubrimiento.",
                suggested_field="description",
                suggested_before=(
                    "El repartidor del barrio marca el avance del pedido en cada etapa.\n"
                    "Origen: Meta Gestion de pedidos en Metas del producto."
                ),
                suggested_after=(
                    "El avance del pedido se registra en cada etapa.\n"
                    "Origen: Meta Gestion de pedidos en Metas del producto."
                ),
            )
        ],
    )
    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()

    # Act
    items = await enrich_impact_items(
        result,
        SpecPhase.CARACTERISTICAS,
        SpecPhase.DESCUBRIMIENTO,
        feature_repo,
        requirement_repo,
        diagram_repo,
    )

    # Assert — el usuario solo ve la descripción, sin "Origen:"
    assert len(items) == 1
    item = items[0]
    assert item.artifact_type == "Feature"
    assert item.diff is not None
    assert item.diff["before"] == "El repartidor del barrio marca el avance del pedido en cada etapa."
    assert item.diff["after"] == "El avance del pedido se registra en cada etapa."
    assert "Origen" not in str(item.diff)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cascading_consistency_end_to_end_actor_removal() -> None:
    """La eliminación de un actor genera impactos en características, requisitos y modelo."""
    from kosmo.application.consistency.cascade_consistency import CascadingConsistencyUseCase
    from kosmo.contracts.sdd.activity_diagram import DiagramaActividad
    from kosmo.contracts.sdd.ids import ActivityDiagramId

    # Arrange
    project = _make_project("prj_cascade")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_pedidos", "prj_cascade", "Gestión de pedidos", number=6)
    feat.description = "Permite al colaborador de tienda gestionar y confirmar pedidos."
    await feature_repo.save(feat)

    req_md = (
        "### REQ-6.1 Descuento automático de stock\n\n"
        "**Basado en eventos**\n\n"
        "CUANDO el colaborador de tienda confirma un pedido, el sistema debe descontar automáticamente "
        "las cantidades de cada producto del inventario disponible.\n"
    )
    requirement_repo = InMemoryRequirementRepository()
    await requirement_repo.save(FeatureId("feat_pedidos"), req_md)

    diagram_repo = InMemoryActivityDiagramRepository()
    diagram_syntax = (
        "@startuml\n|Colaborador de tienda|\nstart\n:Confirmar pedido;\n|Sistema|\n:Descontar stock;\nstop\n@enduml"
    )
    await diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("feat_pedidos"),
            feature_id=FeatureId("feat_pedidos"),
            diagram_syntax=diagram_syntax,
        )
    )

    document_repo = InMemoryDocumentRepository()

    agent = _TwoPhaseAgent(
        detection_report={
            "actions": [
                {
                    "artifact_id": "feat_pedidos",
                    "action": "update",
                    "rationale": "El actor colaborador de tienda fue eliminado.",
                    "suggested_field": "REQ-6.1",
                }
            ],
            "overall_rationale": "Impacto por remoción de actor",
        },
        corrections={
            "feat_pedidos": {
                "suggested_field": "statement",
                "suggested_before": (
                    "CUANDO el colaborador de tienda confirma un pedido, el sistema debe descontar "
                    "automáticamente las cantidades de cada producto del inventario disponible."
                ),
                "suggested_after": (
                    "CUANDO el cliente confirma un pedido, el sistema debe descontar "
                    "automáticamente las cantidades de cada producto del inventario disponible."
                ),
            }
        },
    )

    evaluator = _make_uc(agent, feature_repo, requirement_repo, diagram_repo, document_repo)
    cascade_uc = CascadingConsistencyUseCase(
        project_repo=project_repo,
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        diagram_repo=diagram_repo,
        evaluator=evaluator,
    )

    change = _applied_change(
        "chg_actor",
        before="- **Colaborador de tienda**: Empleado de tienda.",
        after="",
    )

    # Act
    output = await cascade_uc.execute(
        project_id=ProjectId("prj_cascade"),
        source_phase=SpecPhase.DESCUBRIMIENTO,
        applied_changes=[change],
    )

    # Assert: debe haber impacto en Requisitos con REQ-6.1
    req_impacts = [i for i in output.downstream_impact if i.get("artifact_type") == "EARSRequirement"]
    assert len(req_impacts) >= 1
    assert req_impacts[0]["targetDisplayId"] == "REQ-6.1"
    assert req_impacts[0]["targetTitle"] == "Descuento automático de stock"
    assert "colaborador de tienda" in str(req_impacts[0]["diff"]["before"])


@pytest.mark.unit
def test_validate_action_allows_truncated_artifact_content() -> None:
    from kosmo.application.consistency.evaluate_consistency import _validate_action

    # Un artefacto largo cuyo contenido termina en truncado
    desc = "## Sección inicial\nTexto del inicio.\n[…contenido truncado…]"
    # El LLM sugiere un before que estaba en la parte truncada (no aparece en desc)
    is_valid = _validate_action(
        artifact_id="feat_01",
        action="update",
        suggested_before="Texto lejano que no está en el resumen",
        suggested_after="Texto corregido",
        artifact_desc=desc,
        artifact_type="EARSRequirement",
    )

    # Debe ser permitido y no rechazado falsamente
    assert is_valid is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_evaluate_implementation_marks_status_requires_review() -> None:
    from datetime import UTC, datetime

    from kosmo.contracts.sdd.codegen import FeatureImplementation, FeatureImplementationStatus
    from kosmo.contracts.sdd.ids import ImplementationId
    from tests.unit.fakes import InMemoryFeatureImplementationRepository

    project = _make_project("prj_impl_eval")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(project)

    feature_repo = InMemoryFeatureRepository()
    feature = _make_feature("feat_impl", "prj_impl_eval", "Gestión de pedidos", number=1)
    await feature_repo.save(feature)

    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    impl_repo = InMemoryFeatureImplementationRepository()
    now = datetime.now(UTC)
    impl = FeatureImplementation(
        id=ImplementationId("impl_feat_01"),
        feature_id=feature.id,
        project_id=project.id,
        status=FeatureImplementationStatus.IMPLEMENTED,
        attempt_count=1,
        max_attempts=3,
        generated_files=("src/orders.ts",),
        created_at=now,
        updated_at=now,
    )
    await impl_repo.save(impl)

    agent = StubConsistencyAgent(affected_ids=[str(feature.id)])
    uc = EvaluateConsistencyUseCase(
        agent=agent,
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        diagram_repo=diagram_repo,
        document_repo=document_repo,
        implementation_repo=impl_repo,
    )

    result = await uc.evaluate(
        source_phase=SpecPhase.REQUISITOS,
        target_phase=SpecPhase.IMPLEMENTACION,
        project_id=project.id,
        applied_changes=[_applied_change("chg_req", before="REQ-1", after="REQ-1 modificado")],
    )

    assert str(feature.id) in result.affected_artifact_ids
    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.artifact_id == str(feature.id)
    assert action.action == "update"
    assert action.suggested_field == "status"
    assert action.suggested_after == "requires_review"


@pytest.mark.asyncio
async def test_fetch_downstream_artifacts_does_not_truncate_large_documents() -> None:
    feature_repo = InMemoryFeatureRepository()
    requirement_repo = InMemoryRequirementRepository()
    diagram_repo = InMemoryActivityDiagramRepository()
    document_repo = InMemoryDocumentRepository()

    project = _make_project("prj_large_doc")
    feature = _make_feature("feat_large", "prj_large_doc", "Feature Grande", number=1)
    await feature_repo.save(feature)

    # Requisitos de 30,000 caracteres (antes truncados a 20,000)
    large_req_md = "## Requisitos EARS\n" + ("- REQ: El sistema shall registrar logs detallados.\n" * 600)
    assert len(large_req_md) > 25000
    await requirement_repo.save(feature.id, large_req_md)

    # Documento de descubrimiento de 12,000 caracteres (antes truncado a 8,000)
    from kosmo.contracts.sdd.document import DocumentNode, RichTextDocument, SectionHeading

    nodes = [
        DocumentNode(
            type="heading",
            heading=SectionHeading(text="Visión", level=1, slug="vision"),
            content="Inicio de la visión",
        )
    ]
    for i in range(50):
        nodes.append(
            DocumentNode(
                type="paragraph",
                content=f"Detalle extendido de descubrimiento paso {i}: " + ("x" * 200),
            )
        )
    large_doc = RichTextDocument(nodes=nodes)

    await document_repo.save_discovery(project.id, large_doc)

    uc = EvaluateConsistencyUseCase(
        agent=StubConsistencyAgent(),
        feature_repo=feature_repo,
        requirement_repo=requirement_repo,
        diagram_repo=diagram_repo,
        document_repo=document_repo,
    )

    # Descubrimiento downstream
    disc_artifacts = await uc._fetch_downstream_artifacts(SpecPhase.DESCUBRIMIENTO, project.id)
    assert len(disc_artifacts) == 1
    assert "[…contenido truncado…]" not in disc_artifacts[0].description
    assert len(disc_artifacts[0].description) > 9000

    # Requisitos downstream
    req_artifacts = await uc._fetch_downstream_artifacts(SpecPhase.REQUISITOS, project.id)
    assert len(req_artifacts) == 1
    assert "[…contenido truncado…]" not in req_artifacts[0].description
    assert len(req_artifacts[0].description) == len(large_req_md)

    # Requisitos como fuente upstream
    source_content = await uc._fetch_source_content(SpecPhase.REQUISITOS, project.id)
    assert "[…contenido truncado…]" not in source_content
    assert len(source_content) > 25000


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_impact_concurrent_preloading_and_deduplication() -> None:
    """Verifica que enrich_impact_items precargue features y requisitos concurrentemente y deduplique llamadas."""
    from kosmo.application.consistency.enrich_impact import enrich_impact_items
    from kosmo.contracts.ai.consistency import (
        ArtifactAction,
        ConsistencyEvaluationOutput,
        ConsistencyStatus,
    )

    feature_repo = InMemoryFeatureRepository()
    feat1 = _make_feature("feat_batch_1", "prj_batch", "Característica 1", number=1)
    feat2 = _make_feature("feat_batch_2", "prj_batch", "Característica 2", number=2)
    await feature_repo.save(feat1)
    await feature_repo.save(feat2)

    req_md1 = "### REQ-1.1 Paso 1\n\nEl sistema debe ejecutar paso 1.\n"
    req_md2 = "### REQ-2.1 Paso 2\n\nEl sistema debe ejecutar paso 2.\n"

    requirement_repo = InMemoryRequirementRepository()
    await requirement_repo.save(FeatureId("feat_batch_1"), req_md1)
    await requirement_repo.save(FeatureId("feat_batch_2"), req_md2)
    diagram_repo = InMemoryActivityDiagramRepository()

    original_by_id = feature_repo.by_id
    by_id_calls: list[str] = []

    async def spied_by_id(fid: FeatureId, *, for_update: bool = False):
        by_id_calls.append(str(fid))
        return await original_by_id(fid, for_update=for_update)

    feature_repo.by_id = spied_by_id  # type: ignore[assignment]

    result = ConsistencyEvaluationOutput(
        report_id="cnr_batch",
        status=ConsistencyStatus.ANALIZADO_CON_IMPACTO,
        affected_artifact_ids=["feat_batch_1", "feat_batch_2", "feat_batch_1"],
        actions=[
            ArtifactAction(
                artifact_id="feat_batch_1",
                action="update",
                rationale="Cambio 1",
            ),
            ArtifactAction(
                artifact_id="feat_batch_2",
                action="update",
                rationale="Cambio 2",
            ),
        ],
    )

    items = await enrich_impact_items(
        result,
        SpecPhase.REQUISITOS,
        SpecPhase.DESCUBRIMIENTO,
        feature_repo,
        requirement_repo,
        diagram_repo,
    )

    # Solo debe haber consultado 2 veces por ID único a pesar de tener 3 IDs en affected_artifact_ids
    assert len(by_id_calls) == 2
    assert set(by_id_calls) == {"feat_batch_1", "feat_batch_2"}
    # Los items enriquecidos preservan el orden y multiplicidad de affected_artifact_ids
    assert len(items) == 3
    assert items[0].target_id == "feat_batch_1"
    assert items[1].target_id == "feat_batch_2"
    assert items[2].target_id == "feat_batch_1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enrich_impact_modelo_concurrent_preloading() -> None:
    """Verifica que enrich_impact_items para modelo verifique existencia concurrentemente."""
    from kosmo.application.consistency.enrich_impact import enrich_impact_items
    from kosmo.contracts.ai.consistency import (
        ArtifactAction,
        ConsistencyEvaluationOutput,
        ConsistencyStatus,
    )
    from kosmo.contracts.sdd.activity_diagram import DiagramaActividad
    from kosmo.contracts.sdd.ids import ActivityDiagramId

    feature_repo = InMemoryFeatureRepository()
    feat = _make_feature("feat_m1", "prj_m", "Modelo Feature", number=1)
    await feature_repo.save(feat)

    diagram_repo = InMemoryActivityDiagramRepository()
    await diagram_repo.save(
        DiagramaActividad(
            id=ActivityDiagramId("feat_m1"),
            feature_id=FeatureId("feat_m1"),
            diagram_syntax="@startuml\nstart\nstop\n@enduml",
        )
    )
    requirement_repo = InMemoryRequirementRepository()

    result = ConsistencyEvaluationOutput(
        report_id="cnr_m",
        status=ConsistencyStatus.ANALIZADO_CON_IMPACTO,
        affected_artifact_ids=["feat_m1"],
        actions=[ArtifactAction(artifact_id="feat_m1", action="update", rationale="Cambio UML")],
    )

    items = await enrich_impact_items(
        result,
        SpecPhase.MODELO,
        SpecPhase.REQUISITOS,
        feature_repo,
        requirement_repo,
        diagram_repo,
    )

    assert len(items) == 1
    assert items[0].artifact_type == "ActivityDiagram"
    assert items[0].target_id == "feat_m1"
