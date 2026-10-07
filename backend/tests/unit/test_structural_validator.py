from __future__ import annotations

from pathlib import Path

import pytest

from kosmo.contracts.sdd.codegen import FileSystemReader
from kosmo.domain.codegen.structural_validator import (
    StructuralValidationResult,
    validate_feature_structure,
    validate_workspace_feature_structure,
)


@pytest.mark.unit
def test_validate_feature_structure_all_present() -> None:
    # Arrange
    slug = "registrar-gastos"
    files = [
        "src/app/registrar-gastos/page.tsx",
        "src/features/registrar-gastos/manifest.ts",
        "src/features/registrar-gastos/logic.ts",
        "src/lib/feature-registry.ts",
    ]
    registry_content = (
        'import { gastosManifest } from "@/features/registrar-gastos/manifest";\n'
        "export const featureRegistry = [gastosManifest];\n"
    )

    # Act
    result = validate_feature_structure(
        feature_slug=slug,
        files=files,
        registry_content=registry_content,
    )

    # Assert
    assert isinstance(result, StructuralValidationResult)
    assert result.is_valid is True
    assert len(result.errors) == 0
    assert result.missing_page is False
    assert result.missing_slice is False
    assert result.missing_registry is False


@pytest.mark.unit
def test_validate_feature_structure_missing_page() -> None:
    # Arrange
    slug = "registrar-gastos"
    files = [
        "src/features/registrar-gastos/manifest.ts",
        "src/features/registrar-gastos/logic.ts",
        "src/lib/feature-registry.ts",
    ]
    registry_content = 'import { gastosManifest } from "@/features/registrar-gastos/manifest";\n'

    # Act
    result = validate_feature_structure(
        feature_slug=slug,
        files=files,
        registry_content=registry_content,
    )

    # Assert
    assert result.is_valid is False
    assert result.missing_page is True
    assert result.missing_slice is False
    assert result.missing_registry is False
    assert any("page.tsx" in err for err in result.errors)


@pytest.mark.unit
def test_validate_feature_structure_missing_slice() -> None:
    # Arrange
    slug = "registrar-gastos"
    files = [
        "src/app/registrar-gastos/page.tsx",
        "src/lib/feature-registry.ts",
    ]
    registry_content = 'import { gastosManifest } from "@/features/registrar-gastos/manifest";\n'

    # Act
    result = validate_feature_structure(
        feature_slug=slug,
        files=files,
        registry_content=registry_content,
    )

    # Assert
    assert result.is_valid is False
    assert result.missing_page is False
    assert result.missing_slice is True
    assert result.missing_registry is False
    assert any("src/features/registrar-gastos/" in err for err in result.errors)


@pytest.mark.unit
def test_validate_feature_structure_missing_registry() -> None:
    # Arrange
    slug = "registrar-gastos"
    files = [
        "src/app/registrar-gastos/page.tsx",
        "src/features/registrar-gastos/manifest.ts",
        "src/lib/feature-registry.ts",
    ]
    registry_content = "export const featureRegistry = [];\n"

    # Act
    result = validate_feature_structure(
        feature_slug=slug,
        files=files,
        registry_content=registry_content,
    )

    # Assert
    assert result.is_valid is False
    assert result.missing_page is False
    assert result.missing_slice is False
    assert result.missing_registry is True
    assert any("feature-registry.ts" in err for err in result.errors)


@pytest.mark.unit
def test_validate_feature_structure_missing_all() -> None:
    # Arrange
    slug = "registrar-gastos"
    files = ["src/other.ts"]
    registry_content = ""

    # Act
    result = validate_feature_structure(
        feature_slug=slug,
        files=files,
        registry_content=registry_content,
    )

    # Assert
    assert result.is_valid is False
    assert result.missing_page is True
    assert result.missing_slice is True
    assert result.missing_registry is True
    assert len(result.errors) == 3


@pytest.mark.unit
def test_validate_feature_structure_handles_windows_separators() -> None:
    # Arrange
    slug = "reportes-mensuales"
    files = [
        r"src\app\reportes-mensuales\page.tsx",
        r"src\features\reportes-mensuales\components\Chart.tsx",
        r"src\lib\feature-registry.ts",
    ]
    registry_content = 'import { reportes } from "@/features/reportes-mensuales/manifest";'

    # Act
    result = validate_feature_structure(
        feature_slug=slug,
        files=files,
        registry_content=registry_content,
    )

    # Assert
    assert result.is_valid is True
    assert result.missing_page is False
    assert result.missing_slice is False
    assert result.missing_registry is False


@pytest.mark.unit
def test_validate_feature_structure_missing_export_default() -> None:
    # Arrange
    slug = "registrar-gastos"
    files = [
        "src/app/registrar-gastos/page.tsx",
        "src/features/registrar-gastos/manifest.ts",
        "src/features/registrar-gastos/logic.ts",
        "src/lib/feature-registry.ts",
    ]
    registry_content = 'import { gastosManifest } from "@/features/registrar-gastos/manifest";\n'
    page_content = "export function Page() { return <div>Gastos</div>; }"

    # Act
    result = validate_feature_structure(
        feature_slug=slug,
        files=files,
        registry_content=registry_content,
        page_content=page_content,
    )

    # Assert
    assert result.is_valid is False
    assert result.missing_page is True
    assert any("export default" in err for err in result.errors)


@pytest.mark.unit
def test_validate_feature_structure_with_valid_export_default() -> None:
    # Arrange
    slug = "registrar-gastos"
    files = [
        "src/app/registrar-gastos/page.tsx",
        "src/features/registrar-gastos/manifest.ts",
        "src/features/registrar-gastos/logic.ts",
        "src/lib/feature-registry.ts",
    ]
    registry_content = 'import { gastosManifest } from "@/features/registrar-gastos/manifest";\n'
    page_content = "export default function GastosPage() { return <div>Gastos</div>; }"

    # Act
    result = validate_feature_structure(
        feature_slug=slug,
        files=files,
        registry_content=registry_content,
        page_content=page_content,
    )

    # Assert
    assert result.is_valid is True
    assert result.missing_page is False
    assert len(result.errors) == 0


class FakeFileSystemReader(FileSystemReader):
    """Lector de sistema de archivos completamente en memoria para tests de dominio puros."""

    def __init__(self, files: dict[str, str] | None = None) -> None:
        self._files: dict[str, str] = files or {}

    def list_files(self, root: str | Path) -> tuple[str, ...]:
        return tuple(self._files.keys())

    def read_text(self, path: str | Path) -> str | None:
        norm = str(path).replace("\\", "/").strip("./")
        for key, val in self._files.items():
            norm_key = key.replace("\\", "/").strip("./")
            if norm == norm_key or norm.endswith(f"/{norm_key}"):
                return val
        return None


@pytest.mark.unit
def test_validate_workspace_feature_structure_pure_with_fake_reader() -> None:
    # Arrange — estructura completa puramente en memoria, sin tocar disco
    slug = "auth-login"
    fake_fs = FakeFileSystemReader(
        {
            "src/app/auth-login/page.tsx": "export default function LoginPage() { return <div />; }",
            "src/features/auth-login/components/LoginForm.tsx": "export const LoginForm = () => null;",
            "src/lib/feature-registry.ts": "export const featureRegistry = ['auth-login'];",
        }
    )

    # Act
    result = validate_workspace_feature_structure(
        workspace_dir="/virtual/workspace",
        feature_slug=slug,
        fs_reader=fake_fs,
    )

    # Assert
    assert isinstance(result, StructuralValidationResult)
    assert result.is_valid is True
    assert len(result.errors) == 0
    assert result.missing_page is False
    assert result.missing_slice is False
    assert result.missing_registry is False


@pytest.mark.unit
def test_validate_workspace_feature_structure_missing_page_with_fake_reader() -> None:
    # Arrange — falta page.tsx
    slug = "auth-login"
    fake_fs = FakeFileSystemReader(
        {
            "src/features/auth-login/components/LoginForm.tsx": "export const LoginForm = () => null;",
            "src/lib/feature-registry.ts": "export const featureRegistry = ['auth-login'];",
        }
    )

    # Act
    result = validate_workspace_feature_structure(
        workspace_dir="/virtual/workspace",
        feature_slug=slug,
        fs_reader=fake_fs,
    )

    # Assert
    assert result.is_valid is False
    assert result.missing_page is True
    assert any("page.tsx" in err for err in result.errors)


@pytest.mark.unit
def test_validate_workspace_feature_structure_missing_slice_with_fake_reader() -> None:
    # Arrange — falta el slice de la feature
    slug = "auth-login"
    fake_fs = FakeFileSystemReader(
        {
            "src/app/auth-login/page.tsx": "export default function LoginPage() { return <div />; }",
            "src/lib/feature-registry.ts": "export const featureRegistry = ['auth-login'];",
        }
    )

    # Act
    result = validate_workspace_feature_structure(
        workspace_dir="/virtual/workspace",
        feature_slug=slug,
        fs_reader=fake_fs,
    )

    # Assert
    assert result.is_valid is False
    assert result.missing_slice is True
    assert any("src/features/auth-login/" in err for err in result.errors)


@pytest.mark.unit
def test_validate_workspace_feature_structure_missing_export_default_with_fake_reader() -> None:
    # Arrange — page.tsx sin export default
    slug = "auth-login"
    fake_fs = FakeFileSystemReader(
        {
            "src/app/auth-login/page.tsx": "export function LoginPage() { return <div />; }",
            "src/features/auth-login/components/LoginForm.tsx": "export const LoginForm = () => null;",
            "src/lib/feature-registry.ts": "export const featureRegistry = ['auth-login'];",
        }
    )

    # Act
    result = validate_workspace_feature_structure(
        workspace_dir="/virtual/workspace",
        feature_slug=slug,
        fs_reader=fake_fs,
    )

    # Assert
    assert result.is_valid is False
    assert result.missing_page is True
    assert any("export default" in err for err in result.errors)


@pytest.mark.unit
def test_validate_workspace_feature_structure_with_extra_files_combined() -> None:
    # Arrange — archivos provistos vía extra_files combinados con fs_reader
    slug = "auth-login"
    fake_fs = FakeFileSystemReader(
        {
            "src/app/auth-login/page.tsx": "export default function LoginPage() { return <div />; }",
            "src/lib/feature-registry.ts": "export const featureRegistry = ['auth-login'];",
        }
    )
    extra = ["src/features/auth-login/extra_component.tsx"]

    # Act
    result = validate_workspace_feature_structure(
        workspace_dir="/virtual/workspace",
        feature_slug=slug,
        fs_reader=fake_fs,
        extra_files=extra,
    )

    # Assert
    assert result.is_valid is True
    assert result.missing_slice is False


@pytest.mark.unit
def test_validate_feature_structure_disposition_skip() -> None:
    # Arrange — feature omitida porque ya fue satisfecha
    slug = "aceptar-terminos"
    files: list[str] = []

    # Act
    result = validate_feature_structure(
        feature_slug=slug,
        files=files,
        disposition="skip",
    )

    # Assert
    assert result.is_valid is True
    assert len(result.errors) == 0


@pytest.mark.unit
def test_validate_feature_structure_disposition_integrate_with_domain() -> None:
    # Arrange — sub-capacidad que aporta componente a src/domain/ sin página propia
    slug = "aceptar-terminos"
    files = ["src/domain/terms/accept-terms.tsx"]

    # Act
    result = validate_feature_structure(
        feature_slug=slug,
        files=files,
        disposition="integrate",
    )

    # Assert
    assert result.is_valid is True
    assert len(result.errors) == 0


@pytest.mark.unit
def test_validate_feature_structure_disposition_integrate_no_files() -> None:
    # Arrange — sub-capacidad que no generó ningún archivo
    slug = "aceptar-terminos"
    files = ["src/other.ts"]

    # Act
    result = validate_feature_structure(
        feature_slug=slug,
        files=files,
        disposition="integrate",
    )

    # Assert
    assert result.is_valid is False
    assert result.missing_slice is True
    assert any("sub-capacidad" in err for err in result.errors)
