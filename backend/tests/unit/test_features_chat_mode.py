from __future__ import annotations

from kosmo.contracts import (
    RespuestaChatLLM,
    SugerenciaCambioLLM,
)
from kosmo.contracts.pipeline.phase_contexts import FeatureChatContext
from kosmo.contracts.sdd.document import DocumentNode, RichTextDocument, SectionHeading, SpecPhase
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.domain.pipeline.phase_modes.features_chat_mode import FeaturesChatMode


def test_features_chat_mode_properties() -> None:
    mode = FeaturesChatMode()

    assert mode.phase_name == SpecPhase.CARACTERISTICAS
    assert mode.temperature == 0.4
    assert mode.max_tokens == 8192
    assert mode.output_type == RespuestaChatLLM
    assert "NIVEL DE USUARIO" in mode.system_prompt
    assert "no afirmes que un cambio fue aplicado" in mode.system_prompt
    assert "NO generes una nueva sugerencia" not in mode.system_prompt
    assert mode.available_tools == []


def test_features_chat_mode_allows_multiple_suggestions() -> None:
    mode = FeaturesChatMode()

    prompt = mode.system_prompt

    assert "change_suggestions" in prompt
    assert "una sugerencia por cada atributo afectado" in prompt
    assert '"change_suggestions": null | [' in prompt


def test_features_chat_mode_build_user_prompt() -> None:
    mode = FeaturesChatMode()

    doc = RichTextDocument(
        nodes=[
            DocumentNode(
                type="heading",
                content="Alcance",
                heading=SectionHeading(text="Alcance", level=2, slug="alcance"),
            )
        ]
    )
    feature = Feature(
        id=FeatureId("feat_100"),
        number=1,
        title="Registrar gastos compartidos",
        slug="registrar-gastos-compartidos",
        description="El usuario ingresa un gasto para dividirlo entre los integrantes del viaje.",
        project_id=ProjectId("prj_001"),
        origin="Deriva de la meta Gestión financiera.",
    )
    context = FeatureChatContext(
        feature=feature,
        discovery_document=doc,
    )

    prompt = mode.build_user_prompt(context)

    assert "Registrar gastos compartidos" in prompt
    assert "C01" in prompt
    assert "El usuario ingresa un gasto" in prompt
    assert "Deriva de la meta Gestión financiera." in prompt
    assert "Documento de descubrimiento de referencia" in prompt


def test_features_chat_mode_validate_output_valid() -> None:
    mode = FeaturesChatMode()

    sugg = SugerenciaCambioLLM(
        section="Descripción",
        description="Amplía el alcance a la región LATAM",
        diff_before="gastos nacionales",
        diff_after="gastos y vuelos en LATAM",
        rationale="Se ajusta de acuerdo a la sección Alcance del Descubrimiento.",
    )
    response = RespuestaChatLLM(
        content="He sugerido actualizar la descripción.",
        change_suggestion=sugg,
    )

    val_res = mode.validate_output(response)
    assert val_res.is_valid is True
    assert len(val_res.errors) == 0


def test_features_chat_mode_validate_output_empty_diff() -> None:
    mode = FeaturesChatMode()

    sugg = SugerenciaCambioLLM(
        section="Descripción",
        description="Sin cambios reales",
        diff_before="mismo texto",
        diff_after="mismo texto",
    )
    response = RespuestaChatLLM(
        content="No hay cambios.",
        change_suggestion=sugg,
    )

    val_res = mode.validate_output(response)
    assert val_res.is_valid is False
    assert any("idénticos" in e for e in val_res.errors)


def test_features_chat_mode_build_user_prompt_with_other_features_and_overlap() -> None:
    mode = FeaturesChatMode()

    doc = RichTextDocument(
        nodes=[
            DocumentNode(
                type="heading",
                content="Alcance",
                heading=SectionHeading(text="Alcance", level=2, slug="alcance"),
            )
        ]
    )
    feature = Feature(
        id=FeatureId("feat_101"),
        number=2,
        title="Aceptar términos y condiciones",
        slug="aceptar-terminos",
        description="Confirmación y consentimiento de políticas para registrar usuarios.",
        project_id=ProjectId("prj_001"),
        origin="Deriva de Reglas de negocio.",
    )
    other = Feature(
        id=FeatureId("feat_100"),
        number=1,
        title="Registro de usuarios",
        slug="registro-de-usuarios",
        description="Permite registrar nuevos usuarios con credenciales.",
        project_id=ProjectId("prj_001"),
        origin="Deriva de Actores.",
    )
    context = FeatureChatContext(
        feature=feature,
        discovery_document=doc,
        other_features=(other,),
    )

    prompt = mode.build_user_prompt(context)

    assert "Otras características del proyecto" in prompt
    assert "Registro de usuarios" in prompt
    assert "Advertencias de solapamiento funcional detectadas" in prompt
    assert "sub-capacidad" in prompt or "solapamiento" in prompt
