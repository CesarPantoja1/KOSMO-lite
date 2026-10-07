import asyncio
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from kosmo.infrastructure.api.dependencies.rate_limit import (  # noqa: E402
    IpRateLimiter,
    ProjectGenerationRateLimiter,
)


class _MockRedis:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        self._ttls[key] = seconds

    async def ttl(self, key: str) -> int:
        return self._ttls.get(key, -1)

    async def eval(self, script: str, numkeys: int, *args: str) -> int:
        key = args[0] if args else ""
        self._counts[key] = self._counts.get(key, 0) + 1
        if self._counts[key] == 1 and len(args) >= 3:
            self._ttls[key] = int(args[2])
        return self._counts[key]


def _build_app(limit: int) -> tuple[FastAPI, _MockRedis]:
    mock_redis = _MockRedis()
    limiter = IpRateLimiter(limit)
    app = FastAPI()
    app.state.container = SimpleNamespace(redis=mock_redis)

    @app.get("/probe", dependencies=[Depends(limiter)])
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    return app, mock_redis


@pytest.mark.unit
def test_requests_within_limit_are_allowed() -> None:
    app, _ = _build_app(3)
    with TestClient(app) as client:
        for _ in range(3):
            assert client.get("/probe").status_code == 200


@pytest.mark.unit
def test_request_exceeding_limit_returns_429() -> None:
    app, _ = _build_app(3)
    with TestClient(app) as client:
        for _ in range(3):
            client.get("/probe")
        response = client.get("/probe")
        assert response.status_code == 429


@pytest.mark.unit
def test_429_includes_retry_after_header() -> None:
    app, _ = _build_app(2)
    with TestClient(app) as client:
        for _ in range(2):
            client.get("/probe")
        response = client.get("/probe")
        assert "retry-after" in response.headers
        assert int(response.headers["retry-after"]) >= 1


@pytest.mark.unit
def test_429_error_message_is_in_spanish() -> None:
    app, _ = _build_app(1)
    with TestClient(app) as client:
        client.get("/probe")
        response = client.get("/probe")
        assert response.status_code == 429
        assert "Demasiadas solicitudes" in response.json()["detail"]
        assert "segundos" in response.json()["detail"]


@pytest.mark.unit
def test_rate_limiter_uses_the_proxy_supplied_client_ip() -> None:
    app, _ = _build_app(1)
    with TestClient(app) as client:
        assert client.get("/probe", headers={"X-Kosmo-Client-IP": "198.51.100.10"}).status_code == 200
        assert client.get("/probe", headers={"X-Kosmo-Client-IP": "198.51.100.11"}).status_code == 200
        assert client.get("/probe", headers={"X-Kosmo-Client-IP": "198.51.100.10"}).status_code == 429


@pytest.mark.unit
def test_rate_limiter_skips_when_redis_unavailable() -> None:
    limiter = IpRateLimiter(1)
    app = FastAPI()
    app.state.container = SimpleNamespace(redis=None)

    @app.get("/probe", dependencies=[Depends(limiter)])
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        for _ in range(5):
            assert client.get("/probe").status_code == 200


@pytest.mark.unit
def test_rate_limiter_fail_closed_when_redis_none_in_production() -> None:
    limiter = IpRateLimiter(1)
    app = FastAPI()
    app.state.container = SimpleNamespace(
        redis=None,
        settings=SimpleNamespace(env="production", rate_limit_required=False),
    )

    @app.get("/probe", dependencies=[Depends(limiter)])
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/probe")
        assert response.status_code == 503
        assert "no disponible" in response.json()["detail"]


@pytest.mark.unit
def test_rate_limiter_fail_closed_when_rate_limit_required() -> None:
    limiter = IpRateLimiter(1)
    app = FastAPI()
    app.state.container = SimpleNamespace(
        redis=None,
        settings=SimpleNamespace(env="development", rate_limit_required=True),
    )

    @app.get("/probe", dependencies=[Depends(limiter)])
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/probe")
        assert response.status_code == 503
        assert "no disponible" in response.json()["detail"]


@pytest.mark.unit
def test_rate_limiter_fail_closed_when_redis_raises_error_in_production() -> None:
    class _FailingRedis:
        async def eval(self, *args: object, **kwargs: object) -> int:
            raise RedisError("Connection refused")

    limiter = IpRateLimiter(1)
    app = FastAPI()
    app.state.container = SimpleNamespace(
        redis=_FailingRedis(),
        settings=SimpleNamespace(env="production", rate_limit_required=False),
    )

    @app.get("/probe", dependencies=[Depends(limiter)])
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/probe")
        assert response.status_code == 503
        assert "temporalmente no disponible" in response.json()["detail"]


@pytest.mark.unit
def test_project_generation_rate_limiter_fail_closed_in_production() -> None:
    limiter = ProjectGenerationRateLimiter(requests_per_hour=20)
    app = FastAPI()
    app.state.container = SimpleNamespace(
        redis=None,
        settings=SimpleNamespace(env="production", rate_limit_required=False),
    )

    @app.post("/projects/{project_id}/generate", dependencies=[Depends(limiter)])
    async def generate(project_id: str) -> dict[str, object]:
        return {"ok": True, "project_id": project_id}

    with TestClient(app) as client:
        response = client.post("/projects/prj_123/generate")
        assert response.status_code == 503
        assert "no disponible" in response.json()["detail"]


@pytest.mark.unit
def test_project_generation_rate_limiter_allows_in_dev_when_redis_none() -> None:
    limiter = ProjectGenerationRateLimiter(requests_per_hour=20)
    app = FastAPI()
    app.state.container = SimpleNamespace(
        redis=None,
        settings=SimpleNamespace(env="development", rate_limit_required=False),
    )

    @app.post("/projects/{project_id}/generate", dependencies=[Depends(limiter)])
    async def generate(project_id: str) -> dict[str, object]:
        return {"ok": True, "project_id": project_id}

    with TestClient(app) as client:
        response = client.post("/projects/prj_123/generate")
        assert response.status_code == 200


@pytest.mark.unit
def test_rate_limiter_rejects_spoofed_ip_from_untrusted_client() -> None:
    app, mock_redis = _build_app(1)
    # Untrusted client connecting directly from external public IP
    with TestClient(app, client=("203.0.113.195", 50000)) as client:
        # First request attempts to set spoofed IP 198.51.100.10
        res1 = client.get("/probe", headers={"X-Kosmo-Client-IP": "198.51.100.10"})
        assert res1.status_code == 200

        # Second request attempts to evade rate limit by changing spoofed IP to 198.51.100.99
        res2 = client.get("/probe", headers={"X-Kosmo-Client-IP": "198.51.100.99"})
        assert res2.status_code == 429

    # Verify keys in redis were tied to the socket host, not the spoofed headers
    assert "auth:ip_rate:/probe:203.0.113.195" in mock_redis._counts
    assert "auth:ip_rate:/probe:198.51.100.10" not in mock_redis._counts
    assert "auth:ip_rate:/probe:198.51.100.99" not in mock_redis._counts


@pytest.mark.unit
def test_rate_limiter_ignores_malformed_ip_from_trusted_proxy() -> None:
    app, mock_redis = _build_app(1)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        res = client.get("/probe", headers={"X-Kosmo-Client-IP": "invalid_ip_injection"})
        assert res.status_code == 200

    # Falls back safely to 127.0.0.1
    assert "auth:ip_rate:/probe:127.0.0.1" in mock_redis._counts
    assert "auth:ip_rate:/probe:invalid_ip_injection" not in mock_redis._counts


@pytest.mark.unit
def test_project_generation_rate_limiter_blocks_after_exceeding_limit() -> None:
    mock_redis = _MockRedis()
    limiter = ProjectGenerationRateLimiter(requests_per_hour=2)
    app = FastAPI()
    app.state.container = SimpleNamespace(redis=mock_redis, settings=SimpleNamespace())

    @app.post("/projects/{project_id}/generate", dependencies=[Depends(limiter)])
    async def generate(project_id: str) -> dict[str, str]:
        return {"project_id": project_id}

    with TestClient(app) as client:
        res1 = client.post("/projects/prj_1/generate")
        assert res1.status_code == 200

        res2 = client.post("/projects/prj_1/generate")
        assert res2.status_code == 200

        res3 = client.post("/projects/prj_1/generate")
        assert res3.status_code == 429
        assert "Retry-After" in res3.headers
        assert "Limite de generaciones excedido" in res3.json()["detail"]


@pytest.mark.unit
def test_project_generation_rate_limiter_uses_settings_default() -> None:
    mock_redis = _MockRedis()
    limiter = ProjectGenerationRateLimiter()
    app = FastAPI()
    app.state.container = SimpleNamespace(
        redis=mock_redis,
        settings=SimpleNamespace(generation_rate_limit_per_hour=1),
    )

    @app.post("/projects/{project_id}/generate", dependencies=[Depends(limiter)])
    async def generate(project_id: str) -> dict[str, str]:
        return {"project_id": project_id}

    with TestClient(app) as client:
        res1 = client.post("/projects/prj_1/generate")
        assert res1.status_code == 200

        res2 = client.post("/projects/prj_1/generate")
        assert res2.status_code == 429


@pytest.mark.unit
def test_project_generation_rate_limiter_resolves_feature_id() -> None:
    mock_redis = _MockRedis()
    limiter = ProjectGenerationRateLimiter(requests_per_hour=1)

    class _MockFeatureRepo:
        async def by_id(self, fid: object) -> object:
            return SimpleNamespace(project_id="prj_resolved_from_feature")

    app = FastAPI()
    app.state.container = SimpleNamespace(
        redis=mock_redis,
        settings=SimpleNamespace(),
        repos=SimpleNamespace(features=_MockFeatureRepo()),
    )

    @app.post("/features/{feature_id}/chat", dependencies=[Depends(limiter)])
    async def feature_chat(feature_id: str) -> dict[str, str]:
        return {"feature_id": feature_id}

    with TestClient(app) as client:
        res1 = client.post("/features/feat_abc/chat")
        assert res1.status_code == 200
        assert "gen:rate:prj_resolved_from_feature" in mock_redis._counts

        res2 = client.post("/features/feat_abc/chat")
        assert res2.status_code == 429


class _StallingRedis:
    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay

    async def eval(self, *args: object, **kwargs: object) -> int:
        await asyncio.sleep(self.delay)
        return 1

    async def ttl(self, *args: object, **kwargs: object) -> int:
        await asyncio.sleep(self.delay)
        return 60


@pytest.mark.unit
def test_ip_rate_limiter_timeout_in_eval_bypasses_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    import kosmo.infrastructure.api.dependencies.rate_limit as rl

    monkeypatch.setattr(rl, "_REDIS_EVAL_TIMEOUT_SECONDS", 0.01)

    limiter = IpRateLimiter(1)
    app = FastAPI()
    app.state.container = SimpleNamespace(
        redis=_StallingRedis(delay=0.05),
        settings=SimpleNamespace(env="development", rate_limit_required=False),
    )

    @app.get("/probe", dependencies=[Depends(limiter)])
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        res = client.get("/probe")
        assert res.status_code == 200


@pytest.mark.unit
def test_ip_rate_limiter_timeout_in_eval_fails_closed_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    import kosmo.infrastructure.api.dependencies.rate_limit as rl

    monkeypatch.setattr(rl, "_REDIS_EVAL_TIMEOUT_SECONDS", 0.01)

    limiter = IpRateLimiter(1)
    app = FastAPI()
    app.state.container = SimpleNamespace(
        redis=_StallingRedis(delay=0.05),
        settings=SimpleNamespace(env="production", rate_limit_required=False),
    )

    @app.get("/probe", dependencies=[Depends(limiter)])
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        res = client.get("/probe")
        assert res.status_code == 503
        assert "temporalmente no disponible" in res.json()["detail"]


@pytest.mark.unit
def test_project_generation_rate_limiter_timeout_bypasses_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    import kosmo.infrastructure.api.dependencies.rate_limit as rl

    monkeypatch.setattr(rl, "_REDIS_EVAL_TIMEOUT_SECONDS", 0.01)

    limiter = ProjectGenerationRateLimiter(requests_per_hour=1)
    app = FastAPI()
    app.state.container = SimpleNamespace(
        redis=_StallingRedis(delay=0.05),
        settings=SimpleNamespace(env="development", rate_limit_required=False),
    )

    @app.post("/projects/{project_id}/generate", dependencies=[Depends(limiter)])
    async def generate(project_id: str) -> dict[str, object]:
        return {"ok": True, "project_id": project_id}

    with TestClient(app) as client:
        res = client.post("/projects/prj_123/generate")
        assert res.status_code == 200


@pytest.mark.unit
def test_project_generation_rate_limiter_timeout_fails_closed_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    import kosmo.infrastructure.api.dependencies.rate_limit as rl

    monkeypatch.setattr(rl, "_REDIS_EVAL_TIMEOUT_SECONDS", 0.01)

    limiter = ProjectGenerationRateLimiter(requests_per_hour=1)
    app = FastAPI()
    app.state.container = SimpleNamespace(
        redis=_StallingRedis(delay=0.05),
        settings=SimpleNamespace(env="production", rate_limit_required=False),
    )

    @app.post("/projects/{project_id}/generate", dependencies=[Depends(limiter)])
    async def generate(project_id: str) -> dict[str, object]:
        return {"ok": True, "project_id": project_id}

    with TestClient(app) as client:
        res = client.post("/projects/prj_123/generate")
        assert res.status_code == 503
        assert "temporalmente no disponible" in res.json()["detail"]
