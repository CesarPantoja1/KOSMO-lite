from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from kosmo.infrastructure.api.dependencies.auth import get_principal
from kosmo.infrastructure.api.schemas import (
    AuthorizationCodeResponse,
    AuthorizeRequest,
    CreateCharacteristicRequest,
    CreateProjectRequest,
    DiscoveryResponse,
    FeatureResponse,
    FeatureSuggestionResponse,
    LogoutRequest,
    OAuthErrorResponse,
    PrincipalView,
    ProjectResponse,
    RegisterRequest,
    RegisterResponse,
    SaveSelectedFeaturesRequest,
    TokenExchangeRequest,
    TokenPairResponse,
    TokenRefreshRequest,
    UserPublic,
)

router = APIRouter(
    prefix="/api/v1/schemas",
    tags=["schemas"],
    dependencies=[Depends(get_principal)],
)


_REGISTRY: dict[str, type[BaseModel]] = {
    "CreateCharacteristicRequest": CreateCharacteristicRequest,
    "CreateProjectRequest": CreateProjectRequest,
    "DiscoveryResponse": DiscoveryResponse,
    "FeatureResponse": FeatureResponse,
    "FeatureSuggestionResponse": FeatureSuggestionResponse,
    "ProjectResponse": ProjectResponse,
    "RegisterRequest": RegisterRequest,
    "RegisterResponse": RegisterResponse,
    "AuthorizeRequest": AuthorizeRequest,
    "AuthorizationCodeResponse": AuthorizationCodeResponse,
    "TokenExchangeRequest": TokenExchangeRequest,
    "TokenRefreshRequest": TokenRefreshRequest,
    "LogoutRequest": LogoutRequest,
    "TokenPairResponse": TokenPairResponse,
    "PrincipalView": PrincipalView,
    "SaveSelectedFeaturesRequest": SaveSelectedFeaturesRequest,
    "UserPublic": UserPublic,
    "OAuthErrorResponse": OAuthErrorResponse,
}


@router.get("")
async def list_schemas() -> dict[str, list[str]]:
    return {"schemas": sorted(_REGISTRY.keys())}


@router.get("/{name}")
async def get_schema(name: str) -> dict[str, Any]:
    model = _REGISTRY.get(name)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schema '{name}' no encontrado",
        )
    return model.model_json_schema()
