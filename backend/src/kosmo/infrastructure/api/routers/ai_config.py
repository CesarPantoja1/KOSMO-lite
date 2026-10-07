from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from kosmo.application.ai.manage_ai_preferences import ManageAIPreferencesUseCase
from kosmo.application.ai.validate_ai_connection import ValidateAIConnectionUseCase
from kosmo.contracts.ai.ai_config import (
    SUPPORTED_PROVIDERS,
    AIConfigError,
    AIProvider,
    SaveAIConfigInput,
    TestAIConnectionInput,
)
from kosmo.contracts.auth import Principal
from kosmo.infrastructure.api.dependencies import (
    get_manage_ai_preferences_use_case,
    get_principal,
    get_validate_ai_connection_use_case,
)
from kosmo.infrastructure.api.schemas import (
    AIConfigResponse,
    AIModelInfoResponse,
    AIProviderInfoResponse,
    SaveAIConfigRequest,
    TestAIConnectionRequest,
    TestAIConnectionResponse,
)

router = APIRouter(prefix="/api/v1/ai-config", tags=["ai_config"])


@router.get(
    "/providers",
    response_model=list[AIProviderInfoResponse],
    summary="Devuelve el catálogo de proveedores y modelos de IA disponibles",
)
def get_providers() -> list[AIProviderInfoResponse]:
    return [
        AIProviderInfoResponse(
            value=p.value,
            label=p.label,
            models=[AIModelInfoResponse(id=m.id, display_name=m.display_name, tier=m.tier) for m in p.models],
        )
        for p in SUPPORTED_PROVIDERS
    ]


@router.get(
    "",
    response_model=AIConfigResponse,
    summary="Obtiene la configuracion de IA del usuario actual",
)
async def get_preferences(
    principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[ManageAIPreferencesUseCase, Depends(get_manage_ai_preferences_use_case)],
) -> AIConfigResponse:
    view = await use_case.get_preferences(principal.subject)
    return AIConfigResponse(
        provider=view.provider.value,
        model=view.model,
        is_custom=view.is_custom,
        has_api_key=view.has_api_key,
        masked_key=view.masked_key,
        updated_at=view.updated_at,
    )


@router.post(
    "",
    response_model=AIConfigResponse,
    summary="Guarda o actualiza la configuracion de IA del usuario",
)
async def save_preferences(
    request: SaveAIConfigRequest,
    req: Request,
    principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[ManageAIPreferencesUseCase, Depends(get_manage_ai_preferences_use_case)],
) -> AIConfigResponse:
    try:
        provider = AIProvider(request.provider)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Proveedor no soportado: {request.provider}",
        ) from None

    try:
        input_data = SaveAIConfigInput(
            provider=provider,
            model=request.model,
            api_key=request.api_key,
        )
        view = await use_case.save_preferences(principal.subject, input_data)
        try:
            container = getattr(req.app.state, "container", None)
            if container is not None:
                llm_client = getattr(container.pipeline, "llm_client", None)
                if llm_client is not None:
                    invalidate_fn = getattr(llm_client, "invalidate_cache", None)
                    if callable(invalidate_fn):
                        invalidate_fn(principal.subject)
        except Exception:
            pass
    except AIConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None

    return AIConfigResponse(
        provider=view.provider.value,
        model=view.model,
        is_custom=view.is_custom,
        has_api_key=view.has_api_key,
        masked_key=view.masked_key,
        updated_at=view.updated_at,
    )


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Elimina la configuracion de IA del usuario",
)
async def delete_preferences(
    req: Request,
    principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[ManageAIPreferencesUseCase, Depends(get_manage_ai_preferences_use_case)],
) -> None:
    await use_case.delete_preferences(principal.subject)
    try:
        container = getattr(req.app.state, "container", None)
        if container is not None:
            llm_client = getattr(container.pipeline, "llm_client", None)
            if llm_client is not None:
                invalidate_fn = getattr(llm_client, "invalidate_cache", None)
                if callable(invalidate_fn):
                    invalidate_fn(principal.subject)
    except Exception:
        pass


@router.post(
    "/test",
    response_model=TestAIConnectionResponse,
    summary="Valida las credenciales de conexion a IA",
)
async def test_connection(
    request: TestAIConnectionRequest,
    principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[ValidateAIConnectionUseCase, Depends(get_validate_ai_connection_use_case)],
) -> TestAIConnectionResponse:
    try:
        provider = AIProvider(request.provider)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Proveedor no soportado: {request.provider}",
        ) from None

    input_data = TestAIConnectionInput(
        provider=provider,
        model=request.model,
        api_key=request.api_key,
        user_id=principal.subject,
    )
    try:
        result = await use_case.execute(input_data)
        return TestAIConnectionResponse(
            is_connected=result.is_connected,
            detected_model=result.detected_model,
            message=result.message,
        )
    except AIConfigError as exc:
        return TestAIConnectionResponse(
            is_connected=False,
            detected_model=request.model,
            message=str(exc),
        )
