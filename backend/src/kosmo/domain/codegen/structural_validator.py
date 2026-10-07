from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from kosmo.contracts.sdd.codegen import FileSystemReader
from kosmo.contracts.sdd.product_map import ImplementationDisposition


@dataclass(frozen=True)
class StructuralValidationResult:
    is_valid: bool
    errors: tuple[str, ...] = field(default_factory=tuple)
    missing_page: bool = False
    missing_slice: bool = False
    missing_registry: bool = False


def validate_feature_structure(
    feature_slug: str,
    files: Iterable[str],
    registry_content: str | None = None,
    page_content: str | None = None,
    disposition: ImplementationDisposition | str = ImplementationDisposition.CREATE,
) -> StructuralValidationResult:
    """Valida determinísticamente la estructura requerida para una funcionalidad en el workspace.

    Respeta la disposición de implementación del Product Map:
    - CREATE / EXTEND / COMPOSE: Verifica page.tsx con export default, slice en src/features/<slug>/
      y registro en src/lib/feature-registry.ts.
    - INTEGRATE: Sub-capacidad integrada en un flujo/página existente o en src/domain/.
      No exige page.tsx aislada ni entrada propia en el registro si aporta archivos al workspace.
    - SKIP: Característica ya cubierta o redundante; no requiere nuevos archivos aislados.
    """
    disp_str = str(disposition).lower()
    if disp_str == ImplementationDisposition.SKIP or disp_str == "skip":
        return StructuralValidationResult(is_valid=True)

    normalized_slug = feature_slug.strip().lower()
    normalized_files = [f.replace("\\", "/").strip("./") for f in files]

    # Caso INTEGRATE: sub-capacidad que se integra en flujo padre o en src/domain/
    if disp_str == ImplementationDisposition.INTEGRATE or disp_str == "integrate":
        has_any_implementation_file = any(
            f.lower().startswith(f"src/features/{normalized_slug}/")
            or f"/{normalized_slug}/" in f.lower()
            or f.lower().startswith("src/domain/")
            or normalized_slug in f.lower()
            for f in normalized_files
        )
        if has_any_implementation_file:
            return StructuralValidationResult(is_valid=True)
        return StructuralValidationResult(
            is_valid=False,
            errors=(f"La sub-capacidad '{normalized_slug}' no generó archivos en el slice ni en src/domain/.",),
            missing_slice=True,
        )

    # 1. Verificar page.tsx
    valid_page_suffixes = (
        f"src/app/{normalized_slug}/page.tsx",
        f"src/app/{normalized_slug}/page.jsx",
        f"src/app/{normalized_slug}/page.ts",
        f"src/app/{normalized_slug}/page.js",
    )
    has_page = any(
        f.lower() in valid_page_suffixes or any(f.lower().endswith(f"/{suffix}") for suffix in valid_page_suffixes)
        for f in normalized_files
    )

    page_has_export_default = True
    if page_content is not None:
        page_has_export_default = "export default" in page_content

    # 2. Verificar feature slice o módulo de dominio
    slice_prefix = f"src/features/{normalized_slug}/"
    has_slice = any(
        f.lower().startswith(slice_prefix)
        or f"/{slice_prefix}" in f.lower()
        or (f.lower().startswith("src/domain/") and normalized_slug in f.lower())
        for f in normalized_files
    )

    # 3. Verificar feature registry
    has_registry = True
    if registry_content is not None:
        has_registry = normalized_slug in registry_content.lower()
    else:
        registry_file = "src/lib/feature-registry.ts"
        has_registry_file = any(
            f.lower() == registry_file or f.lower().endswith(f"/{registry_file}") for f in normalized_files
        )
        if not has_registry_file:
            has_registry = False

    errors: list[str] = []
    if not has_page:
        errors.append(f"Falta la página principal de la funcionalidad: src/app/{normalized_slug}/page.tsx")
    elif not page_has_export_default:
        errors.append(
            f"La página 'src/app/{normalized_slug}/page.tsx' debe tener exportación por defecto ('export default')."
        )
    if not has_slice:
        errors.append(f"Falta el módulo de la funcionalidad: src/features/{normalized_slug}/")
    if not has_registry:
        errors.append(f"La funcionalidad '{normalized_slug}' no está registrada en src/lib/feature-registry.ts")

    return StructuralValidationResult(
        is_valid=len(errors) == 0,
        errors=tuple(errors),
        missing_page=not has_page or not page_has_export_default,
        missing_slice=not has_slice,
        missing_registry=not has_registry,
    )


def validate_workspace_feature_structure(
    workspace_dir: str | Path,
    feature_slug: str,
    fs_reader: FileSystemReader,
    extra_files: Iterable[str] = (),
    disposition: ImplementationDisposition | str = ImplementationDisposition.CREATE,
) -> StructuralValidationResult:
    """Inspecciona la estructura de la feature en el workspace utilizando el puerto FileSystemReader.

    El dominio permanece puro: no realiza llamadas directas al sistema de archivos ni depende
    de adaptadores de infraestructura concretos.
    """
    disp_str = str(disposition).lower()
    if disp_str == ImplementationDisposition.SKIP or disp_str == "skip":
        return StructuralValidationResult(is_valid=True)

    ws_str = str(workspace_dir).replace("\\", "/").rstrip("/")
    listed = fs_reader.list_files(workspace_dir)
    found_files: set[str] = {f.replace("\\", "/").strip("./") for f in listed}
    found_files.update(f.replace("\\", "/").strip("./") for f in extra_files)

    normalized_slug = feature_slug.strip().lower()
    page_candidates = (
        f"{ws_str}/src/app/{normalized_slug}/page.tsx",
        f"{ws_str}/src/app/{normalized_slug}/page.jsx",
        f"{ws_str}/src/app/{normalized_slug}/page.ts",
        f"{ws_str}/src/app/{normalized_slug}/page.js",
    )
    rel_page_candidates = (
        f"src/app/{normalized_slug}/page.tsx",
        f"src/app/{normalized_slug}/page.jsx",
        f"src/app/{normalized_slug}/page.ts",
        f"src/app/{normalized_slug}/page.js",
    )
    page_content: str | None = None
    for candidate in page_candidates:
        page_content = fs_reader.read_text(candidate)
        if page_content is not None:
            break
    if page_content is None:
        for candidate in rel_page_candidates:
            page_content = fs_reader.read_text(candidate)
            if page_content is not None:
                break

    registry_path = f"{ws_str}/src/lib/feature-registry.ts"
    registry_content = fs_reader.read_text(registry_path)
    if registry_content is None:
        registry_content = fs_reader.read_text("src/lib/feature-registry.ts")

    return validate_feature_structure(
        feature_slug=feature_slug,
        files=found_files,
        registry_content=registry_content,
        page_content=page_content,
        disposition=disposition,
    )
