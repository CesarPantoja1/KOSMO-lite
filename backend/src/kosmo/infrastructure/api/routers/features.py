from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status

from kosmo.application.codegen.delete_feature_code import DeleteFeatureCodeInput
from kosmo.application.features import (
    CheckFeatureConsistencyInput,
    CheckFeatureConsistencyUseCase,
    CreateCharacteristicInput,
    CreateCharacteristicUseCase,
    EditFeatureInput,
    EditFeatureUseCase,
    GenerateFeaturesInput,
    GenerateFeaturesUseCase,
    SaveSelectedFeaturesInput,
    SaveSelectedFeaturesUseCase,
    SuggestFeaturesInput,
    SuggestFeaturesUseCase,
)
from kosmo.application.features.delete_feature import DeleteFeatureUseCase
from kosmo.application.features.list_features import (
    ListFeaturesInput,
    ListFeaturesUseCase,
)
from kosmo.contracts.auth import Principal
from kosmo.contracts.sdd.errors import (
    DocumentNotFoundError,
    FeatureNotFoundError,
    ProjectNotFoundError,
)
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.infrastructure.api.composition import AppContainer
from kosmo.infrastructure.api.dependencies.auth import get_principal, verify_project_owner
from kosmo.infrastructure.api.dependencies.container import get_container
from kosmo.infrastructure.api.dependencies.rate_limit import ProjectGenerationRateLimiter
from kosmo.infrastructure.api.schemas import (
    CheckConsistencyRequestView,
    CreateCharacteristicRequest,
    EditFeatureManualRequest,
    FeatureResponse,
    FeatureSuggestionResponse,
    InconsistencyResultView,
    SaveSelectedFeaturesRequest,
)

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/features",
    tags=["features"],
    dependencies=[Depends(verify_project_owner)],
)

_generation_rate_limiter = ProjectGenerationRateLimiter()


def _generate_features(request: Request) -> GenerateFeaturesUseCase:
    return get_container(request).features.generate_features


def _suggest_features(request: Request) -> SuggestFeaturesUseCase:
    return get_container(request).features.suggest_features


def _save_selected_features(request: Request) -> SaveSelectedFeaturesUseCase:
    return get_container(request).features.save_selected_features


def _create_characteristic(request: Request) -> CreateCharacteristicUseCase:
    return get_container(request).features.create_characteristic


def _edit_feature(request: Request) -> EditFeatureUseCase:
    return get_container(request).features.edit_feature


def _list_features(request: Request) -> ListFeaturesUseCase:
    return get_container(request).features.list_features


@router.post(
    "",
    summary="Generar características del producto con IA",
    description=(
        "Genera características de alto nivel evaluando el documento de "
        "descubrimiento del proyecto. Las características representan capacidades "
        "funcionales del producto software a construir."
    ),
    response_model=list[FeatureResponse],
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Características generadas exitosamente."},
        status.HTTP_401_UNAUTHORIZED: {"description": "Token de acceso inválido o ausente."},
    },
)
async def generate_features(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    _rate: Annotated[None, Depends(_generation_rate_limiter)],
    use_case: Annotated[GenerateFeaturesUseCase, Depends(_generate_features)],
) -> list[FeatureResponse]:
    output = await use_case.execute(GenerateFeaturesInput(project_id=ProjectId(project_id)))
    return [_feature_to_response(f) for f in output.features]


@router.get(
    "",
    summary="Listar características del proyecto",
    description=(
        "Devuelve todas las características asociadas a un proyecto. Requiere autenticación mediante Bearer token."
    ),
    response_model=list[FeatureResponse],
    responses={
        status.HTTP_200_OK: {
            "description": "Lista de características del proyecto.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Token de acceso inválido o ausente.",
        },
    },
)
async def list_features(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    uc: Annotated[ListFeaturesUseCase, Depends(_list_features)],
) -> list[FeatureResponse]:
    output = await uc.execute(ListFeaturesInput(project_id=ProjectId(project_id)))
    return [_feature_to_response(f) for f in output.features]


@router.post(
    "/suggest",
    summary="Sugerir nuevas características",
    description=(
        "Sugiere 3 características adicionales basadas en el documento "
        "de descubrimiento, evitando duplicar las existentes. "
        "Requiere autenticación mediante Bearer token."
    ),
    response_model=list[FeatureSuggestionResponse],
    responses={
        status.HTTP_200_OK: {
            "description": "Sugerencias de características generadas.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Token de acceso inválido o ausente.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Documento de descubrimiento no encontrado.",
        },
        status.HTTP_502_BAD_GATEWAY: {
            "description": "Error al invocar el servicio de IA.",
        },
    },
)
async def suggest_features(
    project_id: str,
    _principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[SuggestFeaturesUseCase, Depends(_suggest_features)],
    _rate: Annotated[None, Depends(_generation_rate_limiter)] = None,
) -> list[FeatureSuggestionResponse]:
    try:
        output = await use_case.execute(SuggestFeaturesInput(project_id=ProjectId(project_id)))
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.problem.detail,
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error al generar sugerencias: {exc}",
        ) from exc
    return [
        FeatureSuggestionResponse(
            number=s.number,
            title=s.title,
            description=s.description,
            origin=s.origin,
        )
        for s in output.suggestions
    ]


@router.post(
    "/manual",
    summary="Crear característica manualmente",
    description=(
        "Crea una nueva característica. Si no se proporciona origin, la IA lo deriva "
        "del descubrimiento y verifica coherencia. Si la IA detecta inconsistencia, "
        "devuelve is_saved=false con el origin derivado y la razón. El guardado nunca "
        "se fuerza: si contradice el Descubrimiento, primero debe modificarse ese documento."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Característica creada exitosamente o rechazada por inconsistencia.",
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Datos de entrada inválidos (título vacío, título muy largo, descripción muy larga).",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Token de acceso inválido o ausente.",
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Error inesperado del servidor.",
        },
    },
)
async def create_characteristic_manual(
    project_id: str,
    payload: Annotated[CreateCharacteristicRequest, Body(...)],
    _principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[CreateCharacteristicUseCase, Depends(_create_characteristic)],
) -> dict[str, object]:
    try:
        output = await use_case.execute(
            CreateCharacteristicInput(
                project_id=ProjectId(project_id),
                title=payload.title,
                description=payload.description,
                origin=payload.origin,
            )
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if output.is_saved and output.characteristic is not None:
        return {
            "is_saved": True,
            "feature": _feature_to_response(output.characteristic, output.warnings).model_dump(),
            "origin": output.origin,
            "is_consistent": output.is_consistent,
            "warnings": list(output.warnings),
        }
    return {
        "is_saved": False,
        "origin": output.origin,
        "is_consistent": output.is_consistent,
        "inconsistency_reason": output.inconsistency_reason,
        "warnings": list(output.warnings),
    }


@router.put(
    "/{feature_id}/manual",
    summary="Editar característica manualmente",
    description=(
        "Edita una característica de forma manual. "
        "Si los cambios contradicen flagrantemente el documento de Descubrimiento, "
        "el guardado es rechazado por consistencia."
    ),
    response_model=FeatureResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Característica editada exitosamente.",
        },
        status.HTTP_409_CONFLICT: {
            "description": "Contradicción detectada. No se guardaron los cambios.",
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Característica no encontrada.",
        },
    },
)
async def edit_characteristic_manual(
    project_id: str,
    feature_id: str,
    payload: Annotated[EditFeatureManualRequest, Body(...)],
    _principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[EditFeatureUseCase, Depends(_edit_feature)],
) -> FeatureResponse:
    try:
        output = await use_case.execute(
            EditFeatureInput(
                project_id=ProjectId(project_id),
                feature_id=FeatureId(feature_id),
                title=payload.title,
                description=payload.description,
            )
        )
    except FeatureNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.problem.detail,
        ) from exc

    if not output.is_saved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=output.inconsistency_reason or "Inconsistencia detectada en el documento.",
        )

    assert output.feature is not None
    return _feature_to_response(output.feature, output.warnings)


@router.post(
    "/save",
    summary="Guardar características seleccionadas",
    description=(
        "Guarda las características que el usuario seleccionó desde las "
        "sugerencias de la IA. Requiere autenticación mediante Bearer token."
    ),
    response_model=list[FeatureResponse],
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "Características guardadas exitosamente.",
        },
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Token de acceso inválido o ausente.",
        },
    },
)
async def save_selected_features(
    project_id: str,
    payload: Annotated[SaveSelectedFeaturesRequest, Body(...)],
    _principal: Annotated[Principal, Depends(get_principal)],
    use_case: Annotated[SaveSelectedFeaturesUseCase, Depends(_save_selected_features)],
) -> list[FeatureResponse]:
    items: list[dict[str, object]] = [
        {
            "title": f.title,
            "description": f.description,
            "origin": f.origin,
        }
        for f in payload.features
    ]
    output = await use_case.execute(
        SaveSelectedFeaturesInput(
            project_id=ProjectId(project_id),
            features=items,
        )
    )
    return [_feature_to_response(f) for f in output.features]


def _feature_to_response(f: Any, warnings: Sequence[str] = ()) -> FeatureResponse:
    return FeatureResponse(
        id=str(f.id),
        project_id=str(f.project_id),
        number=f.number,
        title=f.title,
        slug=f.slug,
        description=f.description,
        origin=f.origin,
        display_id=f.display_id,
        warnings=list(warnings),
    )


def _delete_feature_uc(request: Request) -> DeleteFeatureUseCase:
    return get_container(request).consistency.delete_feature


def _check_feature_consistency(request: Request) -> CheckFeatureConsistencyUseCase:
    return get_container(request).features.check_feature_consistency


@router.delete(
    "/{feature_id}",
    summary="Eliminar característica",
    description="Elimina una característica y todos sus artefactos asociados (requisitos, diagrama). "
    "Si tenía código generado, se elimina en background y la aplicación se valida para que "
    "siempre quede funcional.",
    status_code=status.HTTP_200_OK,
)
async def delete_feature(
    project_id: str,
    feature_id: str,
    principal: Annotated[Principal, Depends(get_principal)],
    uc: Annotated[DeleteFeatureUseCase, Depends(_delete_feature_uc)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, str]:

    try:
        feature = await uc.execute(
            project_id=ProjectId(project_id),
            feature_id=FeatureId(feature_id),
        )
    except FeatureNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.problem.detail) from e
    except ProjectNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=e.problem.detail) from e

    # Eliminación del código generado en background: el frontend observa los eventos
    # en GET /implementations/impl_<feature_id>/events
    broker_instance = container.codegen.implementation_broker
    broker_instance.start_implementation(
        implementation_id=f"impl_{feature_id}",
        use_case=container.codegen.delete_feature_code,
        input_data=DeleteFeatureCodeInput(feature=feature),
        project_id=str(feature.project_id),
        user_id=principal.subject,
    )

    return {"status": "deleted", "feature_id": feature_id}


@router.post(
    "/{feature_id}/consistency/check",
    summary="Verificar consistencia antes de guardado manual",
    description=(
        "Verifica que el contenido editado manualmente no contradiga "
        "flagrantemente el documento de Descubrimiento. Invoca al agente IA "
        "con el nuevo contenido y el documento fuente. Si hay inconsistencia, "
        "el guardado debe rechazarse mostrando un modal explicativo."
    ),
    response_model=InconsistencyResultView,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Resultado de la verificación."},
        status.HTTP_404_NOT_FOUND: {"description": "Proyecto o característica no encontrada."},
    },
)
async def check_feature_consistency(
    project_id: str,
    feature_id: str,
    payload: Annotated[CheckConsistencyRequestView, Body(...)],
    use_case: Annotated[CheckFeatureConsistencyUseCase, Depends(_check_feature_consistency)],
    _principal: Annotated[Principal, Depends(get_principal)],
) -> InconsistencyResultView:
    title = str(payload.content.get("title", ""))
    description = str(payload.content.get("description", ""))

    try:
        output = await use_case.execute(
            CheckFeatureConsistencyInput(
                project_id=ProjectId(project_id),
                feature_id=FeatureId(feature_id),
                title=title,
                description=description,
            )
        )
    except FeatureNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.problem.detail,
        ) from exc

    return InconsistencyResultView(
        is_consistent=output.is_consistent,
        reason=output.reason,
        conflicting_section=output.conflicting_section,
    )
