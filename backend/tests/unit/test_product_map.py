from __future__ import annotations

import pytest

from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.contracts.sdd.product_map import (
    ActorRef,
    CapabilityRef,
    DomainEntityRef,
    FeatureDisposition,
    ImplementationDisposition,
    ProductFlow,
    ProductFlowStep,
    ProductMap,
)
from kosmo.domain.codegen.integration_rules import (
    build_product_map,
    detect_capability_overlap,
    determine_feature_disposition,
    extract_actor_from_text,
    extract_actors_from_discovery,
    extract_actors_from_text,
    infer_domain_entities,
)


def _sample_feature(
    feature_id: str,
    number: int,
    title: str,
    description: str,
    origin: str = "Descubrimiento sección 1.2",
    slug: str | None = None,
) -> Feature:
    clean_slug = slug or title.lower().replace(" ", "-")
    return Feature(
        id=FeatureId(feature_id),
        number=number,
        title=title,
        slug=clean_slug,
        description=description,
        project_id=ProjectId("prj_01TEST"),
        origin=origin,
    )


@pytest.mark.unit
def test_product_map_contract_and_helpers() -> None:
    # Arrange
    p_id = ProjectId("prj_01TEST")
    f1 = "feat_01"
    f2 = "feat_02"

    entity = DomainEntityRef(
        name="Cita",
        description="Cita médica",
        table_name="citas",
        feature_ids=(f1, f2),
    )
    actor = ActorRef(
        name="Paciente",
        navigation_group="Área Paciente",
        feature_ids=(f1,),
    )
    capability = CapabilityRef(
        name="reservar_cita",
        description="Reserva de cita",
        provided_by_feature_id=f1,
    )
    flow = ProductFlow(
        name="Flujo de Cita",
        actor="Paciente",
        steps=(ProductFlowStep(step_number=1, feature_id=f1, description="Seleccionar horario", actor="Paciente"),),
    )
    disposition = FeatureDisposition(
        feature_id=f1,
        disposition=ImplementationDisposition.CREATE,
        actor="Paciente",
        navigation_group="Área Paciente",
    )

    # Act
    pmap = ProductMap(
        project_id=p_id,
        entities=(entity,),
        actors=(actor,),
        capabilities=(capability,),
        flows=(flow,),
        dispositions={f1: disposition},
    )

    # Assert
    assert pmap.get_disposition(f1).disposition == ImplementationDisposition.CREATE
    assert pmap.get_disposition("feat_unregistered").disposition == ImplementationDisposition.CREATE
    assert len(pmap.get_entities_for_feature(f1)) == 1
    assert pmap.get_entities_for_feature(f1)[0].name == "Cita"
    assert len(pmap.get_entities_for_feature("feat_other")) == 0
    assert pmap.get_actor_for_feature(f1) is not None
    assert pmap.get_actor_for_feature(f1).name == "Paciente"
    assert pmap.get_actor_for_feature(f2) is None


@pytest.mark.unit
def test_detect_capability_overlap() -> None:
    # Arrange
    feat_booking = _sample_feature(
        "feat_01", 1, "Agendar cita médica", "El paciente puede agendar cita médica seleccionando fecha."
    )
    feat_terms = _sample_feature(
        "feat_02", 2, "Aceptar términos y condiciones", "El paciente debe aceptar términos y condiciones del servicio."
    )
    feat_profile = _sample_feature("feat_03", 3, "Ver perfil", "El usuario puede ver y editar sus datos personales.")

    # Act
    overlaps = detect_capability_overlap(feat_terms, [feat_booking, feat_profile])

    # Assert: detects overlap with booking because terms is a subcapability step
    assert len(overlaps) >= 1
    assert any(o.feature_b_id == "feat_01" for o in overlaps)
    assert any(o.is_subcapability for o in overlaps)


@pytest.mark.unit
def test_extract_actor_from_text() -> None:
    # Act & Assert
    assert extract_actor_from_text("Actor: Administrador del sistema", "Gestiona roles") == "Administrador"
    assert extract_actor_from_text("El cliente compra boletos", "Selecciona asiento") == "Cliente"
    assert extract_actor_from_text("El paciente consulta su historial", "Ver citas") == "Paciente"
    assert extract_actor_from_text("Configuración del servidor", "Sin actor especificado") == "General"


@pytest.mark.unit
def test_infer_domain_entities_detects_shared_nouns() -> None:
    # Arrange
    f1 = _sample_feature("feat_01", 1, "Registrar gastos", "Permite registrar gastos del grupo.")
    f2 = _sample_feature("feat_02", 2, "Liquidar deudas y gastos", "Calcula y liquida gastos pendientes.")
    f3 = _sample_feature("feat_03", 3, "Crear grupo de amigos", "Crea un nuevo grupo.")

    # Act
    entities = infer_domain_entities([f1, f2, f3])

    # Assert: 'gastos' or 'grupo' appear in 2+ features and become DomainEntityRef
    entity_names = {e.name.lower() for e in entities}
    assert "gastos" in entity_names or "gasto" in entity_names


@pytest.mark.unit
def test_determine_feature_disposition_cases() -> None:
    # Arrange
    f_booking = _sample_feature("feat_01", 1, "Agendar cita médica", "Permite agendar cita médica.")
    f_cancel = _sample_feature("feat_02", 2, "Cancelar cita médica", "Permite cancelar una cita agendada.")
    f_terms = _sample_feature("feat_03", 3, "Aceptar términos y condiciones", "Aceptar términos y condiciones.")
    f_dash = _sample_feature("feat_04", 4, "Dashboard de resumen", "Panel y métricas globales de citas.")

    all_features = [f_booking, f_cancel, f_terms, f_dash]
    implemented_ids = {"feat_01"}

    # Act
    disp_extend = determine_feature_disposition(f_cancel, all_features, implemented_ids)
    disp_integrate = determine_feature_disposition(f_terms, all_features, implemented_ids)
    disp_compose = determine_feature_disposition(f_dash, all_features, implemented_ids)
    disp_create = determine_feature_disposition(f_booking, all_features, set())

    # Assert
    assert disp_extend.disposition == ImplementationDisposition.EXTEND
    assert disp_integrate.disposition == ImplementationDisposition.INTEGRATE
    assert disp_integrate.target_feature_id == "feat_01"
    assert disp_compose.disposition == ImplementationDisposition.COMPOSE
    assert disp_create.disposition == ImplementationDisposition.CREATE


@pytest.mark.unit
def test_build_product_map_comprehensive() -> None:
    # Arrange
    p_id = ProjectId("prj_clinic")
    f1 = _sample_feature("feat_01", 1, "Agendar cita médica", "El paciente agenda citas.", "Actores: Paciente")
    f2 = _sample_feature(
        "feat_02", 2, "Consultar historial de citas", "El paciente consulta sus citas.", "Actores: Paciente"
    )
    f3 = _sample_feature("feat_03", 3, "Gestionar horarios", "El doctor configura disponibilidad.", "Actores: Doctor")

    # Act
    pmap = build_product_map(p_id, [f1, f2, f3], implemented_feature_ids={"feat_01"})

    # Assert
    assert pmap.project_id == p_id
    assert len(pmap.actors) >= 2
    actor_names = {a.name for a in pmap.actors}
    assert "Paciente" in actor_names
    assert "Doctor" in actor_names
    assert len(pmap.flows) >= 2
    assert "feat_01" in pmap.dispositions
    assert "feat_02" in pmap.dispositions
    assert pmap.dispositions["feat_02"].disposition == ImplementationDisposition.EXTEND


@pytest.mark.unit
def test_extract_actors_from_discovery() -> None:
    discovery_md = """# Visión del Sistema
## Actores
- Administrador: Gestiona la plataforma
- Médico: Atiende consultas y emite recetas
- Paciente: Solicita citas y consulta historial
## Requisitos
Algo más
"""
    actors = extract_actors_from_discovery(discovery_md)
    assert actors == ("Administrador", "Médico", "Paciente")


@pytest.mark.unit
def test_extract_actors_from_text_multi_actor() -> None:
    # Multiple known actors in same feature
    actors = extract_actors_from_text(
        origin="Actores: Médico y Paciente",
        description="El médico receta medicamentos y el paciente los visualiza en su portal.",
    )
    assert "Médico" in actors
    assert "Paciente" in actors

    # Matching against custom discovery actors
    custom_discovery = ("Recepcionista", "Especialista")
    actors_custom = extract_actors_from_text(
        origin="El recepcionista asigna citas",
        description="Notifica al especialista de turno",
        discovery_actors=custom_discovery,
    )
    assert "Recepcionista" in actors_custom
    assert "Especialista" in actors_custom


@pytest.mark.unit
def test_build_product_map_multi_actor_and_get_actors() -> None:
    p_id = ProjectId("prj_multi")
    f_shared = _sample_feature(
        "feat_chat",
        1,
        "Teleconsulta y Chat",
        "El doctor conversa con el paciente en tiempo real.",
        origin="Actores: Doctor y Paciente",
    )
    pmap = build_product_map(p_id, [f_shared])

    # Feature should belong to both Doctor and Paciente
    disp = pmap.get_disposition("feat_chat")
    assert "Doctor" in disp.actors
    assert "Paciente" in disp.actors

    actors_for_feat = pmap.get_actors_for_feature("feat_chat")
    actor_names = {a.name for a in actors_for_feat}
    assert "Doctor" in actor_names
    assert "Paciente" in actor_names
