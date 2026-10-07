import pytest

from kosmo.domain.sdd.discovery_diff import ChangeClass, ChangeType, SectionChange
from kosmo.domain.sdd.plan_diffs import apply_change_diff, merge_changes_with_diffs


@pytest.mark.unit
def test_replace_when_before_found() -> None:
    result = apply_change_diff("Hola mundo", before="Hola", after="Adiós")

    assert result == "Adiós mundo"


@pytest.mark.unit
def test_replace_first_occurrence_only() -> None:
    result = apply_change_diff("Hola Hola mundo", before="Hola", after="X")

    assert result == "X Hola mundo"


@pytest.mark.unit
def test_append_when_before_empty() -> None:
    result = apply_change_diff("Línea 1", before="", after="Línea 2")

    assert result == "Línea 1\n\nLínea 2"


@pytest.mark.unit
def test_append_when_before_whitespace_only() -> None:
    result = apply_change_diff("Línea 1", before="   ", after="Línea 2")

    assert result == "Línea 1\n\nLínea 2"


@pytest.mark.unit
def test_unchanged_when_after_also_empty() -> None:
    result = apply_change_diff("Línea 1", before="", after="")

    assert result == "Línea 1"


@pytest.mark.unit
def test_none_when_before_not_found() -> None:
    result = apply_change_diff("Hola mundo", before="xyz", after="abc")

    assert result is None


@pytest.mark.unit
def test_replace_with_multiline() -> None:
    markdown = "## Título\n\nContenido original aquí.\n\n## Otra sección"
    result = apply_change_diff(markdown, before="Contenido original aquí.", after="Contenido modificado.")

    assert result is not None
    assert "Contenido modificado." in result
    assert "Contenido original aquí." not in result
    assert "## Título" in result
    assert "## Otra sección" in result


@pytest.mark.unit
def test_merge_changes_with_diffs_propagates_change_class() -> None:
    # Arrange
    cosmetic = SectionChange(
        section="Visión",
        change_type=ChangeType.MODIFIED,
        change_class=ChangeClass.COSMETIC,
        before="Visión original.",
        after="Visión  original.",
    )

    # Act
    result = merge_changes_with_diffs([], [cosmetic])

    # Assert
    assert len(result) == 1
    assert result[0].change_class == "cosmetic"


@pytest.mark.unit
def test_append_to_empty_markdown() -> None:
    result = apply_change_diff("", before="", after="Nueva sección")

    assert result == "\n\nNueva sección"


@pytest.mark.unit
def test_replace_with_crlf_newlines() -> None:
    text_crlf = "## Actores\r\n\r\n- Administrador: Gestiona.\r\n"
    result = apply_change_diff(text_crlf, before="- Administrador: Gestiona.\n", after="- Jefe: Gestiona.\n")

    assert result is not None
    assert "Jefe: Gestiona." in result
    assert "Administrador" not in result


@pytest.mark.unit
def test_delete_with_leading_and_trailing_newlines() -> None:
    markdown = "## Actores\n\n- Administrador: Gestiona el sistema.\n- Operador: Opera.\n"
    # El LLM genera diff para eliminar con saltos de línea en bordes
    result = apply_change_diff(markdown, before="\n- Administrador: Gestiona el sistema.\n", after="")

    assert result is not None
    assert "Administrador" not in result
    assert "- Operador: Opera." in result
    # Debe ser diferente al original (eliminación exitosa)
    assert result != markdown


@pytest.mark.unit
def test_delete_does_not_falsely_succeed_with_empty_after_when_before_missing() -> None:
    markdown = "## Actores\n\n- Empleado: Trabaja aquí.\n"
    # Si before no existe en absoluto, debe retornar None y NO markdown
    result = apply_change_diff(markdown, before="Inexistente", after="")

    assert result is None


@pytest.mark.unit
def test_idempotency_does_not_trigger_when_before_still_in_text() -> None:
    markdown = "## Actores\n- Administrador\n- Jefe\n"
    result = apply_change_diff(markdown, before="- Administrador", after="- SuperJefe")

    assert result is not None
    assert "- SuperJefe" in result
    assert "- Administrador" not in result
