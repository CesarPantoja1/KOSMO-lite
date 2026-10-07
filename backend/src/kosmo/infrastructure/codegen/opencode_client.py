from __future__ import annotations

import base64
import contextlib
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Self, cast

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from kosmo.contracts.sdd.codegen import (
    OpenCodeClientPort,
    OpenCodeEvent,
    OpenCodeEventType,
    OpenCodeSession,
)


class OpenCodeClientError(RuntimeError):
    """Excepción base para errores en el cliente OpenCode."""


class OpenCodeConnectionError(OpenCodeClientError):
    """Lanzada cuando ocurre un error de conexión con el servidor OpenCode."""


class OpenCodeTimeoutError(OpenCodeClientError):
    """Lanzada cuando se agota el tiempo de espera con el servidor OpenCode."""


class OpenCodeSessionNotFoundError(OpenCodeClientError):
    """Lanzada cuando una sesión no existe en el servidor OpenCode."""


class OpenCodeAuthenticationError(OpenCodeClientError):
    """Lanzada cuando la autenticación con el servidor OpenCode falla."""


class OpenCodeHttpClient(OpenCodeClientPort):
    """Adaptador de infraestructura para comunicación HTTP REST y SSE con opencode serve."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:4096",
        server_username: str = "opencode",
        server_password: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 900.0,
        connect_timeout_seconds: float = 30.0,
        read_timeout_seconds: float | None = 900.0,
        write_timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._server_username = server_username
        self._server_password = server_password
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._connect_timeout_seconds = connect_timeout_seconds
        self._read_timeout_seconds = read_timeout_seconds
        self._write_timeout_seconds = write_timeout_seconds

        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(
                    timeout=self._timeout_seconds,
                    connect=self._connect_timeout_seconds,
                    read=self._read_timeout_seconds,
                    write=self._write_timeout_seconds,
                ),
                headers=self._get_auth_headers(),
            )
            self._owns_client = True

    def _get_auth_headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        """Obtiene las cabeceras requeridas incluyendo autenticación si está configurada."""
        headers: dict[str, str] = {}
        if self._server_password:
            credentials = f"{self._server_username}:{self._server_password}"
            encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {encoded}"
        if extra_headers:
            headers.update(extra_headers)
        return headers

    async def aclose(self) -> None:
        """Cierra el cliente HTTP si fue creado internamente."""
        if self._owns_client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        await self.aclose()

    async def health_check(self) -> bool:
        """Verifica la disponibilidad del servidor OpenCode con timeout corto."""
        try:
            headers = self._get_auth_headers()
            response = await self._client.get("/health", headers=headers, timeout=5.0)
            return response.is_success
        except Exception:
            return False

    async def validate_model(self, provider: str, model: str) -> None:
        """Fail before opening a session if the pinned OpenCode catalog lacks the user's model."""
        try:
            response = await self._client.get("/provider", headers=self._get_auth_headers(), timeout=30.0)
            response.raise_for_status()
            raw_data: object = response.json()
            data: dict[str, Any] = cast(dict[str, Any], raw_data) if isinstance(raw_data, dict) else {}
            raw_providers: object = data.get("all", [])
            providers: list[object] = cast(list[object], raw_providers) if isinstance(raw_providers, list) else []
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise OpenCodeClientError("No se pudo consultar el catálogo de modelos de OpenCode.") from exc
        for entry in providers:
            if isinstance(entry, dict):
                provider_entry: dict[str, Any] = cast(dict[str, Any], entry)
                if provider_entry.get("id") != provider:
                    continue
                models: object = provider_entry.get("models")
                if isinstance(models, dict) and model in models:
                    return
        raise OpenCodeClientError(
            f"El modelo '{model}' de {provider} no está disponible en OpenCode. "
            "Selecciona otro modelo en Preferencias de IA."
        )

    async def create_session(
        self,
        workspace_dir: str,
        *,
        title: str = "",
    ) -> OpenCodeSession:
        """Crea una nueva sesión en el servidor OpenCode para el workspace especificado."""
        headers = self._get_auth_headers()
        payload: dict[str, object] = {"title": title}

        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((httpx.ConnectError, httpx.TransportError)),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=4),
            reraise=True,
        ):
            with attempt:
                try:
                    response = await self._client.post(
                        "/session",
                        params={"directory": workspace_dir},
                        json=payload,
                        headers=headers,
                    )
                    if not response.is_success:
                        raise OpenCodeClientError(
                            f"No se pudo iniciar la generación (HTTP {response.status_code}): {response.text}"
                        )
                    data: dict[str, Any] = response.json()
                    session_id = data.get("id") or data.get("session_id")
                    if not session_id:
                        raise OpenCodeClientError(f"La respuesta del asistente de generación es inválida: {data}")

                    resolved_dir = str(data.get("workspace_dir") or data.get("directory") or workspace_dir)
                    resolved_title = str(data.get("title") or title)

                    return OpenCodeSession(
                        session_id=str(session_id),
                        workspace_dir=resolved_dir,
                        title=resolved_title,
                        created_at=datetime.now(UTC),
                    )
                except OpenCodeClientError:
                    raise
                except httpx.TimeoutException as exc:
                    raise OpenCodeTimeoutError(f"Tiempo de espera agotado al crear sesión OpenCode: {exc}") from exc
                except httpx.HTTPError as exc:
                    raise OpenCodeConnectionError(f"Error HTTP al conectar con OpenCode: {exc}") from exc

        raise OpenCodeConnectionError("No se pudo crear la sesión OpenCode tras reintentos")

    def _model_payload(self) -> dict[str, str] | None:
        """Convierte el modelo configurado (provider/model) al objeto que espera la API."""
        if not self._model:
            return None
        if "/" in self._model:
            provider, _, model_id = self._model.partition("/")
            return {"providerID": provider, "modelID": model_id}
        return {"modelID": self._model}

    def _progress_event_type(self, agent: str) -> OpenCodeEventType | str:
        """Tipo de evento de progreso según el agente."""
        if agent == "plan":
            return OpenCodeEventType.PLAN_PROGRESS
        if agent == "build":
            return OpenCodeEventType.BUILD_PROGRESS
        return f"{agent}_progress"

    def _complete_event_type(self, agent: str) -> OpenCodeEventType | str:
        """Tipo de evento de completitud según el agente."""
        if agent == "plan":
            return OpenCodeEventType.PLAN_COMPLETE
        if agent == "build":
            return OpenCodeEventType.BUILD_COMPLETE
        return f"{agent}_complete"

    async def send_prompt(
        self,
        session_id: str,
        prompt: str,
        *,
        agent: str = "plan",
    ) -> AsyncIterator[OpenCodeEvent]:
        """Envía una instrucción al agente en OpenCode (POST /session/{id}/message) y
        traduce el mensaje final de respuesta al vocabulario de eventos KOSMO."""
        headers = self._get_auth_headers({"Accept": "application/json"})
        payload: dict[str, object] = {"parts": [{"type": "text", "text": prompt}], "agent": agent}
        model_payload = self._model_payload()
        if model_payload:
            payload["model"] = model_payload
        url = f"/session/{session_id}/message"

        try:
            response = await self._client.post(url, json=payload, headers=headers)
            if not response.is_success:
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.ERROR,
                    session_id=session_id,
                    data={
                        "error": f"HTTP {response.status_code}",
                        "detail": response.text[:500],
                    },
                    timestamp=datetime.now(UTC),
                )
                return

            raw_json = response.json()
            message: dict[str, Any] = cast(dict[str, Any], raw_json) if isinstance(raw_json, dict) else {}
            raw_info = message.get("info")
            info: dict[str, Any] = cast(dict[str, Any], raw_info) if isinstance(raw_info, dict) else {}
            raw_parts = message.get("parts")
            parts: list[object] = cast(list[object], raw_parts) if isinstance(raw_parts, list) else []

            error_info: object = info.get("error")
            if error_info is not None:
                error_text = error_info if isinstance(error_info, str) else str(error_info)
                yield OpenCodeEvent(
                    event_type=OpenCodeEventType.ERROR,
                    session_id=session_id,
                    data={"error": error_text},
                    timestamp=datetime.now(UTC),
                )
                return

            files: list[str] = []
            for part in parts:
                if not isinstance(part, dict):
                    continue
                part_dict: dict[str, Any] = cast(dict[str, Any], part)
                part_type: object = part_dict.get("type")
                if part_type in ("thought", "reasoning"):
                    raw_thought: object = part_dict.get("text") or part_dict.get("thought") or part_dict.get("content")
                    thought_text = str(raw_thought or "").strip()
                    if thought_text:
                        yield OpenCodeEvent(
                            event_type=self._progress_event_type(agent),
                            session_id=session_id,
                            data={"thought": thought_text, "stage": "thinking"},
                            timestamp=datetime.now(UTC),
                        )
                elif part_type == "file":
                    raw_file = part_dict.get("file")
                    file_obj: dict[str, Any] = cast(dict[str, Any], raw_file) if isinstance(raw_file, dict) else {}
                    raw_path: object = part_dict.get("path") or file_obj.get("path")
                    if raw_path is not None:
                        path_str = str(raw_path)
                        if path_str not in files:
                            files.append(path_str)
                        content_val: object = (
                            part_dict.get("content") or part_dict.get("text") or file_obj.get("content")
                        )
                        yield OpenCodeEvent(
                            event_type=OpenCodeEventType.FILE_EDIT,
                            session_id=session_id,
                            data={
                                "path": path_str,
                                "content": content_val,
                            },
                            timestamp=datetime.now(UTC),
                        )
                elif part_type in ("tool", "tool-call", "tool_call", "tool_invocation"):
                    tool_name = str(part_dict.get("tool") or part_dict.get("name") or "tool")
                    raw_desc = part_dict.get("description") or part_dict.get("args") or ""
                    yield OpenCodeEvent(
                        event_type=self._progress_event_type(agent),
                        session_id=session_id,
                        data={
                            "delta": f"Ejecutando herramienta: {tool_name}",
                            "tool": tool_name,
                            "stage": "tool",
                            "detail": str(raw_desc)[:200] if raw_desc else "",
                        },
                        timestamp=datetime.now(UTC),
                    )
                    raw_args = part_dict.get("args") or part_dict.get("parameters") or part_dict.get("input")
                    if isinstance(raw_args, str) and raw_args.strip().startswith("{"):
                        with contextlib.suppress(Exception):
                            raw_args = json.loads(raw_args)
                    args_dict: dict[str, Any] = cast(dict[str, Any], raw_args) if isinstance(raw_args, dict) else {}
                    raw_path = (
                        part_dict.get("path")
                        or args_dict.get("path")
                        or args_dict.get("filePath")
                        or args_dict.get("file")
                        or args_dict.get("target_file")
                    )
                    file_tools = (
                        "write",
                        "write_file",
                        "edit",
                        "edit_file",
                        "patch",
                        "apply_patch",
                        "create_file",
                        "save_file",
                    )
                    if raw_path and (tool_name.lower() in file_tools or "file" in tool_name.lower()):
                        path_str = str(raw_path)
                        if path_str not in files:
                            files.append(path_str)
                        content_val = args_dict.get("content") or args_dict.get("text") or args_dict.get("patch")
                        yield OpenCodeEvent(
                            event_type=OpenCodeEventType.FILE_EDIT,
                            session_id=session_id,
                            data={
                                "path": path_str,
                                "content": content_val,
                            },
                            timestamp=datetime.now(UTC),
                        )
                elif part_type == "text":
                    raw_text: object = part_dict.get("text")
                    text = str(raw_text or "").strip()
                    if text:
                        yield OpenCodeEvent(
                            event_type=self._progress_event_type(agent),
                            session_id=session_id,
                            data={"delta": text, "stage": "writing"},
                            timestamp=datetime.now(UTC),
                        )

            yield OpenCodeEvent(
                event_type=self._complete_event_type(agent),
                session_id=session_id,
                data={"files": files},
                timestamp=datetime.now(UTC),
            )

        except httpx.TimeoutException as exc:
            detail = str(exc).strip()
            msg = (
                f"Tiempo de espera agotado al comunicar con OpenCode: {detail}"
                if detail
                else (
                    f"Tiempo de espera agotado al comunicar con OpenCode "
                    f"(tiempo límite: {self._read_timeout_seconds:.0f}s)"
                    if self._read_timeout_seconds is not None
                    else "Tiempo de espera agotado al comunicar con OpenCode"
                )
            )
            yield OpenCodeEvent(
                event_type=OpenCodeEventType.ERROR,
                session_id=session_id,
                data={
                    "error": msg,
                    "timeout": True,
                },
                timestamp=datetime.now(UTC),
            )
        except httpx.HTTPError as exc:
            yield OpenCodeEvent(
                event_type=OpenCodeEventType.ERROR,
                session_id=session_id,
                data={
                    "error": f"Error de conexión HTTP con OpenCode: {exc}",
                    "connection_error": True,
                },
                timestamp=datetime.now(UTC),
            )
        except Exception as exc:
            yield OpenCodeEvent(
                event_type=OpenCodeEventType.ERROR,
                session_id=session_id,
                data={"error": str(exc)},
                timestamp=datetime.now(UTC),
            )

    async def close_session(self, session_id: str) -> None:
        """Cierra una sesión de OpenCode de forma idempotente."""
        headers = self._get_auth_headers()
        try:
            response = await self._client.delete(f"/session/{session_id}", headers=headers)
            if response.status_code == 404:
                return
            if not response.is_success:
                raise OpenCodeClientError(
                    f"No se pudo cerrar la sesión de generación (HTTP {response.status_code}): {response.text}"
                )
        except OpenCodeClientError:
            raise
        except httpx.TimeoutException as exc:
            raise OpenCodeTimeoutError(f"Tiempo de espera agotado al cerrar sesión {session_id}: {exc}") from exc
        except httpx.HTTPError as exc:
            raise OpenCodeConnectionError(f"Error HTTP al cerrar sesión {session_id}: {exc}") from exc
