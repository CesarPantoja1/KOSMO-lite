import importlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

app = importlib.import_module("kosmo.infrastructure.api.main").app


@pytest.mark.unit
def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class _Connection:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def execute(self, _statement) -> None:
        return None


class _Engine:
    def connect(self) -> _Connection:
        return _Connection()


class _Redis:
    async def ping(self) -> bool:
        return True


@pytest.mark.unit
def test_readiness_checks_database_and_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        app.state,
        "container",
        SimpleNamespace(db_engine=_Engine(), redis=_Redis()),
        raising=False,
    )

    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "pool" in data
    assert "broker" in data


class _Pool:
    def size(self) -> int:
        return 35

    def checkedin(self) -> int:
        return 30

    def checkedout(self) -> int:
        return 5

    def overflow(self) -> int:
        return 2


class _EngineWithPool(_Engine):
    def __init__(self) -> None:
        self.pool = _Pool()


class _BrokerWithRedis:
    def __init__(self) -> None:
        self._redis = object()


@pytest.mark.unit
def test_readiness_exposes_pool_saturation_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        app.state,
        "container",
        SimpleNamespace(
            db_engine=_EngineWithPool(),
            redis=_Redis(),
            codegen=SimpleNamespace(implementation_broker=_BrokerWithRedis()),
        ),
        raising=False,
    )

    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["pool"] == {
        "size": 35,
        "checked_in": 30,
        "checked_out": 5,
        "overflow": 2,
    }
    assert data["broker"] == {
        "type": "redis",
        "status": "connected",
    }


@pytest.mark.unit
def test_readiness_returns_503_when_a_dependency_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        app.state,
        "container",
        SimpleNamespace(db_engine=SimpleNamespace(connect=lambda: (_ for _ in ()).throw(RuntimeError())), redis=None),
        raising=False,
    )

    response = TestClient(app).get("/ready")

    assert response.status_code == 503
