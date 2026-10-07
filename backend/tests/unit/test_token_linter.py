from __future__ import annotations

import pytest

from kosmo.domain.codegen.token_linter import (
    lint_source_for_token_compliance,
    validate_token_compliance,
)

pytestmark = pytest.mark.unit


def test_lint_compliant_code():
    clean_code = """
    import { Button, Card, DataTable } from "@/components/ui";

    export default function MyPage() {
      return (
        <div className="container py-4">
          <Card className="p-3 shadow-sm">
            <h1 className="text-primary fw-bold">Dashboard</h1>
            <Button variant="primary">Guardar</Button>
          </Card>
        </div>
      );
    }
    """
    errors, warnings = lint_source_for_token_compliance("src/app/my-page/page.tsx", clean_code)
    assert len(errors) == 0
    assert len(warnings) == 0


def test_lint_detects_tailwind():
    tailwind_code = """
    export default function MyPage() {
      return (
        <div className="flex items-center justify-between p-4 bg-blue-500">
          <span>Tailwind test</span>
        </div>
      );
    }
    """
    errors, warnings = lint_source_for_token_compliance("src/app/test/page.tsx", tailwind_code)
    assert len(errors) > 0
    assert "Tailwind CSS" in errors[0]


def test_lint_detects_hardcoded_hex():
    hex_code = """
    export default function MyPage() {
      return (
        <div style={{ backgroundColor: "#ff5500", color: "#112233" }}>
          <span>Custom hex</span>
        </div>
      );
    }
    """
    errors, warnings = lint_source_for_token_compliance("src/app/test/page.tsx", hex_code)
    assert len(warnings) >= 1
    assert any("#ff5500" in w or "#112233" in w for w in warnings)


def test_lint_ignores_design_tokens_file():
    token_file_content = """
    export const designTokens = {
      colors: { primary: "#0f766e" }
    };
    """
    errors, warnings = lint_source_for_token_compliance("src/lib/design-tokens.ts", token_file_content)
    assert len(errors) == 0
    assert len(warnings) == 0


def test_validate_token_compliance_aggregate():
    files = {
        "src/app/page.tsx": '<div className="container text-primary">OK</div>',
        "src/features/foo/components/card.tsx": '<div style={{ color: "#abcdef" }}>Warn</div>',
    }
    res = validate_token_compliance(files)
    assert res.is_valid  # Warnings don't block by default
    assert len(res.warnings) >= 1
