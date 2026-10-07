from __future__ import annotations

import json

import httpx
import pytest

from kosmo.contracts.sdd.codegen import (
    OpenCodeClientPort,
    OpenCodeEvent,
    OpenCodeEventType,
    OpenCodeSession,
)
from kosmo.infrastructure.codegen.opencode_client import (
    OpenCodeClientError,
    OpenCodeHttpClient,
)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_opencode_http_client_implements_protocol() -> None:
    # Arrange
    client: OpenCodeClientPort = OpenCodeHttpClient(base_url="http://127.0.0.1:4096")

    # Act & Assert
    assert hasattr(client, "health_check")
    assert hasattr(client, "create_session")
    assert hasattr(client, "send_prompt")
    assert hasattr(client, "close_session")
    assert callable(client.health_check)
    assert callable(client.create_session)
    assert callable(client.send_prompt)
    assert callable(client.close_session)
    if hasattr(client, "aclose"):
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_health_check_returns_true_when_healthy() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        assert request.method == "GET"
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    is_healthy = await client.health_check()

    # Assert
    assert is_healthy is True
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_health_check_returns_false_on_server_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal_error"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    is_healthy = await client.health_check()

    # Assert
    assert is_healthy is False
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_health_check_returns_false_on_connection_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    is_healthy = await client.health_check()

    # Assert
    assert is_healthy is False
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_session_success() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/session"
        assert request.method == "POST"
        assert request.url.params["directory"] == "/workspaces/prj_01"
        body = json.loads(request.content.decode("utf-8"))
        assert "workspace_dir" not in body
        assert body["title"] == "Feature 1 implementation"
        return httpx.Response(
            201,
            json={
                "id": "oc_sess_12345",
                "workspace_dir": "/workspaces/prj_01",
                "title": "Feature 1 implementation",
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    session = await client.create_session("/workspaces/prj_01", title="Feature 1 implementation")

    # Assert
    assert isinstance(session, OpenCodeSession)
    assert session.session_id == "oc_sess_12345"
    assert session.workspace_dir == "/workspaces/prj_01"
    assert session.title == "Feature 1 implementation"
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_session_sends_directory_query_param() -> None:
    # Arrange
    captured_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "id": "oc_sess_dir_1",
                "workspace_dir": "/workspaces/prj_99",
                "title": "Dir session",
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    await client.create_session("/workspaces/prj_99", title="Dir session")

    # Assert
    assert len(captured_urls) == 1
    query = dict(httpx.QueryParams(httpx.URL(captured_urls[0]).query))
    assert query.get("directory") == "/workspaces/prj_99"
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_session_supports_session_id_field() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "session_id": "oc_sess_alt_999",
                "workspace_dir": "/workspaces/prj_alt",
                "title": "Alt session",
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    session = await client.create_session("/workspaces/prj_alt", title="Alt session")

    # Assert
    assert session.session_id == "oc_sess_alt_999"
    assert session.workspace_dir == "/workspaces/prj_alt"
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_session_raises_on_http_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "Invalid workspace path"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act & Assert
    with pytest.raises(OpenCodeClientError) as exc_info:
        await client.create_session("/invalid/path")

    assert "400" in str(exc_info.value) or "Invalid workspace" in str(exc_info.value)
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_session_raises_on_missing_id_in_response() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"workspace_dir": "/workspaces/prj_01"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act & Assert
    with pytest.raises(OpenCodeClientError) as exc_info:
        await client.create_session("/workspaces/prj_01")

    assert "id" in str(exc_info.value).lower()
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_session_omite_model_del_payload() -> None:
    # Arrange — el endpoint de create rechaza el campo model (400); el modelo
    # se envía por mensaje en send_prompt.
    captured_bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_bodies.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "id": "oc_sess_model_1",
                "workspace_dir": "/workspaces/prj_01",
                "title": "Model session",
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client, model="deepseek/deepseek-v4-flash")

    # Act
    await client.create_session("/workspaces/prj_01", title="Model session")

    # Assert
    assert len(captured_bodies) == 1
    assert "model" not in captured_bodies[0]
    assert captured_bodies[0]["title"] == "Model session"
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_prompt_includes_model_object_when_configured() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == {"providerID": "deepseek", "modelID": "deepseek-v4-flash"}
        return httpx.Response(
            200,
            json={
                "info": {"id": "msg_1", "sessionID": "oc_sess_100", "role": "assistant", "finish": "stop"},
                "parts": [],
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client, model="deepseek/deepseek-v4-flash")

    # Act
    events: list[OpenCodeEvent] = []
    async for event in client.send_prompt("oc_sess_100", "Implementa", agent="build"):
        events.append(event)

    # Assert
    assert len(events) == 1
    assert events[0].event_type == OpenCodeEventType.BUILD_COMPLETE
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_prompt_posts_message_with_parts_and_agent() -> None:
    # Arrange
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/session/oc_sess_100/message"
        assert request.method == "POST"
        body = json.loads(request.content.decode("utf-8"))
        assert body["agent"] == "build"
        assert body["parts"] == [{"type": "text", "text": "Implementa la feature"}]
        return httpx.Response(
            200,
            json={
                "info": {
                    "id": "msg_1",
                    "sessionID": "oc_sess_100",
                    "role": "assistant",
                    "finish": "stop",
                },
                "parts": [],
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    events: list[OpenCodeEvent] = []
    async for event in client.send_prompt("oc_sess_100", "Implementa la feature", agent="build"):
        events.append(event)

    # Assert
    assert len(events) == 1
    assert events[0].event_type == OpenCodeEventType.BUILD_COMPLETE
    assert events[0].session_id == "oc_sess_100"
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_prompt_yields_file_edits_from_message_parts() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "info": {"id": "msg_1", "sessionID": "oc_sess_100", "role": "assistant", "finish": "stop"},
                "parts": [
                    {"id": "prt_1", "type": "step-start", "snapshot": "abc"},
                    {
                        "id": "prt_2",
                        "type": "file",
                        "path": "src/calc.ts",
                        "content": "export const ok = true;",
                    },
                    {"id": "prt_3", "type": "text", "text": "Archivo creado."},
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    events: list[OpenCodeEvent] = []
    async for event in client.send_prompt("oc_sess_100", "Implementa la feature", agent="build"):
        events.append(event)

    # Assert
    assert len(events) == 3
    assert events[0].event_type == OpenCodeEventType.FILE_EDIT
    assert events[0].data.get("path") == "src/calc.ts"
    assert events[0].data.get("content") == "export const ok = true;"
    assert events[1].event_type == OpenCodeEventType.BUILD_PROGRESS
    assert events[1].data.get("delta") == "Archivo creado."
    assert events[2].event_type == OpenCodeEventType.BUILD_COMPLETE
    assert events[2].data.get("files") == ["src/calc.ts"]
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_prompt_yields_plan_progress_and_complete_for_plan_agent() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "info": {"id": "msg_1", "sessionID": "oc_sess_100", "role": "assistant", "finish": "stop"},
                "parts": [
                    {"id": "prt_1", "type": "text", "text": "Analizando requisitos..."},
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    events: list[OpenCodeEvent] = []
    async for event in client.send_prompt("oc_sess_100", "Planifica", agent="plan"):
        events.append(event)

    # Assert
    assert len(events) == 2
    assert events[0].event_type == OpenCodeEventType.PLAN_PROGRESS
    assert events[0].data.get("delta") == "Analizando requisitos..."
    assert events[1].event_type == OpenCodeEventType.PLAN_COMPLETE
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_prompt_emits_error_event_when_message_has_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "info": {
                    "id": "msg_1",
                    "sessionID": "oc_sess_100",
                    "role": "assistant",
                    "error": {"name": "APICallError", "message": "Rate limit excedido"},
                },
                "parts": [],
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    events: list[OpenCodeEvent] = []
    async for event in client.send_prompt("oc_sess_100", "Prompt", agent="build"):
        events.append(event)

    # Assert
    assert len(events) == 1
    assert events[0].event_type == OpenCodeEventType.ERROR
    assert "Rate limit" in str(events[0].data.get("error", ""))
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_prompt_emits_error_event_on_http_failure() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Session oc_sess_missing not found"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    events: list[OpenCodeEvent] = []
    async for event in client.send_prompt("oc_sess_missing", "Hola"):
        events.append(event)

    # Assert
    assert len(events) == 1
    assert events[0].event_type == OpenCodeEventType.ERROR
    assert events[0].session_id == "oc_sess_missing"
    assert "404" in str(events[0].data) or "not found" in str(events[0].data).lower()
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_prompt_emits_error_event_on_connection_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection timed out")

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    events: list[OpenCodeEvent] = []
    async for event in client.send_prompt("oc_sess_timeout", "Prompt"):
        events.append(event)

    # Assert
    assert len(events) == 1
    assert events[0].event_type == OpenCodeEventType.ERROR
    assert events[0].session_id == "oc_sess_timeout"
    assert "Connection" in str(events[0].data) or "timed out" in str(events[0].data)
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_close_session_success() -> None:
    # Arrange
    deleted_sessions: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/session/oc_sess_to_close"
        deleted_sessions.append("oc_sess_to_close")
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    await client.close_session("oc_sess_to_close")

    # Assert
    assert deleted_sessions == ["oc_sess_to_close"]
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_close_session_idempotent_on_404() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Session already closed"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act (debe completar sin lanzar excepción)
    await client.close_session("oc_sess_non_existent")

    # Assert
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_close_session_raises_on_server_error() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "Internal server crash"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act & Assert
    with pytest.raises(OpenCodeClientError) as exc_info:
        await client.close_session("oc_sess_err")

    assert "500" in str(exc_info.value) or "crash" in str(exc_info.value)
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_authentication_header_sent_when_password_configured() -> None:
    # Arrange
    captured_auth_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_auth_headers.append(request.headers.get("authorization", ""))
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(
        client=http_client,
        server_password="secret_opencode_password_123",
    )

    # Act
    await client.health_check()

    # Assert
    assert len(captured_auth_headers) == 1
    assert captured_auth_headers[0] == "Basic b3BlbmNvZGU6c2VjcmV0X29wZW5jb2RlX3Bhc3N3b3JkXzEyMw=="
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_authentication_header_uses_configured_username() -> None:
    # Arrange
    captured_auth_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_auth_headers.append(request.headers.get("authorization", ""))
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(
        client=http_client,
        server_username="kosmo-agent",
        server_password="tok",
    )

    # Act
    await client.health_check()

    # Assert
    assert len(captured_auth_headers) == 1
    assert captured_auth_headers[0] == "Basic a29zbW8tYWdlbnQ6dG9r"
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_no_authentication_header_when_no_password() -> None:
    # Arrange
    captured_auth_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_auth_headers.append(request.headers.get("authorization", ""))
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    await client.health_check()

    # Assert
    assert captured_auth_headers == [""]
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_async_context_manager_lifecycle() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

    # Act & Assert
    async with OpenCodeHttpClient(client=http_client) as client:
        is_healthy = await client.health_check()
        assert is_healthy is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_prompt_yields_thought_and_tool_events() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "info": {"id": "msg_thought_1", "sessionID": "oc_sess_200", "role": "assistant", "finish": "stop"},
                "parts": [
                    {"id": "prt_th", "type": "thought", "text": "Analizando la arquitectura de componentes"},
                    {"id": "prt_tool", "type": "tool", "tool": "file_search", "description": "searching files"},
                    {"id": "prt_txt", "type": "text", "text": "Código generado correctamente"},
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    events: list[OpenCodeEvent] = []
    async for event in client.send_prompt("oc_sess_200", "Genera", agent="build"):
        events.append(event)

    # Assert
    assert len(events) == 4
    assert events[0].event_type == OpenCodeEventType.BUILD_PROGRESS
    assert events[0].data.get("thought") == "Analizando la arquitectura de componentes"
    assert events[0].data.get("stage") == "thinking"

    assert events[1].event_type == OpenCodeEventType.BUILD_PROGRESS
    assert events[1].data.get("tool") == "file_search"
    assert events[1].data.get("stage") == "tool"

    assert events[2].event_type == OpenCodeEventType.BUILD_PROGRESS
    assert events[2].data.get("delta") == "Código generado correctamente"
    assert events[2].data.get("stage") == "writing"

    assert events[3].event_type == OpenCodeEventType.BUILD_COMPLETE
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_opencode_http_client_initializes_with_granular_timeouts() -> None:
    # Arrange & Act
    client = OpenCodeHttpClient(
        base_url="http://127.0.0.1:4096",
        timeout_seconds=500.0,
        connect_timeout_seconds=8.0,
        read_timeout_seconds=200.0,
        write_timeout_seconds=25.0,
    )

    # Assert
    assert client._timeout_seconds == 500.0
    assert client._connect_timeout_seconds == 8.0
    assert client._read_timeout_seconds == 200.0
    assert client._write_timeout_seconds == 25.0
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_prompt_handles_read_timeout_specifically() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read operation timed out after 300s")

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    events: list[OpenCodeEvent] = []
    async for event in client.send_prompt("oc_sess_timeout", "Prompt"):
        events.append(event)

    # Assert
    assert len(events) == 1
    assert events[0].event_type == OpenCodeEventType.ERROR
    assert events[0].data.get("timeout") is True
    assert "Tiempo de espera agotado" in str(events[0].data.get("error"))
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_prompt_handles_http_connection_error_specifically() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused by host")

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    events: list[OpenCodeEvent] = []
    async for event in client.send_prompt("oc_sess_conn_err", "Prompt"):
        events.append(event)

    # Assert
    assert len(events) == 1
    assert events[0].event_type == OpenCodeEventType.ERROR
    assert events[0].data.get("connection_error") is True
    assert "Error de conexión HTTP" in str(events[0].data.get("error"))
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_prompt_formats_timeout_when_exception_message_is_empty() -> None:
    # Arrange: httpx.ReadTimeout() default has empty str(exc) == ""
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("")

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client, read_timeout_seconds=300.0)

    # Act
    events: list[OpenCodeEvent] = []
    async for event in client.send_prompt("oc_sess_timeout", "Prompt"):
        events.append(event)

    # Assert
    assert len(events) == 1
    assert events[0].event_type == OpenCodeEventType.ERROR
    assert events[0].data.get("timeout") is True
    error_msg = str(events[0].data.get("error"))
    assert "tiempo límite: 300s" in error_msg
    assert not error_msg.endswith(":")
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_send_prompt_yields_file_edits_from_tool_calls() -> None:
    # Arrange
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "info": {"id": "msg_1", "sessionID": "oc_sess_tools", "role": "assistant", "finish": "stop"},
                "parts": [
                    {
                        "id": "prt_tool_1",
                        "type": "tool",
                        "tool": "write_file",
                        "args": {"path": "src/features/search/search.ts", "content": "export const search = () => {};"},
                    },
                    {
                        "id": "prt_tool_2",
                        "type": "tool_call",
                        "name": "edit_file",
                        "parameters": {"path": "src/lib/feature-registry.ts", "content": "// updated"},
                    },
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    client = OpenCodeHttpClient(client=http_client)

    # Act
    events: list[OpenCodeEvent] = []
    async for event in client.send_prompt("oc_sess_tools", "Implementa", agent="build"):
        events.append(event)

    # Assert
    # 2 tool progress events + 2 file edit events + 1 build complete
    file_edit_events = [e for e in events if e.event_type == OpenCodeEventType.FILE_EDIT]
    assert len(file_edit_events) == 2
    assert file_edit_events[0].data.get("path") == "src/features/search/search.ts"
    assert file_edit_events[1].data.get("path") == "src/lib/feature-registry.ts"

    complete_events = [e for e in events if e.event_type == OpenCodeEventType.BUILD_COMPLETE]
    assert len(complete_events) == 1
    assert complete_events[0].data.get("files") == [
        "src/features/search/search.ts",
        "src/lib/feature-registry.ts",
    ]
    await client.aclose()
