from __future__ import annotations

import asyncio
import contextlib
import contextvars
import dataclasses
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import httpx

from kosmo.contracts.ai.ai_config import AIProvider, UserAiConfigRepository
from kosmo.contracts.auth.context import current_user_id
from kosmo.contracts.auth.secrets import EncryptedSecret, SecretCipher
from kosmo.contracts.sdd.codegen import OpenCodeEvent, OpenCodeEventType, OpenCodeSession
from kosmo.infrastructure.codegen.opencode_client import OpenCodeHttpClient


class UserCodegenConfigError(ValueError):
    """The current user has no usable personal OpenCode credentials."""


class IsolatedOpenCodeClient:
    """Per-task client backed by a one-project, one-user ephemeral OpenCode job."""

    def __init__(
        self,
        launcher_url: str,
        launcher_token: str,
        config_repo: UserAiConfigRepository,
        cipher: SecretCipher,
    ) -> None:
        self._launcher = httpx.AsyncClient(
            base_url=launcher_url.rstrip("/"),
            headers={"Authorization": f"Bearer {launcher_token}"},
            timeout=httpx.Timeout(30.0, connect=5.0),
        )
        self._config_repo = config_repo
        self._cipher = cipher
        self._active: contextvars.ContextVar[tuple[str, OpenCodeHttpClient, asyncio.Task[None]] | None] = (
            contextvars.ContextVar("opencode_job", default=None)
        )

    async def _credentials(self) -> tuple[AIProvider, str, str]:
        user_id = current_user_id.get()
        if not user_id:
            raise UserCodegenConfigError("No se pudo identificar al usuario que solicitó la implementación.")
        config = await self._config_repo.by_user_id(user_id)
        if config is None or config.encrypted_api_key is None:
            raise UserCodegenConfigError(
                "Configura tu proveedor, modelo y API key en Preferencias de IA antes de implementar."
            )
        if config.provider not in {AIProvider.OPENAI, AIProvider.ANTHROPIC, AIProvider.GOOGLE, AIProvider.DEEPSEEK}:
            raise UserCodegenConfigError(
                "El proveedor seleccionado no es compatible con OpenCode. Elige OpenAI, Anthropic, Google o DeepSeek."
            )
        if not config.model or "/" in config.model:
            raise UserCodegenConfigError("El modelo configurado no es válido para OpenCode.")
        encrypted = config.encrypted_api_key
        secret = encrypted if isinstance(encrypted, EncryptedSecret) else EncryptedSecret(ciphertext=encrypted)
        api_key = self._cipher.decrypt(secret).decode("utf-8").strip()
        if not api_key:
            raise UserCodegenConfigError("La API key configurada está vacía. Actualízala en Preferencias de IA.")
        return config.provider, config.model, api_key

    async def validate_user_config(self) -> None:
        """Reject missing/unsupported BYOK configuration before mutating the workspace."""
        await self._credentials()

    async def health_check(self) -> bool:
        active = self._active.get()
        if active is not None:
            return await active[1].health_check()
        try:
            response = await self._launcher.get("/health", timeout=5.0)
            return response.is_success
        except httpx.HTTPError:
            return False

    async def start_job(self, workspace_dir: str) -> None:
        if self._active.get() is not None:
            raise RuntimeError("Ya existe un trabajo OpenCode activo en esta tarea.")
        provider, model, api_key = await self._credentials()
        project_id = Path(workspace_dir).name
        max_retries = 60  # 60 × 5s = 5 minutos máximo de espera
        for _attempt in range(max_retries):
            try:
                response = await self._launcher.post(
                    "/jobs",
                    json={"project_id": project_id, "provider": provider.value, "model": model, "api_key": api_key},
                )
            except httpx.HTTPError as exc:
                raise RuntimeError("No se pudo contactar el lanzador aislado de OpenCode.") from exc
            if response.status_code != 429:
                break
            await asyncio.sleep(5)
        else:
            raise RuntimeError(
                "No se pudo iniciar el trabajo de OpenCode: el lanzador está saturado "
                f"después de {max_retries * 5 // 60} minutos de espera."
            )
        if not response.is_success:
            try:
                data: dict[str, Any] = response.json()
                message = str(data.get("error", "No se pudo iniciar OpenCode."))
            except ValueError:
                message = "No se pudo iniciar OpenCode."
            raise RuntimeError(message)
        data = response.json()
        job_id = str(data["job_id"])
        client = OpenCodeHttpClient(
            base_url=str(data["base_url"]),
            server_password=str(data["password"]),
            model=f"{provider.value}/{model}",
            read_timeout_seconds=None,
        )
        heartbeat = asyncio.create_task(self._heartbeat(job_id))
        try:
            for _ in range(60):
                if await client.health_check():
                    await client.validate_model(provider.value, model)
                    self._active.set((job_id, client, heartbeat))
                    return
                state: dict[str, Any] = {}
                try:
                    status = await self._launcher.get(f"/jobs/{job_id}")
                    if status.is_success:
                        payload = status.json()
                        if isinstance(payload, dict):
                            state = cast("dict[str, Any]", payload)
                except (httpx.HTTPError, ValueError):
                    pass
                if state.get("oom_killed"):
                    raise UserCodegenConfigError("OpenCode superó el máximo de 1 GiB de RAM al iniciar.")
                if state.get("status") == "exited":
                    raise RuntimeError("OpenCode terminó inesperadamente antes de iniciar.")
                await asyncio.sleep(2)
            raise RuntimeError("OpenCode no inició correctamente en el contenedor aislado.")
        except BaseException:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
            await client.aclose()
            with contextlib.suppress(httpx.HTTPError):
                await self._launcher.delete(f"/jobs/{job_id}")
            raise

    async def _heartbeat(self, job_id: str) -> None:
        while True:
            await asyncio.sleep(20)
            with contextlib.suppress(httpx.HTTPError):
                await self._launcher.post(f"/jobs/{job_id}/heartbeat")

    async def stop_job(self) -> None:
        active = self._active.get()
        if active is None:
            return
        self._active.set(None)
        job_id, client, heartbeat = active
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat
        await client.aclose()
        try:
            response = await self._launcher.delete(f"/jobs/{job_id}")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("No se pudo liberar el contenedor aislado de OpenCode.") from exc

    def _client(self) -> OpenCodeHttpClient:
        active = self._active.get()
        if active is None:
            raise RuntimeError("No hay un trabajo aislado de OpenCode activo.")
        return active[1]

    async def create_session(self, workspace_dir: str, *, title: str = "") -> OpenCodeSession:
        return await self._client().create_session(workspace_dir, title=title)

    async def send_prompt(self, session_id: str, prompt: str, *, agent: str = "plan") -> AsyncIterator[OpenCodeEvent]:
        async for event in self._client().send_prompt(session_id, prompt, agent=agent):
            active = self._active.get()
            if active is not None and event.event_type == OpenCodeEventType.ERROR:
                with contextlib.suppress(httpx.HTTPError, ValueError):
                    status = await self._launcher.get(f"/jobs/{active[0]}")
                    if status.is_success and status.json().get("oom_killed"):
                        event = dataclasses.replace(
                            event,
                            data={
                                "error": "OpenCode superó el máximo de 1 GiB de RAM. Reduce el contexto del proyecto."
                            },
                        )
            yield event

    async def close_session(self, session_id: str) -> None:
        await self._client().close_session(session_id)

    async def aclose(self) -> None:
        await self._launcher.aclose()
