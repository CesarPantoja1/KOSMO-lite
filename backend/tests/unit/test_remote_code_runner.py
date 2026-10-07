from __future__ import annotations

import json

import httpx
import pytest

from kosmo.infrastructure.sandbox.remote_code_runner import RemoteCodeRunner, RemoteCodeRunnerError


def _package_and_lock() -> tuple[dict[str, object], str]:
    package: dict[str, object] = {
        "name": "generated-app",
        "version": "0.1.0",
        "dependencies": {"react": "^19.0.0"},
    }
    lock = json.dumps(
        {
            "name": "generated-app",
            "version": "0.1.0",
            "lockfileVersion": 3,
            "packages": {"": package},
        }
    )
    return package, lock


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remote_pipeline_persists_generated_lockfile(tmp_path) -> None:
    package, lock = _package_and_lock()
    (tmp_path / "package.json").write_text(json.dumps(package), encoding="utf-8")

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-token"
        assert json.loads(request.content)["operation"] == "pipeline"
        return httpx.Response(200, json={"all_passed": True, "results": [], "package_lock": lock})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://runner") as client:
        runner = RemoteCodeRunner("http://runner", "test-token", client=client)
        result = await runner.run_pipeline(str(tmp_path), steps=())

    assert result.all_passed
    assert (tmp_path / "package-lock.json").read_text(encoding="utf-8") == lock


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remote_pipeline_rejects_lockfile_for_different_dependencies(tmp_path) -> None:
    package, lock = _package_and_lock()
    (tmp_path / "package.json").write_text(json.dumps(package), encoding="utf-8")
    invalid_lock = lock.replace("^19.0.0", "^18.0.0")

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"all_passed": True, "results": [], "package_lock": invalid_lock})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://runner") as client:
        runner = RemoteCodeRunner("http://runner", "test-token", client=client)
        with pytest.raises(RemoteCodeRunnerError, match="does not match"):
            await runner.run_pipeline(str(tmp_path), steps=())

    assert not (tmp_path / "package-lock.json").exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remote_pipeline_rejects_changed_manifest(tmp_path) -> None:
    package, lock = _package_and_lock()
    manifest = tmp_path / "package.json"
    manifest.write_text(json.dumps(package), encoding="utf-8")

    def respond(_request: httpx.Request) -> httpx.Response:
        manifest.write_text(json.dumps({**package, "version": "0.2.0"}), encoding="utf-8")
        return httpx.Response(200, json={"all_passed": True, "results": [], "package_lock": lock})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://runner") as client:
        runner = RemoteCodeRunner("http://runner", "test-token", client=client)
        with pytest.raises(RemoteCodeRunnerError, match="changed during"):
            await runner.run_pipeline(str(tmp_path), steps=())

    assert not (tmp_path / "package-lock.json").exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_remote_pipeline_rejects_success_without_lockfile(tmp_path) -> None:
    package, _lock = _package_and_lock()
    (tmp_path / "package.json").write_text(json.dumps(package), encoding="utf-8")

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"all_passed": True, "results": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url="http://runner") as client:
        runner = RemoteCodeRunner("http://runner", "test-token", client=client)
        with pytest.raises(RemoteCodeRunnerError, match="did not return"):
            await runner.run_pipeline(str(tmp_path), steps=())
