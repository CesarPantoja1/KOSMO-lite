from __future__ import annotations

import asyncio
import contextlib
import inspect
import ipaddress
from typing import Any, cast

import structlog
from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from kosmo.contracts.sdd.ids import FeatureId
from kosmo.infrastructure.api.dependencies.container import get_container

_log = structlog.get_logger("kosmo.rate_limit")
_DEFAULT_TRUSTED_PROXIES = "127.0.0.1,::1,testclient,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
_REDIS_EVAL_TIMEOUT_SECONDS: float = 1.0


def _should_fail_closed(container: Any) -> bool:
    settings = getattr(container, "settings", None)
    if settings is None:
        return False
    rl_req = getattr(settings, "rate_limit_required", False)
    env = getattr(settings, "env", "")
    return (rl_req is True) or (isinstance(env, str) and env in ("production", "staging"))


def _is_trusted_proxy(host: str, trusted_proxies_cfg: str) -> bool:
    if not host:
        return False
    proxies = [p.strip() for p in trusted_proxies_cfg.split(",") if p.strip()]
    if host in proxies:
        return True
    try:
        host_ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    for proxy in proxies:
        try:
            if "/" in proxy:
                if host_ip in ipaddress.ip_network(proxy, strict=False):
                    return True
            elif host_ip == ipaddress.ip_address(proxy):
                return True
        except ValueError:
            continue
    return False


def _resolve_client_ip(request: Request, container: Any) -> str:
    host = request.client.host if request.client else ""
    if not host:
        return "unknown"

    settings = getattr(container, "settings", None)
    trusted_proxies = getattr(settings, "trusted_proxies", _DEFAULT_TRUSTED_PROXIES)
    if _is_trusted_proxy(host, trusted_proxies):
        header_ip = (request.headers.get("x-kosmo-client-ip") or "").strip()
        if header_ip:
            try:
                ipaddress.ip_address(header_ip)
                return header_ip
            except ValueError:
                pass
    return host


class IpRateLimiter:
    _LUA_SCRIPT = """
        local key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local current = redis.call('INCR', key)
        if current == 1 then
            redis.call('EXPIRE', key, window)
        end
        return current
    """

    def __init__(self, requests_per_minute: int) -> None:
        self._limit = requests_per_minute

    async def __call__(self, request: Request) -> None:
        container = get_container(request)
        redis = cast(Any, getattr(container, "redis", None))
        fail_closed = _should_fail_closed(container)

        if redis is None:
            if fail_closed:
                _log.error("rate_limit.redis_unavailable_fail_closed", path=request.url.path)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Servicio de limitación de tasa no disponible.",
                )
            _log.warning("rate_limit.bypassed_no_redis", path=request.url.path)
            return

        # Public deployments pass the client address through a trusted reverse proxy
        # in x-kosmo-client-ip. Header is only trusted if the connection originates
        # from a verified trusted proxy address or subnet.
        client_ip = _resolve_client_ip(request, container)
        key = f"auth:ip_rate:{request.url.path}:{client_ip}"
        try:

            async def _run_eval() -> int:
                eval_res = redis.eval(self._LUA_SCRIPT, 1, key, str(self._limit), "60")
                if inspect.isawaitable(eval_res):
                    eval_res = await eval_res
                return int(eval_res)

            count = await asyncio.wait_for(_run_eval(), timeout=_REDIS_EVAL_TIMEOUT_SECONDS)
            if count > self._limit:

                async def _run_ttl() -> int:
                    ttl_res = redis.ttl(key)
                    if inspect.isawaitable(ttl_res):
                        ttl_res = await ttl_res
                    return int(ttl_res)

                ttl = await asyncio.wait_for(_run_ttl(), timeout=_REDIS_EVAL_TIMEOUT_SECONDS)
                retry_after = max(ttl, 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Demasiadas solicitudes. Intente de nuevo en {retry_after} segundos.",
                    headers={"Retry-After": str(retry_after)},
                )
        except HTTPException:
            raise
        except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
            if fail_closed:
                _log.error("rate_limit.redis_eval_failed_fail_closed", path=request.url.path, error=str(exc))
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Servicio de limitación de tasa temporalmente no disponible.",
                ) from exc
            _log.warning("rate_limit.redis_eval_failed_bypassed", path=request.url.path, error=str(exc))
            return


class ProjectGenerationRateLimiter:
    _LUA_SCRIPT = """
        local key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local current = redis.call('INCR', key)
        if current == 1 then
            redis.call('EXPIRE', key, window)
        end
        return current
    """

    def __init__(self, requests_per_hour: int | None = None) -> None:
        self._limit = requests_per_hour

    async def __call__(self, request: Request, project_id: str = "") -> None:
        try:
            container = get_container(request)
        except Exception:
            app = getattr(request, "app", None)
            container = getattr(getattr(app, "state", None), "container", None)

        if container is None:
            return

        if not project_id:
            raw_path_params = getattr(request, "path_params", None)
            if isinstance(raw_path_params, dict):
                pid_val = cast(dict[str, Any], raw_path_params).get("project_id")
                if isinstance(pid_val, str) and pid_val:
                    project_id = pid_val
            if not project_id:
                state = getattr(request, "state", None)
                state_pid = getattr(state, "project_id", None)
                if isinstance(state_pid, str):
                    project_id = state_pid
        if not project_id:
            raw_path_params = getattr(request, "path_params", None)
            if isinstance(raw_path_params, dict):
                feat_val = cast(dict[str, Any], raw_path_params).get("feature_id")
                if isinstance(feat_val, str) and feat_val:
                    feature_id = feat_val
                    repos = getattr(container, "repos", None)
                    feature_repo = getattr(repos, "features", None)
                    if feature_repo is not None and hasattr(feature_repo, "by_id"):
                        with contextlib.suppress(Exception):
                            feature = await feature_repo.by_id(FeatureId(feature_id))
                            if feature is not None:
                                project_id = str(feature.project_id)
                                state = getattr(request, "state", None)
                                if state is not None:
                                    state.project_id = project_id
                    if not project_id:
                        project_id = f"feat_{feature_id}"

        if not project_id:
            project_id = "unknown"

        redis = cast(Any, getattr(container, "redis", None))
        fail_closed = _should_fail_closed(container)

        if redis is None:
            if fail_closed:
                _log.error("rate_limit.redis_unavailable_fail_closed", project_id=project_id)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Servicio de limitación de tasa no disponible.",
                )
            _log.warning("rate_limit.bypassed_no_redis", project_id=project_id)
            return

        limit = self._limit
        if limit is None:
            settings = getattr(container, "settings", None)
            raw_limit = getattr(settings, "generation_rate_limit_per_hour", None)
            limit = raw_limit if isinstance(raw_limit, int) and not isinstance(raw_limit, bool) else 120

        key = f"gen:rate:{project_id}"
        try:

            async def _run_eval() -> int | None:
                eval_res = redis.eval(self._LUA_SCRIPT, 1, key, str(limit), "3600")
                if inspect.isawaitable(eval_res):
                    eval_res = await eval_res
                try:
                    return int(eval_res)
                except (TypeError, ValueError):
                    return None

            count = await asyncio.wait_for(_run_eval(), timeout=_REDIS_EVAL_TIMEOUT_SECONDS)
            if count is None:
                return

            if count > limit:

                async def _run_ttl() -> int:
                    ttl_res = redis.ttl(key)
                    if inspect.isawaitable(ttl_res):
                        ttl_res = await ttl_res
                    try:
                        return int(ttl_res)
                    except (TypeError, ValueError):
                        return 60

                ttl = await asyncio.wait_for(_run_ttl(), timeout=_REDIS_EVAL_TIMEOUT_SECONDS)
                retry_after = max(ttl, 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Limite de generaciones excedido para el proyecto. Intente de nuevo en {retry_after} segundos."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )
        except HTTPException:
            raise
        except (RedisError, ConnectionError, TimeoutError, OSError) as exc:
            if fail_closed:
                _log.error("rate_limit.redis_eval_failed_fail_closed", project_id=project_id, error=str(exc))
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Servicio de limitación de tasa temporalmente no disponible.",
                ) from exc
            _log.warning("rate_limit.redis_eval_failed_bypassed", project_id=project_id, error=str(exc))
            return
