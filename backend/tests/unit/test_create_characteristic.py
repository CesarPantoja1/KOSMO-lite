from typing import Any

import pytest

from kosmo.application.features.create_characteristic import (
    CreateCharacteristicInput,
    CreateCharacteristicUseCase,
)
from kosmo.contracts.llm.ports import LLMResponse, LLMUsage, PromptTemplate
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from tests.unit.conftest import DISCOVERY_VALID
from tests.unit.fakes import InMemoryDocumentRepository, InMemoryFeatureRepository


class _InconsistentLLMClient:
    async def complete_json(
        self,
        prompt: PromptTemplate,  # noqa: ARG002
        temperature: float = 0.2,  # noqa: ARG002
        max_tokens: int = 2048,  # noqa: ARG002
    ) -> LLMResponse:
        return LLMResponse(
            text=(
                '{"origin": "Sin relacion directa con las secciones del descubrimiento.", '
                '"is_consistent": false, '
                '"reason": "Amplia el alcance mas alla de lo declarado: las bebidas estan Excluidas en Alcance."}'
            ),
            usage=LLMUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_characteristic_success() -> None:
    repository: Any = InMemoryFeatureRepository()
    use_case = CreateCharacteristicUseCase(feature_repo=repository)
    project_id = ProjectId("prj_create_test")

    input_data = CreateCharacteristicInput(
        project_id=project_id,
        title="Catalogo de productos",
        description="Permite a los usuarios administrar el catalogo de productos del sistema",
    )
    output = await use_case.execute(input_data)

    assert output.characteristic.project_id == project_id
    assert output.characteristic.title == "Catalogo de productos"
    assert output.characteristic.number == 1
    assert output.characteristic.display_id == "C01"
    assert str(output.characteristic.id).startswith("feat_")
    assert output.characteristic.slug == "catalogo-de-productos"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_characteristic_increments_number() -> None:
    repository: Any = InMemoryFeatureRepository()
    use_case = CreateCharacteristicUseCase(feature_repo=repository)
    project_id = ProjectId("prj_increment")

    await repository.save(
        Feature(
            id=FeatureId("feat_existing1"),
            number=1,
            title="Feature 1",
            slug="feature-1",
            description="Desc 1",
            project_id=project_id,
        )
    )
    await repository.save(
        Feature(
            id=FeatureId("feat_existing2"),
            number=2,
            title="Feature 2",
            slug="feature-2",
            description="Desc 2",
            project_id=project_id,
        )
    )

    output = await use_case.execute(
        CreateCharacteristicInput(
            project_id=project_id,
            title="Feature 3",
            description="Tercera caracteristica",
        )
    )

    assert output.characteristic.number == 3
    assert output.characteristic.display_id == "C03"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_characteristic_title_too_long_raises() -> None:
    repository: Any = InMemoryFeatureRepository()
    use_case = CreateCharacteristicUseCase(feature_repo=repository)

    with pytest.raises(ValueError, match="50 caracteres"):
        await use_case.execute(
            CreateCharacteristicInput(
                project_id=ProjectId("prj_long_title"),
                title="A" * 60,
                description="Descripcion valida",
            )
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_characteristic_description_too_long_raises() -> None:
    repository: Any = InMemoryFeatureRepository()
    use_case = CreateCharacteristicUseCase(feature_repo=repository)

    with pytest.raises(ValueError, match="500 caracteres"):
        await use_case.execute(
            CreateCharacteristicInput(
                project_id=ProjectId("prj_long_desc"),
                title="Titulo valido",
                description="D" * 600,
            )
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_characteristic_empty_title_raises() -> None:
    repository: Any = InMemoryFeatureRepository()
    use_case = CreateCharacteristicUseCase(feature_repo=repository)

    with pytest.raises(ValueError, match="vacio"):
        await use_case.execute(
            CreateCharacteristicInput(
                project_id=ProjectId("prj_empty_title"),
                title="",
                description="Descripcion valida",
            )
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_characteristic_generates_unique_id_per_call() -> None:
    repository: Any = InMemoryFeatureRepository()
    use_case = CreateCharacteristicUseCase(feature_repo=repository)
    project_id = ProjectId("prj_unique")

    output1 = await use_case.execute(
        CreateCharacteristicInput(
            project_id=project_id,
            title="Feature A",
            description="Primera",
        )
    )
    output2 = await use_case.execute(
        CreateCharacteristicInput(
            project_id=project_id,
            title="Feature B",
            description="Segunda",
        )
    )

    assert str(output1.characteristic.id) != str(output2.characteristic.id)
    assert output1.characteristic.number == 1
    assert output2.characteristic.number == 2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_characteristic_rejects_when_inconsistent_with_discovery() -> None:
    """Una característica que contradice el Descubrimiento no debe guardarse
    ni siquiera con intención de forzar: el guard de coherencia es definitivo."""
    # Arrange
    from kosmo.domain.sdd.document_converters import markdown_to_document

    repository: Any = InMemoryFeatureRepository()
    docs: Any = InMemoryDocumentRepository()
    docs.discovery_docs["prj_guard"] = markdown_to_document(DISCOVERY_VALID)
    use_case = CreateCharacteristicUseCase(
        feature_repo=repository,
        document_repo=docs,
        llm_client=_InconsistentLLMClient(),  # type: ignore[reportArgumentType]
    )

    # Act
    output = await use_case.execute(
        CreateCharacteristicInput(
            project_id=ProjectId("prj_guard"),
            title="Venta de bebidas y abarrotes",
            description="Administrar bebidas, abarrotes y articulos de cocina.",
        )
    )

    # Assert — rechazada y sin persistir
    assert output.is_saved is False
    assert output.characteristic is None
    assert output.is_consistent is False
    assert "alcance" in output.inconsistency_reason.lower()
    saved = await repository.list_by_project(ProjectId("prj_guard"))
    assert saved == []


@pytest.mark.asyncio
@pytest.mark.unit
async def test_create_characteristic_emits_warning_on_capability_overlap() -> None:
    repository: Any = InMemoryFeatureRepository()
    use_case = CreateCharacteristicUseCase(feature_repo=repository)
    project_id = ProjectId("prj_overlap")

    await repository.save(
        Feature(
            id=FeatureId("feat_1"),
            number=1,
            title="Registro de usuarios",
            slug="registro-de-usuarios",
            description="Permite registrar nuevos usuarios con verificacion y datos personales",
            project_id=project_id,
        )
    )

    output = await use_case.execute(
        CreateCharacteristicInput(
            project_id=project_id,
            title="Aceptar terminos y condiciones",
            description="Confirmacion de politicas y consentimiento para registro de usuarios",
        )
    )

    assert output.is_saved is True
    assert output.characteristic is not None
    assert len(output.warnings) > 0
    assert any("solapamiento" in w.lower() or "sub-capacidad" in w.lower() for w in output.warnings)
