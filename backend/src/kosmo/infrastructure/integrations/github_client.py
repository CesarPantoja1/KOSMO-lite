from __future__ import annotations

import logging
from typing import Self, cast

import httpx

from kosmo.contracts.integrations.github import (
    GitHubApiError,
    GitHubAuthenticationError,
    GitHubClientPort,
    GitHubOAuthToken,
    GitHubPermissionError,
    GitHubRateLimitError,
    GitHubRepository,
    GitHubRepositoryAlreadyExistsError,
    GitHubResourceNotFoundError,
    GitHubUser,
)

logger = logging.getLogger(__name__)

_DEFAULT_API_VERSION = "2022-11-28"
_DEFAULT_USER_AGENT = "KOSMO-App"


class GitHubHttpClient(GitHubClientPort):
    """Adaptador de infraestructura para interactuar con la API REST de GitHub vía HTTP."""

    def __init__(
        self,
        base_url: str = "https://api.github.com",
        oauth_url: str = "https://github.com/login/oauth/access_token",
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._oauth_url = oauth_url
        self._timeout_seconds = timeout_seconds

        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout_seconds, connect=10.0),
            )
            self._owns_client = True

    def _headers_for_token(self, token: str | None = None) -> dict[str, str]:
        """Construye las cabeceras estándar requeridas por la API REST de GitHub."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _DEFAULT_API_VERSION,
            "User-Agent": _DEFAULT_USER_AGENT,
        }
        if token and token.strip():
            headers["Authorization"] = f"Bearer {token.strip()}"
        return headers

    def _handle_response_error(self, response: httpx.Response, action_description: str) -> None:
        """Mapea códigos de error HTTP de GitHub a excepciones de dominio tipadas."""
        status = response.status_code

        if status == 401:
            raise GitHubAuthenticationError(
                "Token de acceso de GitHub inválido o expirado. Reconecta tu cuenta en KOSMO."
            )

        if status == 403:
            is_rate_limit = (
                response.headers.get("x-ratelimit-remaining") == "0"
                or "rate limit" in response.text.lower()
                or "secondary rate limit" in response.text.lower()
            )
            if is_rate_limit:
                raise GitHubRateLimitError(
                    "Límite de solicitudes de la API de GitHub excedido. Intenta nuevamente más tarde."
                )
            raise GitHubPermissionError(
                f"Permisos insuficientes en GitHub para {action_description}: {response.text[:200]}"
            )

        if status == 404:
            raise GitHubResourceNotFoundError(
                f"El recurso solicitado en GitHub no fue encontrado ({action_description}): {response.text[:200]}"
            )

        detail = response.text[:300] if response.text else f"código HTTP {status}"
        raise GitHubApiError(f"Error en la API de GitHub al {action_description} ({status}): {detail}")

    async def aclose(self) -> None:
        """Cierra el cliente HTTP subyacente si fue creado internamente."""
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

    async def get_authenticated_user(self, token: str) -> GitHubUser:
        """Obtiene la información del usuario asociado al token provisto."""
        headers = self._headers_for_token(token)
        try:
            response = await self._client.get("/user", headers=headers)
            if not response.is_success:
                self._handle_response_error(response, "obtener usuario autenticado")

            data = cast(dict[str, object], response.json())
            user_login = str(data.get("login") or "")
            raw_id = data.get("id")
            user_id = int(str(raw_id)) if raw_id is not None else 0
            user_name = str(data["name"]) if data.get("name") is not None else None
            user_email = str(data["email"]) if data.get("email") is not None else None
            user_avatar = str(data["avatar_url"]) if data.get("avatar_url") is not None else None
            user_html = str(data["html_url"]) if data.get("html_url") is not None else None

            return GitHubUser(
                login=user_login,
                id=user_id,
                name=user_name,
                email=user_email,
                avatar_url=user_avatar,
                html_url=user_html,
            )
        except (GitHubApiError, GitHubAuthenticationError, GitHubPermissionError, GitHubRateLimitError):
            raise
        except httpx.TimeoutException as exc:
            raise GitHubApiError(f"Tiempo de espera agotado al conectar con GitHub: {exc}") from exc
        except httpx.RequestError as exc:
            raise GitHubApiError(f"Error de red al conectar con GitHub: {exc}") from exc

    async def check_repository_exists(self, token: str, owner: str, repo_name: str) -> bool:
        """Verifica si un repositorio ya existe para el propietario indicado."""
        headers = self._headers_for_token(token)
        url = f"/repos/{owner}/{repo_name}"
        try:
            response = await self._client.get(url, headers=headers)
            if response.status_code == 200:
                return True
            if response.status_code == 404:
                return False
            self._handle_response_error(response, f"verificar existencia de repositorio {owner}/{repo_name}")
            return False
        except (GitHubApiError, GitHubAuthenticationError, GitHubPermissionError, GitHubRateLimitError):
            raise
        except httpx.TimeoutException as exc:
            raise GitHubApiError(f"Tiempo de espera agotado al conectar con GitHub: {exc}") from exc
        except httpx.RequestError as exc:
            raise GitHubApiError(f"Error de red al conectar con GitHub: {exc}") from exc

    async def get_repository(self, token: str, owner: str, repo_name: str) -> GitHubRepository | None:
        """Obtiene los detalles de un repositorio o None si no existe."""
        headers = self._headers_for_token(token)
        url = f"/repos/{owner}/{repo_name}"
        try:
            response = await self._client.get(url, headers=headers)
            if response.status_code == 404:
                return None
            if not response.is_success:
                self._handle_response_error(response, f"obtener repositorio {owner}/{repo_name}")

            data = cast(dict[str, object], response.json())
            raw_owner = data.get("owner")
            owner_login = owner
            if isinstance(raw_owner, dict):
                owner_dict = cast(dict[str, object], raw_owner)
                owner_login_val = owner_dict.get("login")
                if owner_login_val is not None:
                    owner_login = str(owner_login_val)

            raw_id = data.get("id")
            repo_id = int(str(raw_id)) if raw_id is not None else 0
            repo_title = str(data.get("name") or repo_name)
            full_name = str(data.get("full_name") or f"{owner_login}/{repo_name}")
            html_url = str(data.get("html_url") or f"https://github.com/{owner_login}/{repo_name}")
            clone_url = str(data.get("clone_url") or f"https://github.com/{owner_login}/{repo_name}.git")
            is_private = bool(data.get("private", True))
            default_branch = str(data.get("default_branch") or "main")
            description = str(data["description"]) if data.get("description") is not None else None

            return GitHubRepository(
                id=repo_id,
                name=repo_title,
                full_name=full_name,
                owner=owner_login,
                html_url=html_url,
                clone_url=clone_url,
                is_private=is_private,
                default_branch=default_branch,
                description=description,
            )
        except (GitHubApiError, GitHubAuthenticationError, GitHubPermissionError, GitHubRateLimitError):
            raise
        except httpx.TimeoutException as exc:
            raise GitHubApiError(f"Tiempo de espera agotado al conectar con GitHub: {exc}") from exc
        except httpx.RequestError as exc:
            raise GitHubApiError(f"Error de red al conectar con GitHub: {exc}") from exc

    async def create_repository(
        self,
        token: str,
        name: str,
        description: str = "",
        is_private: bool = False,
        auto_init: bool = False,
    ) -> GitHubRepository:
        """Crea un nuevo repositorio en la cuenta del usuario autenticado."""
        headers = self._headers_for_token(token)
        payload = {
            "name": name,
            "description": description,
            "private": is_private,
            "auto_init": auto_init,
        }

        try:
            response = await self._client.post("/user/repos", json=payload, headers=headers)

            if response.status_code == 422:
                err_text = response.text.lower()
                if "already exists" in err_text or "name already exists" in err_text:
                    raise GitHubRepositoryAlreadyExistsError(
                        f"El repositorio '{name}' ya existe en la cuenta de GitHub."
                    )

            if not response.is_success:
                self._handle_response_error(response, f"crear repositorio {name}")

            data = cast(dict[str, object], response.json())
            raw_owner = data.get("owner")
            owner_login = ""
            if isinstance(raw_owner, dict):
                owner_dict = cast(dict[str, object], raw_owner)
                owner_login_val = owner_dict.get("login")
                if owner_login_val is not None:
                    owner_login = str(owner_login_val)

            raw_id = data.get("id")
            repo_id = int(str(raw_id)) if raw_id is not None else 0
            repo_title = str(data.get("name") or name)
            full_name = str(data.get("full_name") or f"{owner_login}/{name}")
            html_url = str(data.get("html_url") or f"https://github.com/{owner_login}/{name}")
            clone_url = str(data.get("clone_url") or f"https://github.com/{owner_login}/{name}.git")
            is_priv = bool(data.get("private", is_private))
            default_branch = str(data.get("default_branch") or "main")
            desc = str(data["description"]) if data.get("description") is not None else description

            return GitHubRepository(
                id=repo_id,
                name=repo_title,
                full_name=full_name,
                owner=owner_login,
                html_url=html_url,
                clone_url=clone_url,
                is_private=is_priv,
                default_branch=default_branch,
                description=desc,
            )
        except (
            GitHubApiError,
            GitHubAuthenticationError,
            GitHubPermissionError,
            GitHubRateLimitError,
            GitHubRepositoryAlreadyExistsError,
        ):
            raise
        except httpx.TimeoutException as exc:
            raise GitHubApiError(f"Tiempo de espera agotado al conectar con GitHub: {exc}") from exc
        except httpx.RequestError as exc:
            raise GitHubApiError(f"Error de red al conectar con GitHub: {exc}") from exc

    async def exchange_oauth_code(
        self,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str | None = None,
        code_verifier: str | None = None,
    ) -> GitHubOAuthToken:
        """Intercambia un código de autorización OAuth por un token de acceso."""
        headers = {
            "Accept": "application/json",
            "User-Agent": _DEFAULT_USER_AGENT,
        }
        payload: dict[str, str] = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        }
        if redirect_uri:
            payload["redirect_uri"] = redirect_uri
        if code_verifier:
            payload["code_verifier"] = code_verifier

        try:
            response = await self._client.post(self._oauth_url, json=payload, headers=headers)
            if response.status_code == 404:
                raise GitHubAuthenticationError(
                    "GitHub rechazó el intercambio OAuth (404 Not Found). "
                    "Verifica que GITHUB_CLIENT_ID y GITHUB_CLIENT_SECRET pertenezcan a una OAuth App válida en GitHub."
                )
            if not response.is_success:
                self._handle_response_error(response, "intercambiar código OAuth")

            data = cast(dict[str, object], response.json())

            if "error" in data:
                error_code = str(data.get("error") or "error_oauth")
                error_desc = str(data.get("error_description") or error_code)
                raise GitHubAuthenticationError(f"Fallo en autorización OAuth de GitHub: {error_desc} ({error_code})")

            access_token = str(data.get("access_token") or "")
            if not access_token:
                raise GitHubAuthenticationError(
                    "GitHub no devolvió un token de acceso válido en la respuesta de OAuth."
                )

            return GitHubOAuthToken(
                access_token=access_token,
                token_type=str(data.get("token_type") or "bearer"),
                scope=str(data.get("scope") or ""),
            )
        except (GitHubApiError, GitHubAuthenticationError):
            raise
        except httpx.TimeoutException as exc:
            raise GitHubApiError(f"Tiempo de espera agotado al conectar con GitHub OAuth: {exc}") from exc
        except httpx.RequestError as exc:
            raise GitHubApiError(f"Error de red al conectar con GitHub OAuth: {exc}") from exc

    async def delete_repository(self, token: str, owner: str, repo_name: str) -> bool:
        """Elimina un repositorio remoto si existe."""
        headers = self._headers_for_token(token)
        url = f"/repos/{owner}/{repo_name}"
        try:
            response = await self._client.delete(url, headers=headers)
            if response.status_code in (200, 204):
                return True
            if response.status_code == 404:
                return False
            self._handle_response_error(response, f"eliminar repositorio {owner}/{repo_name}")
            return False
        except (GitHubApiError, GitHubAuthenticationError, GitHubPermissionError, GitHubRateLimitError):
            raise
        except httpx.TimeoutException as exc:
            raise GitHubApiError(f"Tiempo de espera agotado al conectar con GitHub: {exc}") from exc
        except httpx.RequestError as exc:
            raise GitHubApiError(f"Error de red al conectar con GitHub: {exc}") from exc

    async def grant_app_installation_access(
        self,
        token: str,
        repo_id: int,
        app_slug: str = "railway",
    ) -> bool:
        """Asocia un repositorio a la instalación de una GitHub App (ej. Railway)
        si existe y está en modo de repositorios seleccionados.
        """
        headers = self._headers_for_token(token)
        try:
            response = await self._client.get("/user/installations", headers=headers)
            if not response.is_success:
                logger.debug(
                    "No se pudieron consultar instalaciones de GitHub Apps (%s): %s",
                    response.status_code,
                    response.text[:120],
                )
                return False

            data = cast(dict[str, object], response.json())
            installations = data.get("installations")
            if not isinstance(installations, list):
                return False

            target_slug = app_slug.strip().lower()
            for inst_item in cast(list[object], installations):
                if not isinstance(inst_item, dict):
                    continue
                inst = cast(dict[str, object], inst_item)
                current_slug = str(inst.get("app_slug") or "").strip().lower()
                if current_slug == target_slug or target_slug in current_slug:
                    inst_id = inst.get("id")
                    selection = str(inst.get("repository_selection") or "").strip().lower()
                    if selection == "all":
                        logger.info("GitHub App %s ya cuenta con acceso global a todos los repositorios.", app_slug)
                        return True
                    if inst_id:
                        put_resp = await self._client.put(
                            f"/user/installations/{inst_id}/repositories/{repo_id}",
                            headers=headers,
                        )
                        if put_resp.status_code in (200, 204):
                            logger.info(
                                "Repositorio %s concedido exitosamente a la instalación %s (%s).",
                                repo_id,
                                inst_id,
                                app_slug,
                            )
                            return True
                        logger.warning(
                            "GitHub rechazó asociar repo %s a instalación %s: %s",
                            repo_id,
                            inst_id,
                            put_resp.status_code,
                        )
            return False
        except Exception as exc:
            logger.warning("Error al autorizar repositorio con la GitHub App de %s: %s", app_slug, exc)
            return False
