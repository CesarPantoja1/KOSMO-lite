from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx

from kosmo.contracts.sdd.codegen import ValidationRunResult, ValidationStep, ValidationStepResult
from kosmo.domain.codegen.parse_validation_output import parse_step_output


class RemoteCodeRunnerError(RuntimeError):
    """The isolated runner could not accept or execute a validation request."""


class RemoteCodeRunner:
    """Runs generated code in a separate container using an archive, never the shared volume."""

    def __init__(self, base_url: str, token: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._client = client or httpx.AsyncClient(base_url=self._base_url, timeout=httpx.Timeout(900, connect=10))
        self._owns_client = client is None

    @staticmethod
    def _archive_workspace(workspace_dir: str) -> str:
        root = Path(workspace_dir).resolve()
        if not root.is_dir():
            raise RemoteCodeRunnerError(f"Workspace does not exist: {workspace_dir}")
        output = io.BytesIO()
        ignored = {"node_modules", ".git", ".next", ".turbo", "coverage"}
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for path in root.rglob("*"):
                relative = path.relative_to(root)
                if any(part in ignored for part in relative.parts):
                    continue
                if path.is_file() and not path.is_symlink():
                    archive.add(path, arcname=str(relative).replace("\\", "/"), recursive=False)
        return base64.b64encode(output.getvalue()).decode("ascii")

    async def _run(self, workspace_dir: str, payload: dict[str, object]) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        payload["archive"] = await loop.run_in_executor(None, self._archive_workspace, workspace_dir)
        response = await self._client.post("/run", json=payload, headers={"Authorization": f"Bearer {self._token}"})
        if not response.is_success:
            raise RemoteCodeRunnerError(f"Runner returned HTTP {response.status_code}: {response.text[:500]}")
        data = response.json()
        if not isinstance(data, dict):
            raise RemoteCodeRunnerError("Runner returned an invalid response")
        return cast(dict[str, Any], data)

    @staticmethod
    def _result(raw: dict[str, Any], step: ValidationStep) -> ValidationStepResult:
        output = str(raw.get("output", ""))
        exit_code = int(raw.get("exit_code", 1))
        duration_ms = int(raw.get("duration_ms", 0))
        return parse_step_output(step, output, exit_code, duration_ms)

    @staticmethod
    def _persist_package_lock(workspace_dir: str, manifest_before: bytes, package_lock: str) -> None:
        if len(package_lock.encode("utf-8")) > 5_000_000:
            raise RemoteCodeRunnerError("Generated package-lock.json is too large")
        workspace = Path(workspace_dir).resolve()
        manifest_path = workspace / "package.json"
        if manifest_path.read_bytes() != manifest_before:
            raise RemoteCodeRunnerError("package.json changed during isolated validation")
        try:
            package_raw: object = json.loads(manifest_before)
            lock_raw: object = json.loads(package_lock)
            if not isinstance(package_raw, dict) or not isinstance(lock_raw, dict):
                raise ValueError("Invalid package or lockfile")
            package = cast(dict[str, Any], package_raw)
            lock = cast(dict[str, Any], lock_raw)
            packages_raw: object = lock.get("packages")
            if not isinstance(packages_raw, dict):
                raise ValueError("Missing lockfile root")
            packages = cast(dict[str, object], packages_raw)
            root_raw = packages.get("")
            if not isinstance(root_raw, dict):
                raise ValueError("Missing lockfile root")
            root = cast(dict[str, Any], root_raw)
            version: object = lock.get("lockfileVersion")
            if not isinstance(version, int) or version < 2:
                raise ValueError("Unsupported lockfile format")
            for field in ("name", "version"):
                if root.get(field) != package.get(field):
                    raise ValueError(f"Lockfile does not match package.json: {field}")
            for field in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
                if root.get(field, {}) != package.get(field, {}):
                    raise ValueError(f"Lockfile does not match package.json: {field}")
        except (KeyError, TypeError, ValueError) as exc:
            raise RemoteCodeRunnerError("Generated package-lock.json does not match package.json") from exc

        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=workspace, delete=False) as temporary:
                temporary_path = temporary.name
                temporary.write(package_lock)
            os.replace(temporary_path, workspace / "package-lock.json")
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)

    async def run_step(
        self, workspace_dir: str, step: ValidationStep, *, timeout_seconds: int = 300
    ) -> ValidationStepResult:
        data = await self._run(
            workspace_dir, {"operation": "step", "step": str(step), "timeout_seconds": timeout_seconds}
        )
        return self._result(cast(dict[str, Any], data["result"]), step)

    async def run_command(
        self, workspace_dir: str, command: str, *, timeout_seconds: int = 300
    ) -> ValidationStepResult:
        data = await self._run(
            workspace_dir, {"operation": "command", "command": command, "timeout_seconds": timeout_seconds}
        )
        return self._result(cast(dict[str, Any], data["result"]), ValidationStep.TESTS)

    async def run_pipeline(
        self,
        workspace_dir: str,
        steps: tuple[ValidationStep, ...] = (
            ValidationStep.TYPECHECK,
            ValidationStep.LINT,
            ValidationStep.TESTS,
            ValidationStep.BUILD,
        ),
        run_id: str = "",
    ) -> ValidationRunResult:
        manifest_before = (Path(workspace_dir).resolve() / "package.json").read_bytes()
        data = await self._run(
            workspace_dir, {"operation": "pipeline", "steps": [str(step) for step in steps], "run_id": run_id}
        )
        package_lock = data.get("package_lock")
        if isinstance(package_lock, str):
            self._persist_package_lock(workspace_dir, manifest_before, package_lock)
        elif data.get("all_passed"):
            raise RemoteCodeRunnerError("Runner did not return the generated package-lock.json")
        results = tuple(
            self._result(item, ValidationStep(str(item["step"])))
            for item in cast(list[dict[str, Any]], data.get("results", []))
        )
        errors = tuple(str(error) for error in cast(list[object], data.get("error_summary", [])))
        return ValidationRunResult(
            steps=results,
            all_passed=bool(data.get("all_passed")),
            total_duration_ms=sum(result.duration_ms for result in results),
            executed_at=datetime.now(UTC),
            error_summary=errors,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
