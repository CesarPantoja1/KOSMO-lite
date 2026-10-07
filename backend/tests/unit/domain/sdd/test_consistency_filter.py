from __future__ import annotations

import pytest

from kosmo.contracts.ai.chat import AppliedChange, DiffCambio
from kosmo.contracts.pipeline.consistency_phase_context import DownstreamArtifact
from kosmo.domain.sdd.consistency_filter import (
    extract_key_terms,
    filter_downstream_artifacts,
)


def _change(description: str, before: str, after: str) -> AppliedChange:
    return AppliedChange(
        id="chg_01",
        section="Alcance",
        description=description,
        diff=DiffCambio(before=before, after=after),
    )


def _artifact(artifact_id: str, title: str, description: str) -> DownstreamArtifact:
    return DownstreamArtifact(
        artifact_id=artifact_id,
        artifact_type="Feature",
        title=title,
        description=description,
    )


@pytest.mark.unit
def test_extract_key_terms_ignores_stopwords_and_short_tokens() -> None:
    # Arrange
    change = _change(
        "Cambio de alcance",
        "El sistema tendrá el producto X",
        "El sistema ya no tendrá el producto X",
    )

    # Act
    terms = extract_key_terms([change])

    # Assert
    assert "producto" in terms
    assert "sistema" in terms
    assert "el" not in terms
    assert "ya" not in terms
    assert "x" not in terms


@pytest.mark.unit
def test_filter_keeps_only_artifacts_mentioning_change_terms() -> None:
    # Arrange
    change = _change("Cambio de alcance", "se elimina el producto X", "se elimina el producto Y")
    artifacts = [
        _artifact("feat_a", "Registro de productos", "Descripción con el producto X."),
        _artifact("feat_b", "Gestión de pagos", "Descripción de pagos."),
    ]

    # Act
    result = filter_downstream_artifacts(artifacts, [change])

    # Assert
    assert [a.artifact_id for a in result] == ["feat_a"]


@pytest.mark.unit
def test_filter_falls_back_to_all_when_nothing_matches() -> None:
    # Arrange
    change = _change("Cambio de alcance", "termino raro zzz", "otro termino raro")
    artifacts = [
        _artifact("feat_a", "Registro de productos", "Descripción A."),
        _artifact("feat_b", "Gestión de pagos", "Descripción B."),
    ]

    # Act
    result = filter_downstream_artifacts(artifacts, [change])

    # Assert
    assert len(result) == 2


@pytest.mark.unit
def test_filter_falls_back_to_all_when_no_terms_extracted() -> None:
    # Arrange: solo stopwords y tokens cortos
    change = _change("el ya", "no es su", "de un")
    artifacts = [_artifact("feat_a", "Registro de productos", "Descripción A.")]

    # Act
    result = filter_downstream_artifacts(artifacts, [change])

    # Assert
    assert len(result) == 1


@pytest.mark.unit
def test_filter_finds_artifacts_when_actor_is_renamed() -> None:
    change = _change(
        "Cambio en Actores",
        before="### Actores\n- Administrador: Gestiona la plataforma.",
        after="### Actores\n- Jefe: Gestiona la plataforma.",
    )
    artifacts = [
        _artifact("feat_01", "Panel de Control", "Permite al Administrador gestionar usuarios."),
        _artifact("feat_02", "Catálogo de Productos", "Permite ver productos a clientes."),
    ]

    result = filter_downstream_artifacts(artifacts, [change])

    # feat_01 menciona al actor anterior (Administrador) y debe ser seleccionada
    assert any(a.artifact_id == "feat_01" for a in result)


@pytest.mark.unit
def test_extract_key_terms_includes_two_and_three_char_tokens() -> None:
    change = _change("Cambio de rol y UI", before="ui admin rol", after="ui jefe rol")
    terms = extract_key_terms([change])

    assert "ui" in terms
    assert "rol" in terms
