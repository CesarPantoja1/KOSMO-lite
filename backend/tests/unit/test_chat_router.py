from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from kosmo.application.chat.process_chat_message import (
    ProcessChatMessageInput,
    ProcessChatMessageOutput,
    ProcessChatMessageUseCase,
)
from kosmo.application.chat.validate_phase_context import (
    ValidatePhaseContextUseCase,
)
from kosmo.application.pipeline.context_builder import ContextBuilder
from kosmo.contracts.ai.chat import ChatRole, MensajeChat, ModificacionChat
from kosmo.contracts.auth import Principal
from kosmo.contracts.pipeline.phase_contexts import DiscoveryChatContext, FeatureChatContext
from kosmo.contracts.pipeline.phase_errors import PhaseTransitionError
from kosmo.contracts.sdd.document import SpecPhase
from kosmo.contracts.sdd.errors import FeatureNotFoundError
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import ChatMessageId, FeatureId, ProjectId
from kosmo.domain.sdd.document_converters import markdown_to_document
from kosmo.domain.sdd.id_generator import IdGenerator
from kosmo.infrastructure.api.routers.discovery import process_chat_message as discovery_chat
from kosmo.infrastructure.api.routers.feature_chat import (
    process_feature_chat_message as feature_chat,
)
from kosmo.infrastructure.api.routers.requirement_chat import (
    process_requirement_chat_message as requirement_chat,
)
from kosmo.infrastructure.api.schemas import ChatResponse, SendChatRequest
from tests.unit.conftest import DISCOVERY_VALID

_REAL_VALIDATE_UC = ValidatePhaseContextUseCase()


def _principal() -> Principal:
    return Principal(subject="usr_test123", scopes=frozenset({"*"}))


def _assistant_message(content: str = "Se aplicó el cambio.") -> MensajeChat:
    return MensajeChat(
        id=ChatMessageId(IdGenerator.generate("chat_message")),
        role=ChatRole.ASSISTANT,
        content=content,
        modification=ModificacionChat(
            applied=True,
            modified_section="Visión del producto",
            change_description=content,
        ),
    )


def _make_mock_uc(message: MensajeChat | None = None, exc: Exception | None = None) -> MagicMock:
    uc = MagicMock(spec=ProcessChatMessageUseCase)
    if exc:
        uc.execute = AsyncMock(side_effect=exc)
    else:
        output = ProcessChatMessageOutput(project_id=ProjectId("prj_01"), message=message or _assistant_message())
        uc.execute = AsyncMock(return_value=output)
    return uc


def _make_mock_builder(exc: Exception | None = None) -> MagicMock:
    builder = MagicMock(spec=ContextBuilder)
    if exc:
        builder.build_discovery_chat_context = AsyncMock(side_effect=exc)
        builder.build_feature_chat_context = AsyncMock(side_effect=exc)
        builder.build_requirement_chat_context = AsyncMock(side_effect=exc)
    else:
        builder.build_discovery_chat_context = AsyncMock(
            return_value=DiscoveryChatContext(current_document=markdown_to_document(DISCOVERY_VALID))
        )
        feature = Feature(
            id=FeatureId("feat_01"),
            number=1,
            title="Registrar gastos compartidos",
            slug="registrar-gastos-compartidos",
            description="El usuario ingresa un gasto.",
            project_id=ProjectId("prj_01"),
        )
        builder.build_feature_chat_context = AsyncMock(
            return_value=FeatureChatContext(
                feature=feature,
                discovery_document=markdown_to_document(DISCOVERY_VALID),
            )
        )
    return builder


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discovery_chat_returns_chat_response_with_modification() -> None:
    # Arrange
    uc = _make_mock_uc()
    builder = _make_mock_builder()
    payload = SendChatRequest(content="Cambia el público objetivo a pymes")

    # Act
    response = await discovery_chat("prj_01", payload, _principal(), uc, _REAL_VALIDATE_UC, builder)

    # Assert
    assert isinstance(response, ChatResponse)
    assert response.modification is not None
    assert response.modification.applied is True
    assert response.redirect is None
    input_data = uc.execute.await_args.args[0]
    assert isinstance(input_data, ProcessChatMessageInput)
    assert input_data.phase == SpecPhase.DESCUBRIMIENTO


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discovery_chat_returns_redirect_when_message_belongs_to_other_phase() -> None:
    # Arrange
    uc = _make_mock_uc()
    builder = _make_mock_builder()
    payload = SendChatRequest(content="Agrega la característica de login al sistema")

    # Act
    response = await discovery_chat("prj_01", payload, _principal(), uc, _REAL_VALIDATE_UC, builder)

    # Assert
    assert response.redirect is not None
    assert response.redirect.target_phase == "caracteristicas"
    assert response.modification is None
    uc.execute.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_feature_chat_redirects_business_change_to_discovery() -> None:
    # Arrange
    uc = _make_mock_uc()
    builder = _make_mock_builder()
    payload = SendChatRequest(content="Cambia el giro del negocio a venta de suscripciones")

    # Act
    response = await feature_chat("feat_01", payload, _principal(), uc, _REAL_VALIDATE_UC, builder)

    # Assert
    assert response.redirect is not None
    assert response.redirect.target_phase == "descubrimiento"
    uc.execute.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_feature_chat_passes_feature_context_and_project() -> None:
    # Arrange
    uc = _make_mock_uc()
    builder = _make_mock_builder()
    payload = SendChatRequest(content="Cambia el título a 'Registrar y editar gastos'")

    # Act
    response = await feature_chat("feat_01", payload, _principal(), uc, _REAL_VALIDATE_UC, builder)

    # Assert
    assert response.modification is not None
    assert response.modification.applied is True
    input_data = uc.execute.await_args.args[0]
    assert input_data.phase == SpecPhase.CARACTERISTICAS
    assert input_data.project_id == ProjectId("prj_01")
    assert input_data.context_id == "feat_01"
    assert isinstance(input_data.context, FeatureChatContext)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_requirement_chat_passes_requirement_context() -> None:
    # Arrange
    uc = _make_mock_uc(_assistant_message("REQ-1.1 actualizado."))
    builder = _make_mock_builder()
    from kosmo.contracts.pipeline.phase_contexts import RequirementChatContext
    from kosmo.contracts.sdd.document import EARSPattern
    from kosmo.contracts.sdd.ears import EARSRequirement
    from kosmo.contracts.sdd.ids import RequirementId

    builder.build_requirement_chat_context = AsyncMock(
        return_value=RequirementChatContext(
            requirement=EARSRequirement(
                id=RequirementId("req_01"),
                feature_id=FeatureId("feat_01"),
                feature_number=1,
                requirement_number=1,
                title="Montos",
                pattern=EARSPattern.ubiquitous,
                statement="El sistema debe presentar montos.",
                origin="Deriva de C01.",
            ),
            feature=_feature(),
            discovery_document=markdown_to_document(DISCOVERY_VALID),
            requirements_markdown="### REQ-1.1 Montos\n",
        )
    )
    payload = SendChatRequest(content="Agrega dos decimales al requisito REQ-1.1")

    # Act
    response = await requirement_chat("feat_01", payload, _principal(), uc, _REAL_VALIDATE_UC, builder)

    # Assert
    assert response.modification is not None
    input_data = uc.execute.await_args.args[0]
    assert input_data.phase == SpecPhase.REQUISITOS


def _feature() -> Feature:
    return Feature(
        id=FeatureId("feat_01"),
        number=1,
        title="Gestión de gastos",
        slug="gestion-gastos",
        description="El usuario administra gastos.",
        project_id=ProjectId("prj_01"),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discovery_chat_maps_missing_document_to_409() -> None:
    # Arrange
    uc = _make_mock_uc()
    builder = _make_mock_builder(
        exc=PhaseTransitionError(detail="No existe un documento de descubrimiento para el chat.")
    )
    payload = SendChatRequest(content="Cambia la visión del producto")

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await discovery_chat("prj_01", payload, _principal(), uc, _REAL_VALIDATE_UC, builder)

    assert exc_info.value.status_code == 409
    uc.execute.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_feature_chat_maps_not_found_to_404() -> None:
    # Arrange
    uc = _make_mock_uc()
    builder = _make_mock_builder(exc=FeatureNotFoundError(feature_id="feat_missing"))
    payload = SendChatRequest(content="Cambia el título de la característica")

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await feature_chat("feat_missing", payload, _principal(), uc, _REAL_VALIDATE_UC, builder)

    assert exc_info.value.status_code == 404
