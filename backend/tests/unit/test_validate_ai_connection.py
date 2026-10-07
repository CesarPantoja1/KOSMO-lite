from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from kosmo.application.ai.validate_ai_connection import ValidateAIConnectionUseCase
from kosmo.contracts.ai.ai_config import (
    AIConnectionTestError,
    AIProvider,
    InvalidApiKeyError,
    TestAIConnectionInput,
    TestAIConnectionResult,
    UserAiConfig,
)
from kosmo.contracts.auth.secrets import EncryptedSecret, SecretCipher
from kosmo.infrastructure.llm.connection_tester import HttpAIConnectionTester
from tests.unit.fakes import InMemoryUserAiConfigRepository


class FakeSecretCipher(SecretCipher):
    def encrypt(self, plaintext: bytes) -> EncryptedSecret:
        return EncryptedSecret(ciphertext=b"enc:" + plaintext)

    def decrypt(self, secret: EncryptedSecret) -> bytes:
        if secret.ciphertext.startswith(b"enc:"):
            return secret.ciphertext[4:]
        return secret.ciphertext


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_ai_connection_success_with_explicit_key() -> None:
    # Arrange
    tester = MagicMock()
    tester.test_connection = AsyncMock(
        return_value=TestAIConnectionResult(
            is_connected=True,
            detected_model="gpt-4o",
            message="Conexión exitosa con OpenAI. Modelo gpt-4o verificado y listo.",
        )
    )
    use_case = ValidateAIConnectionUseCase(connection_tester=tester)
    input_data = TestAIConnectionInput(
        provider=AIProvider.OPENAI,
        model="gpt-4o",
        api_key="sk-explicit-12345",
    )

    # Act
    result = await use_case.execute(input_data)

    # Assert
    assert result.is_connected is True
    assert result.detected_model == "gpt-4o"
    assert "Conexión exitosa" in result.message
    tester.test_connection.assert_awaited_once_with(
        provider=AIProvider.OPENAI,
        model="gpt-4o",
        api_key="sk-explicit-12345",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_ai_connection_success_with_persisted_key() -> None:
    # Arrange
    tester = MagicMock()
    tester.test_connection = AsyncMock(
        return_value=TestAIConnectionResult(
            is_connected=True,
            detected_model="claude-3-5-sonnet-20241022",
            message="Conexión exitosa con Anthropic. Modelo claude-3-5-sonnet-20241022 verificado y listo.",
        )
    )
    repo = InMemoryUserAiConfigRepository()
    cipher = FakeSecretCipher()
    await repo.save(
        UserAiConfig(
            user_id="usr_persisted",
            provider=AIProvider.ANTHROPIC,
            model="claude-3-5-sonnet-20241022",
            encrypted_api_key=cipher.encrypt(b"sk-ant-persisted-secret"),
            is_custom=True,
        )
    )
    use_case = ValidateAIConnectionUseCase(
        connection_tester=tester,
        config_repo=repo,
        cipher=cipher,
    )
    input_data = TestAIConnectionInput(
        provider=AIProvider.ANTHROPIC,
        model="claude-3-5-sonnet-20241022",
        api_key=None,
        user_id="usr_persisted",
    )

    # Act
    result = await use_case.execute(input_data)

    # Assert
    assert result.is_connected is True
    assert result.detected_model == "claude-3-5-sonnet-20241022"
    tester.test_connection.assert_awaited_once_with(
        provider=AIProvider.ANTHROPIC,
        model="claude-3-5-sonnet-20241022",
        api_key="sk-ant-persisted-secret",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_ai_connection_success_for_kosmo_default_without_key() -> None:
    # Arrange
    tester = MagicMock()
    tester.test_connection = AsyncMock(
        return_value=TestAIConnectionResult(
            is_connected=True,
            detected_model="gemini-3.8-flash",
            message=("Conexión exitosa con el proveedor predeterminado de KOSMO. Modelo gemini-3.8-flash verificado."),
        )
    )
    use_case = ValidateAIConnectionUseCase(connection_tester=tester)
    input_data = TestAIConnectionInput(
        provider=AIProvider.KOSMO_DEFAULT,
        model="gemini-3.8-flash",
        api_key=None,
    )

    # Act
    result = await use_case.execute(input_data)

    # Assert
    assert result.is_connected is True
    assert result.detected_model == "gemini-3.8-flash"
    tester.test_connection.assert_awaited_once_with(
        provider=AIProvider.KOSMO_DEFAULT,
        model="gemini-3.8-flash",
        api_key=None,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_ai_connection_raises_when_no_key_and_no_persisted_config() -> None:
    # Arrange
    tester = MagicMock()
    repo = InMemoryUserAiConfigRepository()
    cipher = FakeSecretCipher()
    use_case = ValidateAIConnectionUseCase(
        connection_tester=tester,
        config_repo=repo,
        cipher=cipher,
    )
    input_data = TestAIConnectionInput(
        provider=AIProvider.OPENAI,
        model="gpt-4o",
        api_key=None,
        user_id="usr_no_config",
    )

    # Act & Assert
    with pytest.raises(InvalidApiKeyError, match="No se proporcionó una clave de API ni existe una clave guardada"):
        await use_case.execute(input_data)

    tester.test_connection.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_ai_connection_raises_when_no_key_and_no_user_id() -> None:
    # Arrange
    tester = MagicMock()
    use_case = ValidateAIConnectionUseCase(connection_tester=tester)
    input_data = TestAIConnectionInput(
        provider=AIProvider.GOOGLE,
        model="gemini-2.5-flash",
        api_key=None,
        user_id=None,
    )

    # Act & Assert
    with pytest.raises(InvalidApiKeyError, match="La clave de API es requerida"):
        await use_case.execute(input_data)

    tester.test_connection.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_ai_connection_raises_when_persisted_config_has_no_secret() -> None:
    # Arrange
    tester = MagicMock()
    repo = InMemoryUserAiConfigRepository()
    cipher = FakeSecretCipher()
    await repo.save(
        UserAiConfig(
            user_id="usr_empty_key",
            provider=AIProvider.ANTHROPIC,
            model="claude-3-5-sonnet-20241022",
            encrypted_api_key=None,
            is_custom=False,
        )
    )
    use_case = ValidateAIConnectionUseCase(
        connection_tester=tester,
        config_repo=repo,
        cipher=cipher,
    )
    input_data = TestAIConnectionInput(
        provider=AIProvider.ANTHROPIC,
        model="claude-3-5-sonnet-20241022",
        api_key=None,
        user_id="usr_empty_key",
    )

    # Act & Assert
    with pytest.raises(InvalidApiKeyError, match="No se proporcionó una clave de API ni existe una clave guardada"):
        await use_case.execute(input_data)

    tester.test_connection.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_ai_connection_propagates_tester_error() -> None:
    # Arrange
    tester = MagicMock()
    tester.test_connection = AsyncMock(
        side_effect=AIConnectionTestError("Clave de API inválida para OpenAI. Verifica tus credenciales.")
    )
    use_case = ValidateAIConnectionUseCase(connection_tester=tester)
    input_data = TestAIConnectionInput(
        provider=AIProvider.OPENAI,
        model="gpt-4o",
        api_key="sk-invalid-key",
    )

    # Act & Assert
    with pytest.raises(AIConnectionTestError, match="Clave de API inválida"):
        await use_case.execute(input_data)


# ── Tests de HttpAIConnectionTester (Adaptador de Infraestructura) ──


@pytest.mark.unit
@pytest.mark.asyncio
async def test_http_tester_kosmo_default_and_custom() -> None:
    # Arrange
    tester = HttpAIConnectionTester()

    # Act - KOSMO_DEFAULT
    result_default = await tester.test_connection(
        provider=AIProvider.KOSMO_DEFAULT,
        model="gemini-3.8-flash",
    )

    # Assert - KOSMO_DEFAULT
    assert result_default.is_connected is True
    assert result_default.detected_model == "gemini-3.8-flash"
    assert "predeterminado" in result_default.message

    # Act - CUSTOM
    result_custom = await tester.test_connection(
        provider=AIProvider.CUSTOM,
        model="custom-finetuned-v1",
        api_key="sk-custom-secret",
    )

    # Assert - CUSTOM
    assert result_custom.is_connected is True
    assert result_custom.detected_model == "custom-finetuned-v1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_http_tester_openai_success_and_error() -> None:
    # Arrange - MockTransport para 200 OK
    def handler_200(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-openai-valid"
        return httpx.Response(200, json={"data": [{"id": "gpt-4o"}]})

    client_ok = httpx.AsyncClient(transport=httpx.MockTransport(handler_200))
    tester_ok = HttpAIConnectionTester(client=client_ok)

    # Act - Success
    result = await tester_ok.test_connection(
        provider=AIProvider.OPENAI,
        model="gpt-4o",
        api_key="sk-openai-valid",
    )

    # Assert - Success
    assert result.is_connected is True
    assert result.detected_model == "gpt-4o"
    assert "OpenAI" in result.message

    # Arrange - MockTransport para 401 Unauthorized
    def handler_401(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    client_401 = httpx.AsyncClient(transport=httpx.MockTransport(handler_401))
    tester_401 = HttpAIConnectionTester(client=client_401)

    # Act & Assert - 401
    with pytest.raises(AIConnectionTestError, match="inválida o no autorizada"):
        await tester_401.test_connection(
            provider=AIProvider.OPENAI,
            model="gpt-4o",
            api_key="sk-openai-invalid",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_http_tester_anthropic_success_and_error() -> None:
    # Arrange - MockTransport para 200 OK
    def handler_200(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "sk-ant-valid"
        return httpx.Response(200, json={"data": [{"id": "claude-3-5-sonnet-20241022"}]})

    client_ok = httpx.AsyncClient(transport=httpx.MockTransport(handler_200))
    tester_ok = HttpAIConnectionTester(client=client_ok)

    # Act - Success
    result = await tester_ok.test_connection(
        provider=AIProvider.ANTHROPIC,
        model="claude-3-5-sonnet-20241022",
        api_key="sk-ant-valid",
    )

    # Assert - Success
    assert result.is_connected is True
    assert result.detected_model == "claude-3-5-sonnet-20241022"

    # Arrange - MockTransport para 403 Forbidden
    def handler_403(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "Forbidden"}})

    client_403 = httpx.AsyncClient(transport=httpx.MockTransport(handler_403))
    tester_403 = HttpAIConnectionTester(client=client_403)

    # Act & Assert - 403
    with pytest.raises(AIConnectionTestError):
        await tester_403.test_connection(
            provider=AIProvider.ANTHROPIC,
            model="claude-3-5-sonnet-20241022",
            api_key="sk-ant-invalid",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_http_tester_google_gemini_and_deepseek() -> None:
    # Arrange - Google 200 OK
    def handler_google(request: httpx.Request) -> httpx.Response:
        assert "key=AIzaSyValid" in str(request.url)
        return httpx.Response(200, json={"name": "models/gemini-3.8-flash"})

    client_google = httpx.AsyncClient(transport=httpx.MockTransport(handler_google))
    tester_google = HttpAIConnectionTester(client=client_google)

    # Act - Google
    res_google = await tester_google.test_connection(
        provider=AIProvider.GOOGLE,
        model="gemini-3.8-flash",
        api_key="AIzaSyValid",
    )

    # Assert - Google
    assert res_google.is_connected is True
    assert res_google.detected_model == "gemini-3.8-flash"

    # Arrange - DeepSeek 200 OK
    def handler_deepseek(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-ds-valid"
        return httpx.Response(200, json={"object": "list", "data": []})

    client_deepseek = httpx.AsyncClient(transport=httpx.MockTransport(handler_deepseek))
    tester_deepseek = HttpAIConnectionTester(client=client_deepseek)

    # Act - DeepSeek
    res_deepseek = await tester_deepseek.test_connection(
        provider=AIProvider.DEEPSEEK,
        model="deepseek-chat",
        api_key="sk-ds-valid",
    )

    # Assert - DeepSeek
    assert res_deepseek.is_connected is True
    assert res_deepseek.detected_model == "deepseek-chat"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_http_tester_timeout_and_network_error() -> None:
    # Arrange - Timeout
    def handler_timeout(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout")

    client_timeout = httpx.AsyncClient(transport=httpx.MockTransport(handler_timeout))
    tester_timeout = HttpAIConnectionTester(client=client_timeout)

    # Act & Assert - Timeout
    with pytest.raises(AIConnectionTestError, match="Tiempo de espera agotado"):
        await tester_timeout.test_connection(
            provider=AIProvider.OPENAI,
            model="gpt-4o",
            api_key="sk-test",
        )

    # Arrange - Generic RequestError
    def handler_req_error(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    client_req_error = httpx.AsyncClient(transport=httpx.MockTransport(handler_req_error))
    tester_req_error = HttpAIConnectionTester(client=client_req_error)

    # Act & Assert - RequestError
    with pytest.raises(AIConnectionTestError, match="Error de red"):
        await tester_req_error.test_connection(
            provider=AIProvider.OPENAI,
            model="gpt-4o",
            api_key="sk-test",
        )

    # Arrange - 404 Not Found
    def handler_404(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "Model not found"}})

    client_404 = httpx.AsyncClient(transport=httpx.MockTransport(handler_404))
    tester_404 = HttpAIConnectionTester(client=client_404)

    # Act & Assert - 404
    with pytest.raises(AIConnectionTestError, match="no fue encontrado"):
        await tester_404.test_connection(
            provider=AIProvider.OPENAI,
            model="gpt-nonexistent",
            api_key="sk-test",
        )

    # Arrange - 500 Internal Server Error
    def handler_500(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client_500 = httpx.AsyncClient(transport=httpx.MockTransport(handler_500))
    tester_500 = HttpAIConnectionTester(client=client_500)

    # Act & Assert - 500
    with pytest.raises(AIConnectionTestError, match="Fallo al comprobar la conexión"):
        await tester_500.test_connection(
            provider=AIProvider.OPENAI,
            model="gpt-4o",
            api_key="sk-test",
        )

    # Act & Assert - Missing API key in tester
    tester_missing_key = HttpAIConnectionTester()
    with pytest.raises(InvalidApiKeyError, match="Se requiere una clave de API"):
        await tester_missing_key.test_connection(
            provider=AIProvider.OPENAI,
            model="gpt-4o",
            api_key="",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_ai_connection_with_raw_bytes_and_str_persisted_secrets() -> None:
    # Arrange
    tester = MagicMock()
    tester.test_connection = AsyncMock(
        return_value=TestAIConnectionResult(
            is_connected=True,
            detected_model="gpt-4o",
            message="OK",
        )
    )
    repo = InMemoryUserAiConfigRepository()
    cipher = FakeSecretCipher()

    # Raw bytes secret in repo
    await repo.save(
        UserAiConfig(
            user_id="usr_bytes",
            provider=AIProvider.OPENAI,
            model="gpt-4o",
            encrypted_api_key=b"enc:sk-bytes-key",
            is_custom=True,
        )
    )

    use_case = ValidateAIConnectionUseCase(
        connection_tester=tester,
        config_repo=repo,
        cipher=cipher,
    )

    # Act - Bytes
    res_bytes = await use_case.execute(
        TestAIConnectionInput(
            provider=AIProvider.OPENAI,
            model="gpt-4o",
            user_id="usr_bytes",
        )
    )

    # Assert - Bytes
    assert res_bytes.is_connected is True
    tester.test_connection.assert_awaited_with(
        provider=AIProvider.OPENAI,
        model="gpt-4o",
        api_key="sk-bytes-key",
    )
