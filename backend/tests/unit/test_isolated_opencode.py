from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from kosmo.contracts.ai.ai_config import AIProvider, UserAiConfig
from kosmo.contracts.auth.context import current_user_id
from kosmo.contracts.sdd.codegen import OpenCodeEvent, OpenCodeEventType
from kosmo.infrastructure.codegen import isolated_opencode
from kosmo.infrastructure.codegen.isolated_opencode import IsolatedOpenCodeClient, UserCodegenConfigError
from kosmo.infrastructure.codegen.opencode_client import OpenCodeClientError, OpenCodeHttpClient
from kosmo.infrastructure.security.fernet_vault import FernetSecretCipher


@pytest.fixture
def cipher() -> FernetSecretCipher:
    return FernetSecretCipher(FernetSecretCipher.generate_master_key())


def make_client(config: UserAiConfig | None, cipher: FernetSecretCipher) -> IsolatedOpenCodeClient:
    repo = SimpleNamespace(by_user_id=AsyncMock(return_value=config))
    return IsolatedOpenCodeClient("http://launcher:8082", "internal-token", repo, cipher)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_implementation_requires_users_own_key(cipher: FernetSecretCipher) -> None:
    client = make_client(None, cipher)
    user_token = current_user_id.set("owner-1")
    try:
        with pytest.raises(UserCodegenConfigError, match="Configura tu proveedor"):
            await client.validate_user_config()
    finally:
        current_user_id.reset(user_token)
        await client.aclose()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_model_preflight_rejects_missing_model() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"all": [{"id": "deepseek", "models": {"deepseek-flash": {}}}]})
    )
    async with httpx.AsyncClient(base_url="http://opencode", transport=transport) as http_client:
        client = OpenCodeHttpClient(client=http_client)
        await client.validate_model("deepseek", "deepseek-flash")
        with pytest.raises(OpenCodeClientError, match="no está disponible"):
            await client.validate_model("deepseek", "deepseek-v4-flash")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_implementation_rejects_unsupported_provider(cipher: FernetSecretCipher) -> None:
    config = UserAiConfig(
        user_id="owner-1",
        provider=AIProvider.CUSTOM,
        model="custom-model",
        encrypted_api_key=cipher.encrypt(b"secret"),
    )
    client = make_client(config, cipher)
    user_token = current_user_id.set("owner-1")
    try:
        with pytest.raises(UserCodegenConfigError, match="no es compatible"):
            await client.validate_user_config()
    finally:
        current_user_id.reset(user_token)
        await client.aclose()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_job_uses_exact_personal_model_and_cleans_up(
    cipher: FernetSecretCipher, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = UserAiConfig(
        user_id="owner-1",
        provider=AIProvider.DEEPSEEK,
        model="deepseek-flash",
        encrypted_api_key=cipher.encrypt(b"sk-personal"),
    )
    client = make_client(config, cipher)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST" and request.url.path == "/jobs":
            return httpx.Response(
                201,
                json={
                    "job_id": "a" * 64,
                    "base_url": "http://kosmo-oc-abc:4096",
                    "password": "ephemeral-password",
                },
            )
        return httpx.Response(200, json={"ok": True})

    await client._launcher.aclose()
    client._launcher = httpx.AsyncClient(
        base_url="http://launcher:8082",
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer internal-token"},
    )
    made_clients: list[object] = []

    class FakeOpenCode:
        def __init__(self, **kwargs: object) -> None:
            made_clients.append(kwargs)

        async def health_check(self) -> bool:
            return True

        async def validate_model(self, provider: str, model: str) -> None:
            assert (provider, model) == ("deepseek", "deepseek-flash")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(isolated_opencode, "OpenCodeHttpClient", FakeOpenCode)
    user_token = current_user_id.set("owner-1")
    try:
        await client.start_job("/workspaces/prj_123")
        await client.stop_job()
        assert calls[0].headers["Authorization"] == "Bearer internal-token"
        assert calls[0].url.path == "/jobs"
        assert calls[0].read().decode() == (
            '{"project_id":"prj_123","provider":"deepseek","model":"deepseek-flash","api_key":"sk-personal"}'
        )
        assert calls[-1].method == "DELETE"
        assert made_clients[0]["model"] == "deepseek/deepseek-flash"
        assert made_clients[0]["read_timeout_seconds"] is None
    finally:
        current_user_id.reset(user_token)
        await client.aclose()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_oom_error_explains_one_gib_limit(cipher: FernetSecretCipher) -> None:
    client = make_client(None, cipher)
    await client._launcher.aclose()
    client._launcher = httpx.AsyncClient(
        base_url="http://launcher:8082",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"status": "exited", "oom_killed": True})),
    )

    class FailedOpenCode:
        async def send_prompt(self, session_id: str, prompt: str, *, agent: str):
            yield OpenCodeEvent(
                event_type=OpenCodeEventType.ERROR,
                session_id=session_id,
                data={"error": "connection reset"},
            )

    heartbeat = asyncio.create_task(asyncio.sleep(100))
    client._active.set(("a" * 64, FailedOpenCode(), heartbeat))
    try:
        events = [event async for event in client.send_prompt("sess", "test")]
        assert len(events) == 1
        assert "1 GiB" in events[0].data["error"]
    finally:
        heartbeat.cancel()
        client._active.set(None)
        await client.aclose()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_startup_oom_is_reported_immediately(cipher: FernetSecretCipher, monkeypatch: pytest.MonkeyPatch) -> None:
    config = UserAiConfig(
        user_id="owner-1",
        provider=AIProvider.DEEPSEEK,
        model="deepseek-flash",
        encrypted_api_key=cipher.encrypt(b"sk-personal"),
    )
    client = make_client(config, cipher)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                201,
                json={"job_id": "a" * 64, "base_url": "http://job:4096", "password": "ephemeral"},
            )
        return httpx.Response(200, json={"status": "exited", "oom_killed": True})

    await client._launcher.aclose()
    client._launcher = httpx.AsyncClient(base_url="http://launcher:8082", transport=httpx.MockTransport(handler))

    class UnavailableOpenCode:
        def __init__(self, **kwargs: object) -> None:
            pass

        async def health_check(self) -> bool:
            return False

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(isolated_opencode, "OpenCodeHttpClient", UnavailableOpenCode)
    user_token = current_user_id.set("owner-1")
    try:
        with pytest.raises(UserCodegenConfigError, match="1 GiB"):
            await client.start_job("/workspaces/prj_123")
    finally:
        current_user_id.reset(user_token)
        await client.aclose()
