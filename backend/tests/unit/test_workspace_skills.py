from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kosmo.contracts.sdd.ids import ProjectId
from kosmo.infrastructure.codegen.workspace import (
    DEFAULT_TEMPLATE_DIR,
    LocalWorkspaceManager,
)


@pytest.mark.unit
def test_skills_in_template_exist_and_have_valid_frontmatter() -> None:
    skills_dir = DEFAULT_TEMPLATE_DIR / ".opencode" / "skills"
    assert skills_dir.exists(), f"Skills directory does not exist at {skills_dir}"

    expected_skills = [
        "kosmo-implementation",
        "kosmo-testing",
        "kosmo-drizzle",
        "kosmo-nextjs",
        "kosmo-ui",
    ]

    for skill_name in expected_skills:
        skill_file = skills_dir / skill_name / "SKILL.md"
        assert skill_file.exists(), f"Expected skill '{skill_name}' at {skill_file} is missing."

        content = skill_file.read_text(encoding="utf-8")
        assert content.startswith("---"), f"Skill '{skill_name}' must start with YAML frontmatter."
        assert f"name: {skill_name}" in content, f"Skill '{skill_name}' must declare its name in frontmatter."
        assert "description:" in content, f"Skill '{skill_name}' must declare a description in frontmatter."


@pytest.mark.unit
def test_kosmo_implementation_skill_content() -> None:
    skill_file = DEFAULT_TEMPLATE_DIR / ".opencode" / "skills" / "kosmo-implementation" / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")

    # Clean Architecture & Capas
    assert "Clean Architecture" in content
    assert "Dominio" in content
    assert "Presentación" in content
    assert "src/app" in content
    assert "src/db" in content
    assert "src/lib" in content

    # TypeScript Estricto & Anti-patrones
    assert "Cero `any`" in content
    assert "Anti-patrones" in content
    assert "Checklist de Calidad" in content


@pytest.mark.unit
def test_kosmo_testing_skill_content() -> None:
    skill_file = DEFAULT_TEMPLATE_DIR / ".opencode" / "skills" / "kosmo-testing" / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")

    # TDD & AAA
    assert "Red-Green-Refactor" in content
    assert "AAA" in content
    assert "// Arrange" in content
    assert "// Act" in content
    assert "// Assert" in content

    # Cobertura obligatoria de caminos
    assert "Happy Path" in content or "Camino Feliz" in content
    assert "Error Path" in content or "Camino de Error" in content
    assert "it.each" in content
    assert "factories" in content or "Builders" in content


@pytest.mark.unit
def test_kosmo_drizzle_skill_content() -> None:
    skill_file = DEFAULT_TEMPLATE_DIR / ".opencode" / "skills" / "kosmo-drizzle" / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")

    # Drizzle ORM & SQLite
    assert "Drizzle ORM" in content
    assert "sqliteTable" in content
    assert "$inferSelect" in content
    assert "$inferInsert" in content
    assert "select" in content
    assert "insert" in content
    assert "better-sqlite3" in content
    assert "Raw SQL" in content or "SQL Crudo" in content
    assert "Server Actions" in content
    assert "revalidatePath" in content


@pytest.mark.unit
def test_kosmo_nextjs_skill_content() -> None:
    skill_file = DEFAULT_TEMPLATE_DIR / ".opencode" / "skills" / "kosmo-nextjs" / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")

    # Next.js 16 & Server Components
    assert "Server Components por Defecto" in content
    assert "'use client'" in content
    assert "NextResponse.json" in content
    assert "Bootstrap 5" in content
    assert "cn(" in content
    assert "Server Actions" in content
    assert "revalidatePath" in content


@pytest.mark.unit
def test_kosmo_ui_skill_content() -> None:
    skill_file = DEFAULT_TEMPLATE_DIR / ".opencode" / "skills" / "kosmo-ui" / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")

    # Feature-slices desacoplados y registro de navegación
    assert "src/features/<slug>/" in content
    assert "manifest.ts" in content
    assert "actions.ts" in content
    assert "feature-registry.ts" in content
    assert "Desacople" in content

    # Diseño: Bootstrap 5, arquetipos y anti-IA
    assert "Bootstrap 5" in content
    assert "dashboard" in content or "Dashboard" in content
    assert "Anti-" in content or "anti-" in content
    assert "src/components/ui/" in content
    assert "Español" in content or "español" in content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_generates_all_skills() -> None:
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_skills_test")

        ws = await manager.ensure_workspace(project_id)
        assert ws.workspace_dir is not None
        ws_dir = Path(ws.workspace_dir)

        skills_dir = ws_dir / ".opencode" / "skills"
        assert skills_dir.exists()

        expected_skills = [
            "kosmo-implementation",
            "kosmo-testing",
            "kosmo-drizzle",
            "kosmo-nextjs",
            "kosmo-ui",
            "tdd",
        ]

        for skill_name in expected_skills:
            skill_file = skills_dir / skill_name / "SKILL.md"
            assert skill_file.exists(), f"Generated workspace is missing skill '{skill_name}'"
            rel_path = f".opencode/skills/{skill_name}/SKILL.md"
            assert rel_path in ws.manifest_files


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ensure_workspace_preserves_custom_skills() -> None:
    with tempfile.TemporaryDirectory() as tmp_root:
        manager = LocalWorkspaceManager(workspaces_root=tmp_root, git_init=False)
        project_id = ProjectId("prj_custom_skills")

        # Primera llamada crea las skills por defecto
        ws1 = await manager.ensure_workspace(project_id)
        assert ws1.workspace_dir is not None
        ws_dir = Path(ws1.workspace_dir)

        custom_file = ws_dir / ".opencode" / "skills" / "kosmo-drizzle" / "SKILL.md"
        custom_content = "---\nname: kosmo-drizzle\n---\n# Custom Drizzle Rules\n"
        custom_file.write_text(custom_content, encoding="utf-8")

        # Segunda llamada no debe sobreescribir
        await manager.ensure_workspace(project_id)

        assert custom_file.read_text(encoding="utf-8") == custom_content
