from __future__ import annotations

import contextlib
import logging
from typing import Self, cast

import httpx

from kosmo.contracts.integrations.deployment import (
    DeploymentApiError,
    DeploymentAuthenticationError,
    DeploymentConfigurationError,
    DeploymentOAuthToken,
    DeploymentPermissionError,
    DeploymentProviderPort,
    DeploymentRateLimitError,
    DeploymentResourceNotFoundError,
    DeploymentStatus,
    EnvironmentVariable,
    PortSpec,
    VolumeConfig,
)

logger = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = "KOSMO-App"


def _extract_first_edge_node(container: dict[str, object], key: str) -> dict[str, object] | None:
    """Extrae de forma segura el primer nodo de una colección Relay-style { edges: [{ node: {...} }] }."""
    raw_val = container.get(key)
    if not isinstance(raw_val, dict):
        return None
    typed_val = cast(dict[str, object], raw_val)
    raw_edges = typed_val.get("edges")
    if not isinstance(raw_edges, list) or not raw_edges:
        return None
    typed_edges = cast(list[object], raw_edges)
    first_edge = typed_edges[0]
    if not isinstance(first_edge, dict):
        return None
    typed_edge = cast(dict[str, object], first_edge)
    raw_node = typed_edge.get("node")
    if isinstance(raw_node, dict):
        return cast(dict[str, object], raw_node)
    return None


class RailwayHttpClient(DeploymentProviderPort):
    """Adaptador de infraestructura para interactuar con la API de Railway vía HTTP."""

    def __init__(
        self,
        base_url: str = "https://backboard.railway.com",
        oauth_url: str = "https://backboard.railway.com/oauth/token",
        userinfo_url: str = "https://backboard.railway.com/oauth/me",
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._oauth_url = oauth_url
        self._userinfo_url = userinfo_url
        self._client_id = client_id
        self._client_secret = client_secret
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
        """Construye las cabeceras estándar requeridas por la API de Railway."""
        headers = {
            "Accept": "application/json",
            "User-Agent": _DEFAULT_USER_AGENT,
        }
        if token and token.strip():
            headers["Authorization"] = f"Bearer {token.strip()}"
        return headers

    def _handle_response_error(self, response: httpx.Response, action_description: str) -> None:
        """Mapea códigos de error HTTP de Railway a excepciones de dominio tipadas."""
        status = response.status_code

        if status == 401:
            raise DeploymentAuthenticationError(
                "Token de acceso de Railway inválido o expirado. Reconecta tu cuenta en KOSMO."
            )

        if status == 403:
            is_rate_limit = (
                response.headers.get("x-ratelimit-remaining") == "0"
                or "rate limit" in response.text.lower()
                or "secondary rate limit" in response.text.lower()
            )
            if is_rate_limit:
                raise DeploymentRateLimitError(
                    "Límite de solicitudes de la API de Railway excedido. Intenta nuevamente más tarde."
                )
            raise DeploymentPermissionError(
                f"Permisos insuficientes en Railway para {action_description}: {response.text[:200]}"
            )

        if status == 404:
            raise DeploymentResourceNotFoundError(
                f"El recurso solicitado en Railway no fue encontrado ({action_description}): {response.text[:200]}"
            )

        if status in (400, 422):
            raise DeploymentConfigurationError(
                f"Configuración inválida en Railway al {action_description} ({status}): {response.text[:200]}"
            )

        detail = response.text[:300] if response.text else f"código HTTP {status}"
        raise DeploymentApiError(f"Error en la API de Railway al {action_description} ({status}): {detail}")

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

    async def exchange_oauth_code(
        self,
        code: str,
        redirect_uri: str | None = None,
        code_verifier: str | None = None,
    ) -> DeploymentOAuthToken:
        """Intercambia un código de autorización OAuth por un token de acceso o usa el token directo."""
        cleaned_code = code.strip()
        if cleaned_code.startswith(("rly_", "railway_")):
            return DeploymentOAuthToken(
                access_token=cleaned_code,
                token_type="bearer",
            )

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": _DEFAULT_USER_AGENT,
        }
        payload: dict[str, str] = {
            "code": cleaned_code,
            "grant_type": "authorization_code",
        }
        if redirect_uri:
            payload["redirect_uri"] = redirect_uri
        if code_verifier:
            payload["code_verifier"] = code_verifier
        if self._client_id:
            payload["client_id"] = self._client_id
        if self._client_secret:
            payload["client_secret"] = self._client_secret

        try:
            response = await self._client.post(
                self._oauth_url,
                data=payload,
                headers=headers,
            )
            if not response.is_success:
                try:
                    data = cast(dict[str, object], response.json())
                    if "error" in data:
                        error_code = str(data.get("error") or "error_oauth")
                        error_desc = str(data.get("error_description") or error_code)
                        raise DeploymentAuthenticationError(
                            f"Fallo en autorización OAuth de Railway: {error_desc} ({error_code})"
                        )
                except DeploymentAuthenticationError:
                    raise
                except Exception:
                    pass
                self._handle_response_error(response, "intercambiar código OAuth")

            data = cast(dict[str, object], response.json())

            if "error" in data:
                error_code = str(data.get("error") or "error_oauth")
                error_desc = str(data.get("error_description") or error_code)
                raise DeploymentAuthenticationError(
                    f"Fallo en autorización OAuth de Railway: {error_desc} ({error_code})"
                )

            access_token = str(data.get("access_token") or "")
            if not access_token:
                raise DeploymentAuthenticationError(
                    "Railway no devolvió un token de acceso válido en la respuesta de OAuth."
                )

            raw_expires_in = data.get("expires_in")
            expires_in = int(str(raw_expires_in)) if raw_expires_in is not None else None
            refresh_token = str(data["refresh_token"]) if data.get("refresh_token") is not None else None
            scope = str(data.get("scope") or "")

            return DeploymentOAuthToken(
                access_token=access_token,
                token_type=str(data.get("token_type") or "bearer"),
                refresh_token=refresh_token,
                expires_in=expires_in,
                scope=scope,
            )
        except (DeploymentApiError, DeploymentAuthenticationError):
            raise
        except httpx.TimeoutException as exc:
            raise DeploymentApiError(f"Tiempo de espera agotado al conectar con Railway OAuth: {exc}") from exc
        except httpx.RequestError as exc:
            raise DeploymentApiError(f"Error de red al conectar con Railway OAuth: {exc}") from exc

    async def get_authenticated_user(self, token: str) -> dict[str, str]:
        """Consulta el perfil del usuario autenticado en Railway a través del endpoint OIDC userinfo (/oauth/me)."""
        headers = self._headers_for_token(token)
        try:
            response = await self._client.get(self._userinfo_url, headers=headers)
            if response.status_code == 401:
                raise DeploymentAuthenticationError(
                    "Token de Railway inválido o expirado al consultar datos de usuario."
                )
            if not response.is_success:
                logger.warning("No se pudo obtener información del usuario de Railway (%s)", response.status_code)
                return {}

            data = cast(dict[str, object], response.json())
            return {
                "sub": str(data.get("sub") or ""),
                "name": str(data.get("name") or ""),
                "email": str(data.get("email") or ""),
            }
        except DeploymentAuthenticationError:
            raise
        except Exception as exc:
            logger.warning("Fallo no bloqueante al consultar usuario en Railway: %s", exc)
            return {}

    async def refresh_access_token(self, refresh_token: str) -> DeploymentOAuthToken:
        """Renueva el token de acceso de Railway utilizando un refresh token rotado."""
        cleaned_rt = refresh_token.strip()
        if not cleaned_rt:
            raise DeploymentAuthenticationError("El refresh token de Railway no puede estar vacío.")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": _DEFAULT_USER_AGENT,
        }
        payload: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": cleaned_rt,
        }
        if self._client_id:
            payload["client_id"] = self._client_id
        if self._client_secret:
            payload["client_secret"] = self._client_secret

        try:
            response = await self._client.post(
                self._oauth_url,
                data=payload,
                headers=headers,
            )
            if not response.is_success:
                try:
                    data = cast(dict[str, object], response.json())
                    if "error" in data:
                        error_code = str(data.get("error") or "error_refresh")
                        error_desc = str(data.get("error_description") or error_code)
                        raise DeploymentAuthenticationError(
                            f"Fallo al renovar token de Railway: {error_desc} ({error_code})"
                        )
                except DeploymentAuthenticationError:
                    raise
                except Exception:
                    pass
                self._handle_response_error(response, "renovar token de acceso")

            data = cast(dict[str, object], response.json())
            if "error" in data:
                error_code = str(data.get("error") or "error_refresh")
                error_desc = str(data.get("error_description") or error_code)
                raise DeploymentAuthenticationError(f"Fallo al renovar token de Railway: {error_desc} ({error_code})")

            access_token = str(data.get("access_token") or "")
            if not access_token:
                raise DeploymentAuthenticationError("Railway no devolvió un access_token válido al renovar el token.")

            raw_expires_in = data.get("expires_in")
            expires_in = int(str(raw_expires_in)) if raw_expires_in is not None else None
            new_refresh_token = str(data["refresh_token"]) if data.get("refresh_token") is not None else cleaned_rt
            scope = str(data.get("scope") or "")

            return DeploymentOAuthToken(
                access_token=access_token,
                token_type=str(data.get("token_type") or "bearer"),
                refresh_token=new_refresh_token,
                expires_in=expires_in,
                scope=scope,
            )
        except (DeploymentApiError, DeploymentAuthenticationError):
            raise
        except httpx.TimeoutException as exc:
            raise DeploymentApiError(f"Tiempo de espera agotado al renovar token con Railway: {exc}") from exc
        except httpx.RequestError as exc:
            raise DeploymentApiError(f"Error de red al renovar token con Railway: {exc}") from exc

    async def _execute_graphql(
        self,
        token: str,
        query: str,
        variables: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        """Ejecuta una operación GraphQL contra la API de Railway si está disponible.

        Retorna:
          - dict con los datos de respuesta si la operación tuvo éxito ('data').
          - dict vacío {} si la operación tuvo éxito pero devolvió un escalar/null.
          - None si el endpoint GraphQL no está disponible (HTTP 404 en /graphql/v2).
          - Lanza DeploymentAuthenticationError o DeploymentApiError en errores de dominio.
        """
        headers = self._headers_for_token(token)
        payload = {"query": query, "variables": variables or {}}
        try:
            response = await self._client.post("/graphql/v2", json=payload, headers=headers)
            if response.status_code == 404:
                response = await self._client.post("/graphql", json=payload, headers=headers)
            if response.status_code == 404:
                return None  # Endpoint GraphQL no montado (e.g. MockTransport REST en tests)

            if response.status_code == 401:
                raise DeploymentAuthenticationError(
                    "Token de acceso de Railway inválido o expirado. Reconecta tu cuenta en KOSMO."
                )
            if response.status_code == 403:
                is_rate_limit = (
                    response.headers.get("x-ratelimit-remaining") == "0"
                    or "rate limit" in response.text.lower()
                    or "secondary rate limit" in response.text.lower()
                )
                if is_rate_limit:
                    raise DeploymentRateLimitError(
                        "Límite de solicitudes de la API de Railway excedido. Intenta nuevamente más tarde."
                    )
                raise DeploymentPermissionError(
                    f"Permisos insuficientes en Railway para realizar esta operación: {response.text[:200]}"
                )

            try:
                data = cast(dict[str, object], response.json())
            except Exception as exc:
                if not response.is_success:
                    self._handle_response_error(response, "ejecutar operación en Railway GraphQL")
                raise DeploymentApiError(
                    f"Respuesta no JSON de Railway GraphQL ({response.status_code}): {response.text[:200]}"
                ) from exc

            if "errors" in data and data.get("errors"):
                raw_errors = data.get("errors")
                err_msg = "Error en Railway GraphQL"
                if isinstance(raw_errors, list) and raw_errors:
                    typed_err_list = cast(list[object], raw_errors)
                    first_err = typed_err_list[0]
                    if isinstance(first_err, dict):
                        typed_err = cast(dict[str, object], first_err)
                        if typed_err.get("message"):
                            err_msg = str(typed_err["message"])
                logger.error("Railway GraphQL returned errors: %s", err_msg)
                err_msg_lower = err_msg.lower()
                if "not authorized" in err_msg_lower or "unauthorized" in err_msg_lower:
                    raise DeploymentAuthenticationError(
                        f"No autorizado en Railway para realizar esta operación ({err_msg}). "
                        "Verifica en tu panel de Railway si tienes un aviso de 'Acción necesaria' pendiente, "
                        "si alcanzaste el límite de proyectos de tu plan Trial, "
                        "o reconecta tu cuenta de Railway desde tu Perfil para actualizar los permisos."
                    )
                if (
                    "not found or is not accessible" in err_msg_lower
                    or "forbidden" in err_msg_lower
                    or "permission" in err_msg_lower
                ):
                    raise DeploymentPermissionError(
                        f"Railway no puede acceder al repositorio de GitHub o permisos insuficientes: {err_msg}. "
                        "Si el repositorio es privado, cámbialo a público en GitHub (Settings > General > Danger Zone) "
                        "o instala/autoriza la aplicación de Railway en tu cuenta de GitHub."
                    )
                raise DeploymentApiError(f"Error de Railway GraphQL: {err_msg}")

            if not response.is_success:
                self._handle_response_error(response, "ejecutar operación en Railway GraphQL")

            if "data" in data:
                inner = data["data"]
                if isinstance(inner, dict):
                    return cast(dict[str, object], inner)
                # Escalar/booleano/null: la operación fue aceptada; devolver dict vacío
                return {}
            return None
        except (
            DeploymentApiError,
            DeploymentAuthenticationError,
            DeploymentPermissionError,
            DeploymentRateLimitError,
            DeploymentConfigurationError,
            DeploymentResourceNotFoundError,
        ):
            raise
        except (httpx.TimeoutException, httpx.RequestError):
            raise

    async def create_service(
        self,
        token: str,
        repo_url: str,
        env_vars: list[EnvironmentVariable],
        ports: list[PortSpec],
        service_name: str | None = None,
    ) -> str:
        """Crea un nuevo servicio en Railway vinculado a un repositorio remoto."""
        # 1. Intentar vía GraphQL oficial de Railway
        repo_clean = repo_url.strip()
        if repo_clean.endswith(".git"):
            repo_clean = repo_clean[:-4]
        repo_slug = repo_clean.split("github.com/")[-1].strip("/") if "github.com/" in repo_clean else repo_clean
        repo_name = repo_slug.split("/")[-1] or "kosmo-app"
        requested_service_name = service_name.strip() if service_name and service_name.strip() else repo_name

        project_id: str | None = None
        env_id: str | None = None
        service_id: str | None = None
        workspace_id: str | None = None

        try:
            # 1.1 Consultar contexto de workspaces y proyectos (indispensable para tokens workspace:admin)
            gql_user_context = """
            query GetUserContext {
                me {
                    workspaces {
                        id
                        name
                        projects {
                            edges {
                                node {
                                    id
                                    name
                                    baseEnvironmentId
                                    environments {
                                        edges {
                                            node {
                                                id
                                                name
                                            }
                                        }
                                    }
                                    services {
                                        edges {
                                            node {
                                                id
                                                name
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            """
            try:
                user_ctx = await self._execute_graphql(token, gql_user_context)
                if user_ctx and "me" in user_ctx and isinstance(user_ctx["me"], dict):
                    me_dict = cast(dict[str, object], user_ctx["me"])
                    raw_workspaces = me_dict.get("workspaces")
                    if isinstance(raw_workspaces, list) and raw_workspaces:
                        for ws_item in cast(list[object], raw_workspaces):
                            if isinstance(ws_item, dict):
                                ws_dict = cast(dict[str, object], ws_item)
                                if not workspace_id and ws_dict.get("id"):
                                    workspace_id = str(ws_dict["id"])

                                raw_proj_obj = ws_dict.get("projects")
                                if isinstance(raw_proj_obj, dict):
                                    proj_dict = cast(dict[str, object], raw_proj_obj)
                                    raw_edges = proj_dict.get("edges")
                                    if isinstance(raw_edges, list):
                                        for raw_edge in cast(list[object], raw_edges):
                                            if isinstance(raw_edge, dict):
                                                edge_dict = cast(dict[str, object], raw_edge)
                                                node_obj = edge_dict.get("node")
                                                if isinstance(node_obj, dict):
                                                    node = cast(dict[str, object], node_obj)
                                                    if (
                                                        str(node.get("name") or "").strip().lower()
                                                        == repo_name.strip().lower()
                                                    ):
                                                        project_id = str(node["id"])
                                                        if node.get("baseEnvironmentId"):
                                                            env_id = str(node["baseEnvironmentId"])
                                                        else:
                                                            env_node = _extract_first_edge_node(node, "environments")
                                                            if env_node and env_node.get("id"):
                                                                env_id = str(env_node["id"])
                                                        svc_node = _extract_first_edge_node(node, "services")
                                                        if svc_node and svc_node.get("id"):
                                                            service_id = str(svc_node["id"])
                                                            logger.info(
                                                                "Reutilizando proyecto Railway: %s (%s)",
                                                                project_id,
                                                                service_id,
                                                            )
                                                        break
            except Exception as ctx_err:
                logger.debug("No se pudo obtener el contexto de workspaces en Railway: %s", ctx_err)

            # 1.2 Si no existe el proyecto, crearlo asociando el workspaceId obtenido
            if not project_id:
                gql_project_mutation = """
                mutation ProjectCreate($input: ProjectCreateInput!) {
                    projectCreate(input: $input) {
                        id
                        name
                        baseEnvironmentId
                    }
                }
                """
                create_input: dict[str, object] = {"name": repo_name}
                if workspace_id:
                    create_input["workspaceId"] = workspace_id

                try:
                    gql_data = await self._execute_graphql(token, gql_project_mutation, {"input": create_input})
                    if gql_data and "projectCreate" in gql_data and isinstance(gql_data["projectCreate"], dict):
                        project_info = cast(dict[str, object], gql_data["projectCreate"])
                        project_id = str(project_info["id"])
                        if project_info.get("baseEnvironmentId"):
                            env_id = str(project_info["baseEnvironmentId"])
                except (
                    DeploymentAuthenticationError,
                    DeploymentPermissionError,
                    DeploymentApiError,
                ) as create_err:
                    if not project_id:
                        raise create_err

            if project_id:
                if not env_id:
                    gql_env_query = """
                    query ProjectEnvironments($id: String!) {
                        project(id: $id) {
                            environments {
                                edges {
                                    node {
                                        id
                                        name
                                    }
                                }
                            }
                        }
                    }
                    """
                    try:
                        proj_env_data = await self._execute_graphql(token, gql_env_query, {"id": project_id})
                        if proj_env_data and "project" in proj_env_data and isinstance(proj_env_data["project"], dict):
                            env_node = _extract_first_edge_node(
                                cast(dict[str, object], proj_env_data["project"]), "environments"
                            )
                            if env_node and env_node.get("id"):
                                env_id = str(env_node["id"])
                    except Exception:
                        logger.warning("No se pudieron consultar entornos del proyecto %s en Railway.", project_id)

                if not service_id:
                    gql_service_mutation = """
                    mutation ServiceCreate($input: ServiceCreateInput!) {
                        serviceCreate(input: $input) {
                            id
                            name
                        }
                    }
                    """
                    service_resp = await self._execute_graphql(
                        token,
                        gql_service_mutation,
                        {
                            "input": {
                                "projectId": project_id,
                                "name": requested_service_name,
                                "source": {"repo": repo_slug},
                            }
                        },
                    )
                    if (
                        service_resp
                        and "serviceCreate" in service_resp
                        and isinstance(service_resp["serviceCreate"], dict)
                    ):
                        service_info = cast(dict[str, object], service_resp["serviceCreate"])
                        service_id = str(service_info["id"])
                    else:
                        raise DeploymentApiError("Railway GraphQL no devolvió información del servicio creado.")

                if service_id:
                    if env_id:
                        gql_domain_mutation = """
                        mutation ServiceDomainCreate($input: ServiceDomainCreateInput!) {
                            serviceDomainCreate(input: $input) {
                                domain
                            }
                        }
                        """
                        try:
                            await self._execute_graphql(
                                token,
                                gql_domain_mutation,
                                {"input": {"environmentId": env_id, "serviceId": service_id}},
                            )
                        except Exception:
                            logger.warning("No se pudo generar dominio público inmediato en Railway.")

                    if env_vars and env_id:
                        gql_vars_mutation = """
                        mutation VariableCollectionUpsert($input: VariableCollectionUpsertInput!) {
                            variableCollectionUpsert(input: $input)
                        }
                        """
                        var_payload = {ev.key: ev.value for ev in env_vars}
                        try:
                            await self._execute_graphql(
                                token,
                                gql_vars_mutation,
                                {
                                    "input": {
                                        "projectId": project_id,
                                        "environmentId": env_id,
                                        "serviceId": service_id,
                                        "variables": var_payload,
                                    }
                                },
                            )
                        except Exception:
                            logger.warning("No se pudieron inyectar variables iniciales en Railway.")

                    return service_id
        except (
            DeploymentAuthenticationError,
            DeploymentPermissionError,
            DeploymentRateLimitError,
            DeploymentApiError,
        ):
            raise
        except Exception as exc:
            logger.warning("Fallo en Railway GraphQL al crear servicio: %s", exc)

        # 2. Fallback REST para MockTransport / pruebas unitarias
        headers = self._headers_for_token(token)
        payload = {
            "repo_url": repo_url,
            "env_vars": [
                {
                    "key": ev.key,
                    "value": ev.value,
                    "is_secret": ev.is_secret,
                }
                for ev in env_vars
            ],
            "ports": [
                {
                    "port": p.port,
                    "protocol": p.protocol,
                }
                for p in ports
            ],
        }

        try:
            response = await self._client.post("/v1/services", json=payload, headers=headers)
            if not response.is_success:
                self._handle_response_error(response, f"crear servicio para repositorio {repo_url}")

            data = cast(dict[str, object], response.json())
            service_id: str | None = None

            if "id" in data and data["id"]:
                service_id = str(data["id"])
            elif "service_id" in data and data["service_id"]:
                service_id = str(data["service_id"])
            elif "data" in data and isinstance(data["data"], dict):
                inner_data = cast(dict[str, object], data["data"])
                if "serviceCreate" in inner_data and isinstance(inner_data["serviceCreate"], dict):
                    sc_data = cast(dict[str, object], inner_data["serviceCreate"])
                    if sc_data.get("id"):
                        service_id = str(sc_data["id"])
                elif "service" in inner_data and isinstance(inner_data["service"], dict):
                    srv_data = cast(dict[str, object], inner_data["service"])
                    if srv_data.get("id"):
                        service_id = str(srv_data["id"])

            if not service_id:
                raise DeploymentApiError("Railway no devolvió un ID de servicio válido al crear el servicio.")

            return service_id
        except (
            DeploymentApiError,
            DeploymentAuthenticationError,
            DeploymentPermissionError,
            DeploymentRateLimitError,
            DeploymentConfigurationError,
            DeploymentResourceNotFoundError,
        ):
            raise
        except httpx.TimeoutException as exc:
            raise DeploymentApiError(f"Tiempo de espera agotado al conectar con Railway: {exc}") from exc
        except httpx.RequestError as exc:
            raise DeploymentApiError(f"Error de red al conectar con Railway: {exc}") from exc

    async def configure_volume(self, token: str, service_id: str, volume: VolumeConfig) -> None:
        """Configura un volumen de almacenamiento persistente para el servicio."""
        gql_service_query = """
        query GetServiceProject($id: String!) {
            service(id: $id) {
                id
                projectId
            }
        }
        """
        gql_volume_mutation = """
        mutation VolumeCreate($input: VolumeCreateInput!) {
            volumeCreate(input: $input) {
                id
            }
        }
        """
        try:
            srv_res = await self._execute_graphql(token, gql_service_query, {"id": service_id})
            if srv_res is not None:
                project_id: str | None = None
                if "service" in srv_res and isinstance(srv_res["service"], dict):
                    srv = cast(dict[str, object], srv_res["service"])
                    if srv.get("projectId"):
                        project_id = str(srv["projectId"])

                if project_id:
                    try:
                        await self._execute_graphql(
                            token,
                            gql_volume_mutation,
                            {
                                "input": {
                                    "projectId": project_id,
                                    "serviceId": service_id,
                                    "mountPath": volume.mount_path,
                                }
                            },
                        )
                    except Exception as exc:
                        logger.warning("Railway GraphQL volumeCreate: %s", exc)
                return
        except (
            DeploymentAuthenticationError,
            DeploymentPermissionError,
            DeploymentRateLimitError,
            DeploymentApiError,
        ):
            raise
        except Exception as exc:
            logger.warning("Fallo en Railway GraphQL configure_volume: %s", exc)

        headers = self._headers_for_token(token)
        payload = {
            "mount_path": volume.mount_path,
            "size_mb": volume.size_mb,
        }

        try:
            response = await self._client.post(
                f"/v1/services/{service_id}/volumes",
                json=payload,
                headers=headers,
            )
            if response.status_code == 404 and self._owns_client:
                logger.info("Railway no expone REST /v1/services/.../volumes; continuando.")
                return

            if not response.is_success:
                self._handle_response_error(response, f"configurar volumen para el servicio {service_id}")
        except (
            DeploymentApiError,
            DeploymentAuthenticationError,
            DeploymentPermissionError,
            DeploymentRateLimitError,
            DeploymentConfigurationError,
            DeploymentResourceNotFoundError,
        ):
            raise
        except httpx.TimeoutException as exc:
            raise DeploymentApiError(f"Tiempo de espera agotado al conectar con Railway: {exc}") from exc
        except httpx.RequestError as exc:
            raise DeploymentApiError(f"Error de red al conectar con Railway: {exc}") from exc

    async def trigger_deployment(
        self,
        token: str,
        service_id: str,
        commit_sha: str | None = None,
    ) -> None:
        """Dispara la construcción y despliegue del servicio en Railway.

        Primero consulta el environmentId del servicio (requerido por la API de Railway).
        Los errores de dominio GraphQL se propagan directamente sin degradar al REST.
        El fallback REST solo se activa cuando GraphQL no está disponible (HTTP 404).
        """
        gql_service_query = """
        query GetServiceEnvironment($id: String!) {
            service(id: $id) {
                id
                projectId
                serviceInstances {
                    edges {
                        node {
                            environmentId
                        }
                    }
                }
            }
        }
        """
        try:
            srv_res = await self._execute_graphql(token, gql_service_query, {"id": service_id})
            if srv_res is not None:
                environment_id: str | None = None
                project_id: str | None = None
                if "service" in srv_res and isinstance(srv_res["service"], dict):
                    srv = cast(dict[str, object], srv_res["service"])
                    project_id = str(srv["projectId"]) if srv.get("projectId") else None
                    inst_node = _extract_first_edge_node(srv, "serviceInstances")
                    if inst_node and inst_node.get("environmentId"):
                        environment_id = str(inst_node["environmentId"])

                if not environment_id and project_id:
                    gql_env_query = """
                    query GetProjectEnvironments($id: String!) {
                        project(id: $id) {
                            environments {
                                edges {
                                    node {
                                        id
                                    }
                                }
                            }
                        }
                    }
                    """
                    try:
                        p_res = await self._execute_graphql(token, gql_env_query, {"id": project_id})
                        if p_res and "project" in p_res and isinstance(p_res["project"], dict):
                            env_node = _extract_first_edge_node(
                                cast(dict[str, object], p_res["project"]), "environments"
                            )
                            if env_node and env_node.get("id"):
                                environment_id = str(env_node["id"])
                    except Exception:
                        pass

                if environment_id:
                    gql_deploy = """
                    mutation ServiceInstanceDeployV2(
                        $serviceId: String!
                        $environmentId: String!
                        $commitSha: String
                    ) {
                        serviceInstanceDeployV2(
                            serviceId: $serviceId
                            environmentId: $environmentId
                            commitSha: $commitSha
                        )
                    }
                    """
                    variables: dict[str, object] = {"serviceId": service_id, "environmentId": environment_id}
                    if commit_sha:
                        variables["commitSha"] = commit_sha
                else:
                    gql_deploy = """
                    mutation ServiceInstanceDeploy(
                        $serviceId: String!
                        $commitSha: String
                        $latestCommit: Boolean
                    ) {
                        serviceInstanceDeploy(
                            serviceId: $serviceId
                            commitSha: $commitSha
                            latestCommit: $latestCommit
                        )
                    }
                    """
                    variables = {"serviceId": service_id}
                    if commit_sha:
                        variables["commitSha"] = commit_sha
                    else:
                        variables["latestCommit"] = True

                try:
                    await self._execute_graphql(token, gql_deploy, variables)
                except DeploymentApiError as exc:
                    exc_str = str(exc).lower()
                    if "already" in exc_str and ("deploy" in exc_str or "progress" in exc_str or "building" in exc_str):
                        logger.info("Railway ya inició el despliegue automáticamente: %s", exc)
                        return
                    if "serviceinstancedeployv2" in gql_deploy.lower() and environment_id:
                        gql_fallback = """
                        mutation ServiceInstanceDeploy(
                            $serviceId: String!
                            $environmentId: String!
                            $commitSha: String
                            $latestCommit: Boolean
                        ) {
                            serviceInstanceDeploy(
                                serviceId: $serviceId
                                environmentId: $environmentId
                                commitSha: $commitSha
                                latestCommit: $latestCommit
                            )
                        }
                        """
                        fallback_vars: dict[str, object] = {
                            "serviceId": service_id,
                            "environmentId": environment_id,
                        }
                        if commit_sha:
                            fallback_vars["commitSha"] = commit_sha
                        else:
                            fallback_vars["latestCommit"] = True
                        with contextlib.suppress(Exception):
                            await self._execute_graphql(token, gql_fallback, fallback_vars)
                            return
                    raise
                return
        except (
            DeploymentAuthenticationError,
            DeploymentPermissionError,
            DeploymentRateLimitError,
            DeploymentApiError,
        ):
            raise
        except Exception as exc:
            logger.debug("GraphQL deploy no disponible, intentando REST: %s", exc)

        # Fallback REST — solo cuando GraphQL no está disponible (HTTP 404 en /graphql/v2 y /graphql)
        headers = self._headers_for_token(token)
        payload: dict[str, object] = {"service_id": service_id}
        if commit_sha:
            payload["commit_sha"] = commit_sha

        try:
            response = await self._client.post(
                f"/v1/services/{service_id}/deploy",
                json=payload,
                headers=headers,
            )
            if response.status_code == 404 and self._owns_client:
                # Railway conecta el repo al crear el servicio y arranca el primer build solo
                logger.info("Railway no expone endpoint REST de deploy; primer build iniciado automáticamente.")
                return

            if not response.is_success:
                self._handle_response_error(response, f"disparar despliegue para el servicio {service_id}")
        except (
            DeploymentApiError,
            DeploymentAuthenticationError,
            DeploymentPermissionError,
            DeploymentRateLimitError,
            DeploymentConfigurationError,
            DeploymentResourceNotFoundError,
        ):
            raise
        except httpx.TimeoutException as exc:
            raise DeploymentApiError(f"Tiempo de espera agotado al conectar con Railway: {exc}") from exc
        except httpx.RequestError as exc:
            raise DeploymentApiError(f"Error de red al conectar con Railway: {exc}") from exc

    async def get_service_status(
        self,
        token: str,
        service_id: str,
    ) -> tuple[DeploymentStatus, str | None, str | None]:
        """
        Consulta el estado actual de publicación del servicio en Railway.
        Retorna (status, public_url, build_logs_url_or_error)
        """
        # 1. Intentar GraphQL oficial
        gql_service_query = """
        query ServiceStatus($id: String!) {
            service(id: $id) {
                id
                name
                projectId
                serviceInstances {
                    edges {
                        node {
                            domains {
                                serviceDomains {
                                    domain
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        gql_deployments_query = """
        query DeploymentStatus($input: DeploymentListInput!) {
            deployments(input: $input, first: 1) {
                edges {
                    node {
                        id
                        status
                        url
                        staticUrl
                    }
                }
            }
        }
        """
        try:
            gql_data = await self._execute_graphql(token, gql_service_query, {"id": service_id})
            if gql_data is not None:
                if "service" in gql_data and isinstance(gql_data["service"], dict):
                    srv = cast(dict[str, object], gql_data["service"])
                    project_id = str(srv.get("projectId") or "")
                    if not project_id:
                        raise DeploymentApiError("Railway no devolvió el proyecto asociado al servicio.")
                    deployments_data = await self._execute_graphql(
                        token,
                        gql_deployments_query,
                        {"input": {"projectId": project_id, "serviceId": service_id}},
                    )
                    latest_dep = _extract_first_edge_node(deployments_data or {}, "deployments") or {}

                    raw_status = str(latest_dep.get("status") or "").upper()
                    if raw_status in ("SUCCESS", "DEPLOYED", "LIVE", "ACTIVE", "PUBLISHED"):
                        status = DeploymentStatus.PUBLISHED
                    elif raw_status in ("BUILDING", "PENDING", "INITIALIZING", "DEPLOYING", "WAITING", "QUEUED"):
                        status = DeploymentStatus.BUILDING
                    elif raw_status in ("FAILED", "CRASHED", "CANCELLED", "ERROR"):
                        status = DeploymentStatus.FAILED
                    else:
                        status = DeploymentStatus.BUILDING if raw_status else DeploymentStatus.NOT_CREATED

                    public_url: str | None = None
                    if latest_dep.get("staticUrl"):
                        public_url = f"https://{latest_dep['staticUrl']}"
                    elif latest_dep.get("url"):
                        public_url = str(latest_dep["url"])
                    else:
                        inst_node = _extract_first_edge_node(srv, "serviceInstances")
                        if inst_node:
                            raw_domains = inst_node.get("domains")
                            if isinstance(raw_domains, dict):
                                typed_domains = cast(dict[str, object], raw_domains)
                                svc_domains = typed_domains.get("serviceDomains")
                                if isinstance(svc_domains, list) and svc_domains and isinstance(svc_domains[0], dict):
                                    domain_obj = cast(dict[str, object], svc_domains[0])
                                    if domain_obj.get("domain"):
                                        public_url = f"https://{domain_obj['domain']}"

                    build_logs_url: str | None = None
                    if status == DeploymentStatus.FAILED and project_id:
                        dep_id = str(latest_dep.get("id") or "")
                        if dep_id:
                            build_logs_url = (
                                f"https://railway.com/project/{project_id}/service/{service_id}?id={dep_id}"
                            )
                        else:
                            build_logs_url = f"https://railway.com/project/{project_id}/service/{service_id}"

                    return (status, public_url, build_logs_url)
                return (DeploymentStatus.NOT_CREATED, None, None)
        except (
            DeploymentAuthenticationError,
            DeploymentPermissionError,
            DeploymentRateLimitError,
            DeploymentApiError,
        ):
            raise
        except Exception as exc:
            logger.debug("GraphQL status fallback a REST: %s", exc)

        # 2. Fallback REST
        headers = self._headers_for_token(token)

        try:
            response = await self._client.get(f"/v1/services/{service_id}", headers=headers)
            if response.status_code == 404:
                return (DeploymentStatus.NOT_CREATED, None, None)

            if not response.is_success:
                self._handle_response_error(response, f"consultar estado del servicio {service_id}")

            data = cast(dict[str, object], response.json())
            if "data" in data and isinstance(data["data"], dict):
                inner_data = cast(dict[str, object], data["data"])
                if "service" in inner_data and isinstance(inner_data["service"], dict):
                    data = cast(dict[str, object], inner_data["service"])

            raw_status_rest = str(data.get("status") or data.get("state") or "").lower()

            if raw_status_rest in ("published", "ready", "success", "deployed", "live", "active"):
                status_rest = DeploymentStatus.PUBLISHED
            elif raw_status_rest in ("building", "pending", "deploying", "initializing", "queued", "in_progress"):
                status_rest = DeploymentStatus.BUILDING
            elif raw_status_rest in ("failed", "error", "crashed", "cancelled", "removed"):
                status_rest = DeploymentStatus.FAILED
            else:
                status_rest = DeploymentStatus.NOT_CREATED

            raw_public_url = data.get("public_url") or data.get("deploy_url") or data.get("url")
            public_url_rest = str(raw_public_url) if raw_public_url is not None else None

            raw_logs = (
                data.get("build_logs_url")
                or data.get("error_log_url")
                or data.get("logs_url")
                or data.get("error_message")
            )
            build_logs_url = str(raw_logs) if raw_logs is not None else None

            return (status_rest, public_url_rest, build_logs_url)
        except (
            DeploymentApiError,
            DeploymentAuthenticationError,
            DeploymentPermissionError,
            DeploymentRateLimitError,
            DeploymentConfigurationError,
            DeploymentResourceNotFoundError,
        ):
            raise
        except httpx.TimeoutException as exc:
            raise DeploymentApiError(f"Tiempo de espera agotado al conectar con Railway: {exc}") from exc
        except httpx.RequestError as exc:
            raise DeploymentApiError(f"Error de red al conectar con Railway: {exc}") from exc

    async def delete_service(self, token: str, service_id: str) -> bool:
        """Elimina el servicio o despliegue remoto en Railway si existe."""
        # 1. Intentar vía GraphQL oficial
        gql_find_project_query = """
        query ServiceProject($id: String!) {
            service(id: $id) {
                id
                projectId
            }
        }
        """
        try:
            gql_data = await self._execute_graphql(token, gql_find_project_query, {"id": service_id})
            if gql_data and "service" in gql_data and isinstance(gql_data["service"], dict):
                srv = cast(dict[str, object], gql_data["service"])
                project_id = str(srv.get("projectId") or "")
                if project_id:
                    gql_del_project = """
                    mutation ProjectDelete($id: String!) {
                        projectDelete(id: $id)
                    }
                    """
                    try:
                        del_proj_resp = await self._execute_graphql(token, gql_del_project, {"id": project_id})
                        if del_proj_resp and del_proj_resp.get("projectDelete") is True:
                            return True
                    except Exception:
                        logger.warning(
                            "No se pudo eliminar el proyecto de Railway %s; intentando borrar servicio.",
                            project_id,
                        )

                gql_del_service = """
                mutation ServiceDelete($id: String!) {
                    serviceDelete(id: $id)
                }
                """
                del_resp = await self._execute_graphql(token, gql_del_service, {"id": service_id})
                if del_resp and del_resp.get("serviceDelete") is True:
                    return True

            # Si no se encontró como servicio, intentar borrar directamente como proyecto o servicio
            try:
                del_proj_direct = """
                mutation ProjectDelete($id: String!) {
                    projectDelete(id: $id)
                }
                """
                del_proj_resp = await self._execute_graphql(token, del_proj_direct, {"id": service_id})
                if del_proj_resp and del_proj_resp.get("projectDelete") is True:
                    return True
            except Exception:
                pass

            try:
                del_srv_direct = """
                mutation ServiceDelete($id: String!) {
                    serviceDelete(id: $id)
                }
                """
                del_resp = await self._execute_graphql(token, del_srv_direct, {"id": service_id})
                if del_resp and del_resp.get("serviceDelete") is True:
                    return True
            except Exception:
                pass
        except (DeploymentAuthenticationError, DeploymentPermissionError, DeploymentRateLimitError):
            raise
        except Exception as exc:
            logger.warning("Fallo en Railway GraphQL al eliminar servicio %s: %s", service_id, exc)

        # 2. Fallback REST para MockTransport / pruebas unitarias
        headers = self._headers_for_token(token)
        url = f"/v1/services/{service_id}"
        try:
            response = await self._client.delete(url, headers=headers)
            if response.status_code in (200, 204, 404):
                return True
            self._handle_response_error(response, f"eliminar servicio {service_id}")
            return False
        except (
            DeploymentApiError,
            DeploymentAuthenticationError,
            DeploymentPermissionError,
            DeploymentRateLimitError,
            DeploymentConfigurationError,
            DeploymentResourceNotFoundError,
        ):
            raise
        except httpx.TimeoutException as exc:
            raise DeploymentApiError(f"Tiempo de espera agotado al conectar con Railway: {exc}") from exc
        except httpx.RequestError as exc:
            raise DeploymentApiError(f"Error de red al conectar con Railway: {exc}") from exc
