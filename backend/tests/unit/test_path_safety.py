from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from kosmo.domain.codegen.path_safety import (
    UnsafePathError,
    ensure_safe_path,
    is_safe_path,
    sanitize_relative_path,
    validate_safe_path,
)


@pytest.mark.unit
def test_validate_safe_path_accepts_valid_relative_paths() -> None:
    # Arrange
    root = "/tmp/workspace"
    safe_paths = [
        "src/index.ts",
        "tests/app.test.ts",
        "components/ui/button.tsx",
        "package.json",
        "README.md",
        "nested/deep/directory/file.ext",
    ]

    # Act & Assert
    for path in safe_paths:
        assert validate_safe_path(path, root) is True
        assert is_safe_path(path, root) is True


@pytest.mark.unit
def test_validate_safe_path_rejects_parent_traversal() -> None:
    # Arrange
    root = "/tmp/workspace"
    traversal_paths = [
        "../outside.txt",
        "../../etc/passwd",
        "src/../../outside.txt",
        "a/b/../../../c",
        "..",
        "../",
        r"..\outside.txt",
        r"src\..\..\outside.txt",
    ]

    # Act & Assert
    for path in traversal_paths:
        assert validate_safe_path(path, root) is False
        assert is_safe_path(path, root) is False


@pytest.mark.unit
def test_validate_safe_path_rejects_absolute_path_outside_root() -> None:
    # Arrange
    root = "/tmp/workspace"
    outside_paths = [
        "/etc/passwd",
        "/tmp/other_workspace/file.txt",
        "/var/log/syslog",
        "C:\\Windows\\System32\\cmd.exe",
        "D:\\data\\file.txt",
    ]

    # Act & Assert
    for path in outside_paths:
        assert validate_safe_path(path, root) is False


@pytest.mark.unit
def test_validate_safe_path_accepts_absolute_path_inside_root() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir).resolve()
        subfile = root / "src" / "index.ts"

        # Act & Assert
        assert validate_safe_path(str(subfile), root) is True
        assert validate_safe_path(subfile, root) is True


@pytest.mark.unit
def test_validate_safe_path_rejects_null_bytes_and_empty() -> None:
    # Arrange
    root = "/tmp/workspace"

    # Act & Assert
    assert validate_safe_path("src/\0index.ts", root) is False
    assert validate_safe_path("src/index.ts", "/tmp/\0workspace") is False
    assert validate_safe_path("", root) is False
    assert validate_safe_path("   ", root) is False
    assert validate_safe_path("src/index.ts", "") is False
    assert validate_safe_path("src/index.ts", "   ") is False


@pytest.mark.unit
def test_ensure_safe_path_success() -> None:
    # Arrange
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir).resolve()
        subfile = root / "src" / "app.ts"

        # Act
        safe_rel = ensure_safe_path("src/app.ts", root)
        safe_abs = ensure_safe_path(subfile, root)

        # Assert
        assert safe_rel.is_relative_to(root)
        assert safe_rel == root / "src" / "app.ts"
        assert safe_abs == subfile


@pytest.mark.unit
def test_ensure_safe_path_raises_on_unsafe_path() -> None:
    # Arrange
    root = "/tmp/workspace"
    unsafe_path = "../escaped.txt"

    # Act & Assert
    with pytest.raises(UnsafePathError) as exc_info:
        ensure_safe_path(unsafe_path, root)

    assert "escaped.txt" in str(exc_info.value)


@pytest.mark.unit
def test_sanitize_relative_path() -> None:
    # Arrange & Act & Assert
    assert sanitize_relative_path("src/components/Button.tsx") == "src/components/Button.tsx"
    assert sanitize_relative_path("src\\components\\Button.tsx") == "src/components/Button.tsx"
    assert sanitize_relative_path("./src/app.ts") == "src/app.ts"
    assert sanitize_relative_path("/src/app.ts") == "src/app.ts"
    assert sanitize_relative_path("  src/app.ts  ") == "src/app.ts"
    assert sanitize_relative_path("src//nested///file.ts") == "src/nested/file.ts"

    with pytest.raises(UnsafePathError):
        sanitize_relative_path("../outside.ts")

    with pytest.raises(UnsafePathError):
        sanitize_relative_path("src/../../outside.ts")

    with pytest.raises(UnsafePathError):
        sanitize_relative_path("")

    with pytest.raises(UnsafePathError):
        sanitize_relative_path("src/\0app.ts")

    with pytest.raises(UnsafePathError):
        sanitize_relative_path("././.")


@pytest.mark.property
@pytest.mark.unit
@given(
    st.lists(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
            min_size=1,
            max_size=10,
        ),
        min_size=1,
        max_size=5,
    )
)
def test_property_valid_alphanumeric_path_is_always_safe(parts: list[str]) -> None:
    # Arrange
    root = "/tmp/workspace"
    relative_path = "/".join(parts) + ".ts"

    # Act & Assert
    assert validate_safe_path(relative_path, root) is True


@pytest.mark.property
@pytest.mark.unit
@given(
    st.lists(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-",
            min_size=1,
            max_size=10,
        ),
        min_size=0,
        max_size=3,
    ),
    st.integers(min_value=1, max_value=4),
)
def test_property_path_with_dotdot_is_always_rejected(parts: list[str], dotdots: int) -> None:
    # Arrange
    root = "/tmp/workspace"
    traversal = [".."] * dotdots
    combined_parts = parts[: len(parts) // 2] + traversal + parts[len(parts) // 2 :]
    unsafe_path = "/".join(combined_parts) + "/target.ts"

    # Act & Assert
    assert validate_safe_path(unsafe_path, root) is False
