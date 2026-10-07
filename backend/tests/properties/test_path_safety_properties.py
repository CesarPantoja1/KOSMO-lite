from __future__ import annotations

import os
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from kosmo.domain.codegen.path_safety import (
    UnsafePathError,
    ensure_safe_path,
    sanitize_relative_path,
    validate_safe_path,
)

_WORKSPACE_ROOT = Path("C:/kosmo_test/workspace") if os.name == "nt" else Path("/kosmo_test/workspace")
_VALID_PATH_CHARS = st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_-")
_VALID_NAME = st.text(_VALID_PATH_CHARS, min_size=1, max_size=20)


@pytest.mark.property
@settings(max_examples=60)
@given(st.text(), st.text())
def test_validate_safe_path_is_total_function(raw_path: str, raw_root: str) -> None:
    """Propiedad: validate_safe_path nunca debe lanzar excepciones no controladas ante texto arbitrario."""
    result = validate_safe_path(raw_path, raw_root)
    assert isinstance(result, bool)


@pytest.mark.property
@settings(max_examples=50)
@given(st.lists(_VALID_NAME, min_size=1, max_size=5))
def test_valid_relative_paths_always_resolve_inside_root(segments: list[str]) -> None:
    """Propiedad: toda ruta construida con nombres válidos queda estrictamente contenida en el root."""
    rel_path = "/".join(segments)
    root = _WORKSPACE_ROOT

    assert validate_safe_path(rel_path, root) is True
    resolved = ensure_safe_path(rel_path, root)
    assert resolved.is_relative_to(root.resolve())


@pytest.mark.property
@settings(max_examples=50)
@given(st.lists(_VALID_NAME, min_size=1, max_size=3), st.sampled_from(["..", "../..", "..\\.."]))
def test_directory_traversal_is_strictly_rejected(
    segments: list[str],
    traversal: str,
) -> None:
    """Propiedad: cualquier ruta que incluya secuencias de salto hacia arriba debe ser rechazada."""
    root = _WORKSPACE_ROOT
    malicious_path = f"{traversal}/{'/'.join(segments)}"

    assert validate_safe_path(malicious_path, root) is False
    with pytest.raises(UnsafePathError):
        ensure_safe_path(malicious_path, root)


@pytest.mark.property
@settings(max_examples=40)
@given(st.text(min_size=1, max_size=20), st.text(min_size=1, max_size=20))
def test_null_byte_injections_are_strictly_rejected(prefix: str, suffix: str) -> None:
    """Propiedad: cualquier byte nulo (\0) en la ruta o en el root debe ser rechazado sin excepción inesperada."""
    path_with_null = f"{prefix}\0{suffix}"
    assert validate_safe_path(path_with_null, _WORKSPACE_ROOT) is False
    with pytest.raises(UnsafePathError):
        ensure_safe_path(path_with_null, _WORKSPACE_ROOT)


@pytest.mark.property
@settings(max_examples=50)
@given(st.lists(_VALID_NAME, min_size=1, max_size=4))
def test_sanitize_relative_path_invariants(segments: list[str]) -> None:
    """Propiedad: sanitize_relative_path produce rutas limpias con barras normales y sin saltos."""
    raw = f"///./{'//'.join(segments)}"
    sanitized = sanitize_relative_path(raw)

    assert "\\" not in sanitized
    assert "//" not in sanitized
    assert not sanitized.startswith("/")
    assert not sanitized.startswith("./")
    assert ".." not in sanitized.split("/")
