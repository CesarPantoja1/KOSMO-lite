from __future__ import annotations

from typing import Any

from kosmo.contracts.auth.context import current_user_id
from kosmo.contracts.persistence.persistence import OutboxPort
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.ids import ProjectId
from kosmo.domain.sdd.id_generator import IdGenerator
from kosmo.domain.sdd.traceability_tracer import trace_downstream_phases


async def trigger_downstream_evaluation(
    outbox: OutboxPort | None,
    *,
    project_id: ProjectId,
    source_phase: SpecPhase,
    changes: list[dict[str, str]],
    user_id: str | None = None,
) -> None:
    """Encoda la evaluación de consistencia de todas las fases a la derecha
    de la fase fuente. No-op sin outbox o sin fases downstream."""
    if outbox is None:
        return
    if not trace_downstream_phases(source_phase):
        return
    resolved_user_id = user_id or current_user_id.get()
    payload: dict[str, Any] = {
        "project_id": str(project_id),
        "source_phase": source_phase.value,
        "changes": changes,
        "operation_id": IdGenerator.generate("operation"),
    }
    if resolved_user_id:
        payload["user_id"] = str(resolved_user_id)
    await outbox.enqueue("consistency_evaluate", payload)
