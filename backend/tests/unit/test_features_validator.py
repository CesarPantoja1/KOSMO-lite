import pytest

from kosmo.domain.pipeline.phase_validators.features_validator import (
    validate_feature_structure,
    validate_feature_uniqueness,
)


def _a_valid_feature(
    number: int = 1,
    title: str = "Registrar gastos entre participantes",
    description: str = (
        "Cualquier participante del grupo indica el monto de un gasto, "
        "selecciona a las personas involucradas y elige como repartirlo."
    ),
    origin: str = (
        "Se deriva de la meta Gestion financiera de gastos. "
        "Sin esta caracteristica no existiria la informacion base. "
        "Se traza a Metas del producto, Actores y Reglas de negocio."
    ),
) -> dict[str, object]:
    return {
        "number": number,
        "title": title,
        "description": description,
        "origin": origin,
    }


# ------------------------------------------------------------------
# validate_feature_structure — happy path
# ------------------------------------------------------------------


@pytest.mark.unit
def test_validate_feature_structure_passes_for_valid_four_field_feature() -> None:
    # Arrange
    features = [_a_valid_feature()]

    # Act
    result = validate_feature_structure(features)

    # Assert
    assert result.is_valid is True
    assert result.errors == []


# ------------------------------------------------------------------
# validate_feature_structure — error: missing fields
# ------------------------------------------------------------------


@pytest.mark.unit
def test_validate_feature_structure_fails_when_origin_missing() -> None:
    # Arrange
    feat = _a_valid_feature()
    del feat["origin"]

    # Act
    result = validate_feature_structure([feat])

    # Assert
    assert result.is_valid is False
    assert any("origin" in e for e in result.errors)


@pytest.mark.unit
def test_validate_feature_structure_fails_for_empty_list() -> None:
    # Arrange
    features: list[dict[str, object]] = []

    # Act
    result = validate_feature_structure(features)

    # Assert
    assert result.is_valid is False


@pytest.mark.unit
def test_validate_feature_structure_fails_for_non_list_input() -> None:
    # Arrange
    raw = "not a list"

    # Act
    result = validate_feature_structure(raw)

    # Assert
    assert result.is_valid is False


# ------------------------------------------------------------------
# validate_feature_structure — error: title exceeds 6 words
# ------------------------------------------------------------------


@pytest.mark.unit
def test_validate_feature_structure_fails_when_title_exceeds_six_words() -> None:
    # Arrange
    feat = _a_valid_feature(title="Registrar y consultar gastos compartidos entre participantes del grupo")

    # Act
    result = validate_feature_structure([feat])

    # Assert
    assert result.is_valid is False
    assert any("seis palabras" in e.lower() or "6 palabras" in e for e in result.errors)


@pytest.mark.unit
@pytest.mark.parametrize(
    "title",
    [
        "Registrar gastos",
        "Consultar balances y deudas",
        "Crear y administrar grupos compartidos",
    ],
)
@pytest.mark.unit
def test_validate_feature_structure_accepts_titles_within_six_words(title: str) -> None:
    # Arrange
    feat = _a_valid_feature(title=title)

    # Act
    result = validate_feature_structure([feat])

    # Assert
    assert result.is_valid is True


# ------------------------------------------------------------------
# validate_feature_structure — error: technical terms
# ------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "term",
    ["API", "base de datos", "backend", "PostgreSQL", "Docker", "microservicios"],
)
@pytest.mark.unit
def test_validate_feature_structure_flags_technical_term_in_title(term: str) -> None:
    # Arrange
    feat = _a_valid_feature(title=f"Gestionar con {term} del grupo")

    # Act
    result = validate_feature_structure([feat])

    # Assert
    assert result.is_valid is False
    assert any(term in e for e in result.errors)


@pytest.mark.unit
@pytest.mark.parametrize(
    "term",
    ["API", "base de datos", "backend", "frontend", "Docker"],
)
@pytest.mark.unit
def test_validate_feature_structure_flags_technical_term_in_description(term: str) -> None:
    # Arrange
    feat = _a_valid_feature(description=f"El usuario interactua con el {term} para registrar.")

    # Act
    result = validate_feature_structure([feat])

    # Assert
    assert result.is_valid is False
    assert any(term in e for e in result.errors)


@pytest.mark.unit
@pytest.mark.parametrize(
    "term",
    ["API", "base de datos", "servidor", "Docker"],
)
@pytest.mark.unit
def test_validate_feature_structure_flags_technical_term_in_origin(term: str) -> None:
    # Arrange
    feat = _a_valid_feature(
        origin=f"Se deriva de la meta Gestion financiera. Usa {term}. Se traza a Metas del producto."
    )

    # Act
    result = validate_feature_structure([feat])

    # Assert
    assert result.is_valid is False
    assert any(term in e for e in result.errors)


# ------------------------------------------------------------------
# validate_feature_structure — error: business abstract terms
# ------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "term",
    [
        "propuesta de valor",
        "modelo de negocio",
        "ventaja competitiva",
        "diferenciador",
        "monetizacion",
        "ROI",
        "KPI",
        "stakeholder",
        "oportunidad de mercado",
        "segmento de mercado",
        "caso de negocio",
        "estrategia comercial",
    ],
)
@pytest.mark.unit
def test_validate_feature_structure_flags_business_abstract_term_in_title(term: str) -> None:
    # Arrange
    feat = _a_valid_feature(title=f"Optimizar {term} del producto")

    # Act
    result = validate_feature_structure([feat])

    # Assert
    assert result.is_valid is False
    assert any(term in e for e in result.errors)


@pytest.mark.unit
@pytest.mark.parametrize(
    "term",
    ["propuesta de valor", "modelo de negocio", "ROI", "KPI", "stakeholder"],
)
@pytest.mark.unit
def test_validate_feature_structure_flags_business_abstract_term_in_description(term: str) -> None:
    # Arrange
    feat = _a_valid_feature(description=f"El usuario gestiona el {term} para lograr sus objetivos.")

    # Act
    result = validate_feature_structure([feat])

    # Assert
    assert result.is_valid is False
    assert any(term in e for e in result.errors)


@pytest.mark.unit
def test_validate_feature_structure_allows_discovery_section_names_in_origin() -> None:
    # Arrange
    feat = _a_valid_feature(
        origin=(
            "Se deriva de la meta Gestion financiera. "
            "Se traza a Metas del producto, Propuesta de valor y Reglas de negocio."
        )
    )

    # Act
    result = validate_feature_structure([feat])

    # Assert
    assert result.is_valid is True


# ------------------------------------------------------------------
# validate_feature_structure — error: origin without traceability
# ------------------------------------------------------------------


@pytest.mark.unit
def test_validate_feature_structure_fails_when_origin_lacks_discovery_section() -> None:
    # Arrange
    feat = _a_valid_feature(origin="Esta caracteristica es importante para el producto y debe existir.")

    # Act
    result = validate_feature_structure([feat])

    # Assert
    assert result.is_valid is False
    assert any("trazabilidad" in e.lower() or "descubrimiento" in e.lower() for e in result.errors)


# ------------------------------------------------------------------
# validate_feature_structure — edge cases
# ------------------------------------------------------------------


@pytest.mark.unit
def test_validate_feature_structure_fails_when_number_is_not_int() -> None:
    # Arrange
    feat = _a_valid_feature()
    feat["number"] = "uno"

    # Act
    result = validate_feature_structure([feat])

    # Assert
    assert result.is_valid is False
    assert any("number" in e for e in result.errors)


@pytest.mark.unit
@pytest.mark.parametrize(
    "field,value,error_keyword",
    [
        ("title", "ab", "título"),
        ("description", "Corto", "descripción"),
        ("origin", "Corto", "origen"),
    ],
)
def test_validate_feature_structure_fails_when_field_too_short(field: str, value: str, error_keyword: str) -> None:
    # Arrange
    feat = _a_valid_feature(**{field: value})

    # Act
    result = validate_feature_structure([feat])

    # Assert
    assert result.is_valid is False
    assert any(error_keyword in e for e in result.errors)


# ------------------------------------------------------------------
# validate_feature_uniqueness
# ------------------------------------------------------------------


@pytest.mark.unit
def test_validate_feature_uniqueness_passes_for_distinct_features() -> None:
    # Arrange
    features = [
        _a_valid_feature(number=1, title="Registrar gastos entre participantes"),
        _a_valid_feature(
            number=2,
            title="Consultar balances y deudas pendientes",
            description="Cualquier participante accede a un resumen que muestra cuánto debe.",
        ),
    ]

    # Act
    result = validate_feature_uniqueness(features)

    # Assert
    assert result.is_valid is True


@pytest.mark.unit
def test_validate_feature_uniqueness_fails_for_duplicate_titles() -> None:
    # Arrange
    features = [
        _a_valid_feature(number=1, title="Registrar gastos entre participantes"),
        _a_valid_feature(number=2, title="Registrar gastos entre participantes"),
    ]

    # Act
    result = validate_feature_uniqueness(features)

    # Assert
    assert result.is_valid is False


@pytest.mark.unit
def test_validate_feature_uniqueness_fails_when_existing_title_matches() -> None:
    # Arrange
    features = [_a_valid_feature(number=2, title="Registrar gastos entre participantes")]
    existing = ["Registrar gastos entre participantes"]

    # Act
    result = validate_feature_uniqueness(features, existing)

    # Assert
    assert result.is_valid is False


@pytest.mark.unit
def test_validate_feature_uniqueness_passes_for_empty_list() -> None:
    # Arrange
    features: list[dict[str, object]] = []

    # Act
    result = validate_feature_uniqueness(features)

    # Assert
    assert result.is_valid is True


@pytest.mark.unit
def test_validate_feature_uniqueness_emits_warnings_for_capability_overlap() -> None:
    # Arrange: features that overlap functionally as subcapability
    features = [
        _a_valid_feature(
            number=1,
            title="Registro de usuarios",
            description="Permite registrar nuevos usuarios con datos personales y credenciales.",
        ),
        _a_valid_feature(
            number=2,
            title="Aceptar términos y condiciones",
            description="Confirmación y consentimiento de políticas para nuevos usuarios.",
        ),
    ]

    # Act
    result = validate_feature_uniqueness(features)

    # Assert
    assert result.is_valid is True
    assert len(result.warnings) > 0
    assert any("solapamiento" in w.lower() or "sub-capacidad" in w.lower() for w in result.warnings)


@pytest.mark.unit
def test_validate_feature_uniqueness_emits_warnings_for_existing_features_overlap() -> None:
    # Arrange
    from kosmo.contracts.sdd.feature import Feature
    from kosmo.contracts.sdd.ids import FeatureId, ProjectId

    existing = [
        Feature(
            id=FeatureId("feat_exist_1"),
            number=1,
            title="Registro de usuarios",
            slug="registro-de-usuarios",
            description="Permite registrar nuevos usuarios con credenciales y perfil.",
            project_id=ProjectId("prj_001"),
        )
    ]
    features = [
        _a_valid_feature(
            number=2,
            title="Verificación por captcha",
            description="Confirmación de captcha y políticas para registro de usuarios.",
        )
    ]

    # Act
    result = validate_feature_uniqueness(features, existing_features=existing)

    # Assert
    assert result.is_valid is True
    assert len(result.warnings) > 0
    assert any("solapamiento" in w.lower() or "sub-capacidad" in w.lower() for w in result.warnings)
