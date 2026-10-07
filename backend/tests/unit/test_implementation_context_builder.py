from __future__ import annotations

from pathlib import Path

import pytest

from kosmo.application.codegen.implementation_context_builder import (
    ImplementationContextBuilder,
    NullFileSystemReader,
    NullFileSystemWriter,
    collect_workspace_feature_files,
    get_existing_db_schema_context,
    normalize_generated_file_path,
)
from kosmo.contracts.sdd.codegen import (
    FeatureImplementation,
    FeatureImplementationStatus,
    FileAction,
    FileSystemWriter,
    ValidationErrorDetail,
    ValidationRunResult,
    ValidationSeverity,
    ValidationStep,
    ValidationStepResult,
)
from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ImplementationId, ProjectId, UserId
from kosmo.contracts.sdd.product_map import (
    ActorRef,
    DomainEntityRef,
    FeatureDisposition,
    ImplementationDisposition,
    ProductMap,
)
from kosmo.contracts.sdd.project import Project
from kosmo.contracts.sdd.ux_context import (
    BootstrapDesignTokens,
    BusinessArchetype,
    DataDensity,
    ShellPattern,
    UXAnalysisOutput,
    UXContext,
)
from kosmo.domain.sdd.document_converters import markdown_to_document
from kosmo.infrastructure.codegen.workspace import (
    LocalFileSystemReader,
    LocalFileSystemWriter,
)
from tests.unit.fakes import (
    InMemoryDocumentRepository,
    InMemoryFeatureImplementationRepository,
    InMemoryFeatureRepository,
    InMemoryProjectRepository,
)


class _FakeFsReader(FileSystemWriter):
    def __init__(self, files: dict[str, str]) -> None:
        self.files = files

    def list_files(self, root: str | Path) -> tuple[str, ...]:
        return tuple(self.files.keys())

    def read_text(self, path: str | Path) -> str | None:
        p_str = str(path).replace("\\", "/").strip("./")
        for k, v in self.files.items():
            norm_k = k.replace("\\", "/").strip("./")
            if p_str == norm_k or p_str.endswith(f"/{norm_k}"):
                return v
        return None

    def write_text(self, path: str | Path, content: str) -> None:
        p_str = str(path).replace("\\", "/").strip("./")
        self.files[p_str] = content


@pytest.mark.unit
def test_null_file_system_reader() -> None:
    reader = NullFileSystemReader()
    assert reader.list_files("/any/path") == ()
    assert reader.read_text("/any/file") is None


@pytest.mark.unit
def test_null_file_system_writer() -> None:
    writer = NullFileSystemWriter()
    writer.write_text("/any/path", "content")


@pytest.mark.unit
def test_normalize_generated_file_path(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    file_inside = ws / "src" / "app" / "page.tsx"
    file_inside.parent.mkdir(parents=True)
    file_inside.write_text("ok")

    # Relative path
    assert normalize_generated_file_path("src/app/page.tsx", str(ws)) == "src/app/page.tsx"
    # Absolute path inside workspace
    assert normalize_generated_file_path(str(file_inside), str(ws)) == "src/app/page.tsx"
    # Unsafe or outside path
    assert normalize_generated_file_path("../../outside.ts", str(ws)) is None
    assert normalize_generated_file_path("", str(ws)) is None


@pytest.mark.unit
def test_collect_workspace_feature_files() -> None:
    fs = _FakeFsReader(
        {
            "src/features/billing/components/Invoice.tsx": "...",
            "src/app/billing/page.tsx": "...",
            "src/lib/feature-registry.ts": "...",
            "src/lib/site.ts": "...",
            "src/db/schema.ts": "...",
            "src/features/other/logic.ts": "...",
        }
    )
    collected = collect_workspace_feature_files("/ws", "billing", fs)
    assert "src/features/billing/components/Invoice.tsx" in collected
    assert "src/app/billing/page.tsx" in collected
    assert "src/lib/feature-registry.ts" in collected
    assert "src/lib/site.ts" in collected
    assert "src/db/schema.ts" in collected
    assert "src/features/other/logic.ts" not in collected


@pytest.mark.unit
def test_get_existing_db_schema_context() -> None:
    fs = _FakeFsReader({"src/db/schema.ts": "export const items = sqliteTable('items', {});"})
    ctx = get_existing_db_schema_context("/ws", fs)
    assert "export const items = sqliteTable" in ctx
    assert "### Esquema de base de datos actual" in ctx

    empty_fs = _FakeFsReader({})
    assert get_existing_db_schema_context("/ws", empty_fs) == ""
    assert get_existing_db_schema_context(None, fs) == ""


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_project_context_and_implemented_features() -> None:
    project_id = ProjectId("prj_123")
    user_id = UserId("usr_123")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(
        Project(id=project_id, name="Test App", slug="test-app", description="Una app de prueba", owner_id=user_id)
    )

    doc_repo = InMemoryDocumentRepository()
    doc = markdown_to_document("# Visión\nPlataforma de e-commerce")
    await doc_repo.save_discovery(project_id, doc)

    feat_repo = InMemoryFeatureRepository()
    feat1 = Feature(
        id=FeatureId("feat_1"),
        number=1,
        project_id=project_id,
        title="Catálogo",
        slug="catalogo",
        description="Ver productos",
    )
    feat2 = Feature(
        id=FeatureId("feat_2"),
        number=2,
        project_id=project_id,
        title="Carrito",
        slug="carrito",
        description="Comprar productos",
    )
    await feat_repo.save(feat1)
    await feat_repo.save(feat2)

    impl_repo = InMemoryFeatureImplementationRepository()
    await impl_repo.save(
        FeatureImplementation(
            id=ImplementationId("impl_1"),
            feature_id=feat1.id,
            project_id=project_id,
            status=FeatureImplementationStatus.IMPLEMENTED,
            generated_files=("src/features/catalogo/logic.ts", "src/app/catalogo/page.tsx"),
        )
    )
    await impl_repo.save(
        FeatureImplementation(
            id=ImplementationId("impl_2"),
            feature_id=feat2.id,
            project_id=project_id,
            status=FeatureImplementationStatus.IN_PROGRESS,
        )
    )

    fs = _FakeFsReader({"src/db/schema.ts": "export const products = sqliteTable('products', {});"})

    builder = ImplementationContextBuilder(
        project_repo=project_repo,
        document_repo=doc_repo,
        implementation_repo=impl_repo,
        feature_repo=feat_repo,
        fs_reader=fs,
    )

    # implemented features context excludes current feature and IN_PROGRESS
    impl_ctx = await builder.build_implemented_features_context(project_id, current_feature_id=feat2.id)
    assert "Catálogo" in impl_ctx
    assert "slug: `catalogo`" in impl_ctx
    assert "Carrito" not in impl_ctx

    # full project context
    prj_ctx = await builder.build_project_context(project_id, current_feature_id=feat2.id, workspace_dir="/ws")
    assert "Test App" in prj_ctx
    assert "Una app de prueba" in prj_ctx
    assert "Plataforma de e-commerce" in prj_ctx
    assert "Catálogo" in prj_ctx
    assert "export const products" in prj_ctx


@pytest.mark.unit
def test_build_fallback_plan_operations() -> None:
    builder = ImplementationContextBuilder()
    feat = Feature(
        id=FeatureId("feat_test"),
        number=1,
        project_id=ProjectId("prj_test"),
        title="Reportes",
        slug="reportes",
        description="Módulo de reportes",
    )
    # Manifest without feature-registry.ts -> CREATE
    ops_create = builder.build_fallback_plan_operations(feat, "reportes", ("package.json",))
    assert len(ops_create) == 6
    registry_op = next(op for op in ops_create if op.path == "src/lib/feature-registry.ts")
    assert registry_op.action == FileAction.CREATE
    actions_op = next(op for op in ops_create if op.path == "src/features/reportes/actions.ts")
    assert actions_op.action == FileAction.CREATE

    # Manifest with feature-registry.ts -> MODIFY
    ops_modify = builder.build_fallback_plan_operations(
        feat, "reportes", ("package.json", "src/lib/feature-registry.ts")
    )
    registry_op_mod = next(op for op in ops_modify if op.path == "src/lib/feature-registry.ts")
    assert registry_op_mod.action == FileAction.MODIFY


@pytest.mark.unit
def test_build_prompts() -> None:
    builder = ImplementationContextBuilder()
    feat = Feature(
        id=FeatureId("feat_prompt"),
        number=1,
        project_id=ProjectId("prj_prompt"),
        title="Facturación",
        slug="facturacion",
        description="Generar facturas electrónicas",
    )

    plan_prompt = builder.build_plan_prompt(
        feature=feat,
        req_markdown="REQ-01: Al hacer click en emitir...",
        diagram_syntax="stateDiagram-v2\n[*] --> Emitir",
        ux_prompt_block="[UX Directives: Admin/Table]",
        project_context="## Contexto del proyecto\n- Nombre: Facturador",
    )
    assert "[UX Directives: Admin/Table]" in plan_prompt
    assert "Facturador" in plan_prompt
    assert "REQ-01: Al hacer click" in plan_prompt
    assert "stateDiagram-v2" in plan_prompt
    assert "src/features/<slug>/" in plan_prompt
    assert "CERO MOCKS" in plan_prompt
    assert "actions.ts" in plan_prompt

    build_prompt = builder.build_build_prompt(
        feature=feat,
        req_markdown="REQ-01: Al hacer click en emitir...",
        diagram_syntax="stateDiagram-v2\n[*] --> Emitir",
        ux_prompt_block="[UX Directives: Admin/Table]",
        project_context="## Contexto del proyecto\n- Nombre: Facturador",
        plan_lines="- [create] src/app/facturacion/page.tsx",
    )
    assert "- [create] src/app/facturacion/page.tsx" in build_prompt
    assert "Bootstrap 5" in build_prompt
    assert "PERSISTENCIA REAL, CERO MOCKS" in build_prompt
    assert "actions.ts" in build_prompt

    validation_result = ValidationRunResult(
        steps=(
            ValidationStepResult(
                step=ValidationStep.LINT,
                success=False,
                error_messages=("Type error on line 42",),
                errors=(
                    ValidationErrorDetail(
                        file="src/features/facturacion/logic.ts",
                        message="Type error on line 42",
                        severity=ValidationSeverity.ERROR,
                    ),
                ),
            ),
        ),
        all_passed=False,
        error_summary=("Type error on line 42",),
    )
    fix_prompt = builder.build_fix_prompt(
        attempt=1,
        max_retries=3,
        validation_result=validation_result,
    )
    assert "La validación falló en el intento 1/3" in fix_prompt
    assert "Type error on line 42" in fix_prompt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_site_config(tmp_path: Path) -> None:
    project_id = ProjectId("prj_site")
    user_id = UserId("usr_site")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(
        Project(id=project_id, name="Mi Tienda", slug="mi-tienda", description="Tienda online", owner_id=user_id)
    )

    ws_dir = tmp_path / "ws"
    lib_dir = ws_dir / "src" / "lib"
    lib_dir.mkdir(parents=True)
    site_file = lib_dir / "site.ts"
    site_file.write_text("// original")

    ux_analysis = UXAnalysisOutput(
        ux_context=UXContext(
            archetype=BusinessArchetype.STOREFRONT,
            shell_pattern=ShellPattern.SIDEBAR,
            data_density=DataDensity.MEDIUM,
            tokens=BootstrapDesignTokens(primary_color="#ff5500"),
        ),
        prompt_block="",
    )

    builder = ImplementationContextBuilder(
        project_repo=project_repo,
        fs_reader=LocalFileSystemReader(),
        fs_writer=LocalFileSystemWriter(),
    )
    await builder.sync_site_config(str(ws_dir), project_id, ux_analysis)

    content = site_file.read_text(encoding="utf-8")
    assert "Mi Tienda" in content
    assert "Tienda online" in content
    assert "#ff5500" in content
    assert "storefront" in content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_sync_site_config_pure_in_memory() -> None:
    project_id = ProjectId("prj_mem")
    user_id = UserId("usr_mem")
    project_repo = InMemoryProjectRepository()
    await project_repo.save(
        Project(id=project_id, name="Mem Tienda", slug="mem-tienda", description="Mem desc", owner_id=user_id)
    )

    fake_fs = _FakeFsReader(
        {
            "ws/src/lib/site.ts": "// original",
            "ws/src/lib/design-tokens.ts": "// tokens",
            "ws/src/app/globals.css": "/* css */",
        }
    )

    ux_analysis = UXAnalysisOutput(
        ux_context=UXContext(
            archetype=BusinessArchetype.STOREFRONT,
            shell_pattern=ShellPattern.SIDEBAR,
            data_density=DataDensity.MEDIUM,
            tokens=BootstrapDesignTokens(primary_color="#112233"),
        ),
        prompt_block="",
    )

    builder = ImplementationContextBuilder(
        project_repo=project_repo,
        fs_reader=fake_fs,
        fs_writer=fake_fs,
    )
    await builder.sync_site_config("ws", project_id, ux_analysis)

    site_content = fake_fs.read_text("ws/src/lib/site.ts")
    assert site_content is not None
    assert "Mem Tienda" in site_content
    assert "#112233" in site_content

    tokens_content = fake_fs.read_text("ws/src/lib/design-tokens.ts")
    assert tokens_content is not None
    assert "#112233" in tokens_content

    css_content = fake_fs.read_text("ws/src/app/globals.css")
    assert css_content is not None


@pytest.mark.unit
def test_format_product_map_context_and_prompts() -> None:
    builder = ImplementationContextBuilder()
    p_id = ProjectId("prj_clinic")
    f_id = FeatureId("feat_02")

    pmap = ProductMap(
        project_id=p_id,
        entities=(
            DomainEntityRef(
                name="Cita",
                description="Cita médica",
                table_name="citas",
                feature_ids=("feat_01", "feat_02"),
            ),
        ),
        actors=(ActorRef(name="Paciente", navigation_group="Área Paciente", feature_ids=("feat_02",)),),
        dispositions={
            "feat_02": FeatureDisposition(
                feature_id="feat_02",
                disposition=ImplementationDisposition.EXTEND,
                actor="Paciente",
                actors=("Médico", "Paciente"),
                navigation_group="Área Paciente",
                reason="Extiende la entidad Cita sin duplicar persistencia",
            )
        },
    )

    formatted = builder.format_product_map_context(pmap, current_feature_id=f_id)
    assert "Mapa de Cohesión e Integración del Producto (Product Map)" in formatted
    assert "EXTENSIÓN" in formatted
    assert "Área Paciente" in formatted
    assert "Cita" in formatted
    assert "**Actores involucrados:** Médico, Paciente" in formatted
    assert "Interacción Multi-Rol" in formatted

    feature = Feature(
        id=f_id,
        number=2,
        title="Cancelar cita",
        slug="cancelar-cita",
        description="Cancela una cita médica agendada.",
        project_id=p_id,
    )
    plan_prompt = builder.build_plan_prompt(
        feature=feature,
        req_markdown="### REQ-2.1 Cancelar",
        diagram_syntax="@startuml\n@enduml",
        ux_prompt_block="UX",
        project_context="CTX",
        product_map=pmap,
    )
    assert "Directiva de Integración del Product Map" in plan_prompt
    assert "EXTEND" in plan_prompt
    assert "src/domain/" in plan_prompt
    assert "Actores involucrados: Médico, Paciente" in plan_prompt
    assert "IMPORTANTE MULTI-ROL" in plan_prompt

    build_prompt = builder.build_build_prompt(
        feature=feature,
        req_markdown="### REQ-2.1 Cancelar",
        diagram_syntax="@startuml\n@enduml",
        ux_prompt_block="UX",
        project_context="CTX",
        plan_lines="- [create] src/app/cancelar-cita/page.tsx",
        product_map=pmap,
    )
    assert "Actores involucrados: Médico, Paciente" in build_prompt
    assert "SOPORTE MULTI-ROL" in build_prompt
