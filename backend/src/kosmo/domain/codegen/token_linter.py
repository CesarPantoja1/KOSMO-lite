from __future__ import annotations

import re
from dataclasses import dataclass, field

HEX_COLOR_PATTERN = re.compile(
    r"""(?:style\s*=\s*\{\{[^}]*?(?:color|background|border)\s*:\s*["'])(#[0-9a-fA-F]{3,6})["']"""
)
TAILWIND_PROHIBITED_CLASSES = (
    "bg-blue-",
    "text-blue-",
    "bg-red-",
    "text-red-",
    "bg-green-",
    "text-green-",
    "bg-gray-",
    "text-gray-",
    "items-center",
    "justify-between",
    "space-y-",
    "space-x-",
)

IGNORED_PATHS = (
    "src/lib/site.ts",
    "src/lib/design-tokens.ts",
    "src/app/globals.css",
)


@dataclass(frozen=True)
class TokenLintResult:
    is_valid: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)


def lint_source_for_token_compliance(
    file_path: str,
    content: str,
) -> tuple[list[str], list[str]]:
    """Verifica si un archivo fuente generado cumple con las normas de tokens y framework."""
    norm_path = file_path.replace("\\", "/").strip("./")
    if any(norm_path.endswith(ignored) for ignored in IGNORED_PATHS):
        return [], []

    errors: list[str] = []
    warnings: list[str] = []

    # 1. Detección de clases de Tailwind en vez de utilidades Bootstrap
    for prohibited in TAILWIND_PROHIBITED_CLASSES:
        if prohibited in content:
            errors.append(
                f"{norm_path}: Detectada clase prohibida de Tailwind CSS ('{prohibited}'). "
                "Usa utilidades de Bootstrap 5 (ej. 'd-flex', 'align-items-center', 'text-primary')."
            )
            break

    # 2. Detección de colores hex hardcoded en estilos inline
    hex_matches = HEX_COLOR_PATTERN.findall(content)
    if hex_matches:
        for hex_code in set(hex_matches):
            warnings.append(
                f"{norm_path}: Detectado color hex hardcoded '{hex_code}'. "
                "Usa variables CSS de tokens (ej. 'var(--app-primary)') o clases semánticas de Bootstrap."
            )

    return errors, warnings


def validate_token_compliance(
    files_content: dict[str, str],
) -> TokenLintResult:
    """Valida un conjunto de archivos generados para comprobar adherencia a los tokens del design system."""
    all_errors: list[str] = []
    all_warnings: list[str] = []

    for file_path, content in files_content.items():
        errs, warns = lint_source_for_token_compliance(file_path, content)
        all_errors.extend(errs)
        all_warnings.extend(warns)

    return TokenLintResult(
        is_valid=len(all_errors) == 0,
        errors=tuple(all_errors),
        warnings=tuple(all_warnings),
    )
