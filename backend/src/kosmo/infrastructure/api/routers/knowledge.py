from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status

from kosmo.application.knowledge import ConsolidateInput, ConsolidateKnowledgePatterns
from kosmo.contracts.auth import Principal
from kosmo.infrastructure.api.dependencies.auth import require_scopes
from kosmo.infrastructure.api.dependencies.container import get_container

router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["knowledge"],
)


@router.post(
    "/consolidate",
    summary="Consolidar patrones de conocimiento cross-project",
    status_code=status.HTTP_200_OK,
)
async def consolidate_patterns(
    _principal: Annotated[Principal, Depends(require_scopes("admin"))],
    request: Request,
) -> dict[str, Any]:
    uc: ConsolidateKnowledgePatterns = get_container(request).pipeline.consolidate_patterns
    result = await uc.execute(ConsolidateInput(sessions_limit=50))
    return {"phases": result}
