from __future__ import annotations

import re
from dataclasses import dataclass

from kosmo.contracts.sdd.feature import Feature
from kosmo.contracts.sdd.ids import FeatureId, ProjectId
from kosmo.contracts.sdd.repositories import DocumentRepository, FeatureRepository
from kosmo.contracts.sdd.ux_context import (
    BootstrapDesignTokens,
    BusinessArchetype,
    DataDensity,
    ShellPattern,
    UXAnalysisOutput,
    UXContext,
)
from kosmo.domain.codegen.palette_generator import generate_domain_tokens
from kosmo.domain.sdd.document_converters import document_to_markdown

ARCHETYPE_KEYWORDS: dict[BusinessArchetype, frozenset[str]] = {
    BusinessArchetype.STOREFRONT: frozenset(
        {
            "venta",
            "ventas",
            "catalogo",
            "catálogo",
            "inventario",
            "precio",
            "precios",
            "producto",
            "productos",
            "tienda",
            "compra",
            "compras",
            "cliente",
            "clientes",
            "pedido",
            "pedidos",
            "reserva",
            "reservas",
            "carrito",
        }
    ),
    BusinessArchetype.DASHBOARD: frozenset(
        {
            "reporte",
            "reportes",
            "metrica",
            "metricas",
            "métrica",
            "métricas",
            "analitica",
            "analítica",
            "estadistica",
            "estadística",
            "estadisticas",
            "estadísticas",
            "monitoreo",
            "kpi",
            "control",
            "indicador",
            "indicadores",
            "gasto",
            "gastos",
            "saldo",
            "saldos",
            "balance",
            "balances",
            "finanzas",
            "financiero",
        }
    ),
    BusinessArchetype.WORKFLOW: frozenset(
        {
            "flujo",
            "aprobacion",
            "aprobación",
            "proceso",
            "etapa",
            "etapas",
            "estado",
            "estados",
            "gestion",
            "gestión",
            "tramite",
            "trámite",
            "solicitud",
            "solicitudes",
            "auditoria",
            "auditoría",
            "seguimiento",
        }
    ),
    BusinessArchetype.CONTENT: frozenset(
        {
            "contenido",
            "articulo",
            "artículo",
            "articulos",
            "artículos",
            "publicacion",
            "publicación",
            "blog",
            "documento",
            "documentos",
            "noticia",
            "noticias",
            "educativo",
            "curso",
            "cursos",
            "leccion",
            "lección",
        }
    ),
}

THEME_TOKENS_BY_ARCHETYPE: dict[BusinessArchetype, BootstrapDesignTokens] = {
    BusinessArchetype.DASHBOARD: generate_domain_tokens(BusinessArchetype.DASHBOARD),
    BusinessArchetype.STOREFRONT: generate_domain_tokens(BusinessArchetype.STOREFRONT),
    BusinessArchetype.WORKFLOW: generate_domain_tokens(BusinessArchetype.WORKFLOW),
    BusinessArchetype.CONTENT: generate_domain_tokens(BusinessArchetype.CONTENT),
    BusinessArchetype.SAAS_TOOL: generate_domain_tokens(BusinessArchetype.SAAS_TOOL),
}


@dataclass(frozen=True)
class UXAnalysisInput:
    feature_id: FeatureId
    project_id: ProjectId


def classify_archetype(discovery_text: str, feature_title: str = "", feature_desc: str = "") -> BusinessArchetype:
    """Clasifica el arquetipo de negocio determinísticamente mediante conteo de keywords."""
    combined = f"{discovery_text} {feature_title} {feature_desc}".lower()
    words = set(re.findall(r"\w+", combined))

    scores: dict[BusinessArchetype, int] = {arch: len(words & kw) for arch, kw in ARCHETYPE_KEYWORDS.items()}

    best_arch = max(scores, key=lambda k: scores[k])
    if scores[best_arch] > 0:
        return best_arch

    return BusinessArchetype.SAAS_TOOL


class UXAnalyzerUseCase:
    """Analizador determinista y enriquecedor de UX y tokens de diseño visual."""

    def __init__(
        self,
        document_repo: DocumentRepository | None = None,
        feature_repo: FeatureRepository | None = None,
    ) -> None:
        self._document_repo = document_repo
        self._feature_repo = feature_repo

    async def execute(self, input_data: UXAnalysisInput) -> UXAnalysisOutput:
        discovery_md = ""
        if self._document_repo is not None:
            discovery_doc = await self._document_repo.get_discovery(input_data.project_id)
            if discovery_doc is not None:
                discovery_md = document_to_markdown(discovery_doc)

        feature: Feature | None = None
        if self._feature_repo is not None:
            feature = await self._feature_repo.by_id(input_data.feature_id)

        feature_title = feature.title if feature else ""
        feature_desc = feature.description if feature else ""

        archetype = self.classify_archetype(discovery_md, feature_title, feature_desc)
        target_users = self._extract_actors(discovery_md)
        primary_goals = self._extract_goals(discovery_md)

        shell_pattern, data_density, components, prohibited, layout_guide, rationale = self._derive_ux_rules(
            archetype, feature_title, feature_desc
        )

        # Generación de tokens visuales adaptativos según el arquetipo y texto de descubrimiento
        seed_context = f"{discovery_md} {feature_title} {feature_desc}".strip()
        tokens = generate_domain_tokens(archetype, seed_text=seed_context)

        ux_context = UXContext(
            archetype=archetype,
            shell_pattern=shell_pattern,
            data_density=data_density,
            target_users=tuple(target_users),
            primary_goals=tuple(primary_goals),
            recommended_components=tuple(components),
            prohibited_patterns=tuple(prohibited),
            layout_guideline=layout_guide,
            rationale=rationale,
            tokens=tokens,
        )

        prompt_block = self._build_prompt_block(ux_context)

        return UXAnalysisOutput(ux_context=ux_context, prompt_block=prompt_block)

    def classify_archetype(
        self, discovery_text: str, feature_title: str = "", feature_desc: str = ""
    ) -> BusinessArchetype:
        return classify_archetype(discovery_text, feature_title, feature_desc)

    def _classify_archetype(self, discovery_text: str, feature_title: str, feature_desc: str) -> BusinessArchetype:
        return classify_archetype(discovery_text, feature_title, feature_desc)

    def _extract_actors(self, discovery_text: str) -> list[str]:
        actors: list[str] = []
        if "## Actores" in discovery_text:
            section = discovery_text.split("## Actores")[1].split("##")[0]
            for line in section.split("\n"):
                line = line.strip()
                if line.startswith("-") or line.startswith("*"):
                    clean = line.lstrip("-* ").replace("**", "").strip()
                    if clean:
                        actors.append(clean)
        return actors[:5]

    def _extract_goals(self, discovery_text: str) -> list[str]:
        goals: list[str] = []
        if "## Metas del producto" in discovery_text:
            section = discovery_text.split("## Metas del producto")[1].split("##")[0]
            for line in section.split("\n"):
                line = line.strip()
                if re.match(r"^\d+\.", line) or line.startswith("-"):
                    clean = re.sub(r"^\d+\.\s*", "", line).lstrip("-* ").replace("**", "").strip()
                    if clean:
                        goals.append(clean)
        return goals[:5]

    def _derive_ux_rules(
        self, archetype: BusinessArchetype, _feature_title: str, _feature_desc: str
    ) -> tuple[ShellPattern, DataDensity, list[str], list[str], str, str]:
        if archetype == BusinessArchetype.DASHBOARD:
            return (
                ShellPattern.SIDEBAR,
                DataDensity.HIGH,
                [
                    "PageHeader",
                    "Stat",
                    "DataTable",
                    "Table",
                    "Card",
                    "Dropdown",
                    "BadgeStatus",
                    "Select",
                    "Button",
                    "Toast",
                    "Skeleton",
                ],
                [
                    "Grid de cards como vista de datos principal",
                    "Hero banner publicitario",
                    "Textos genéricos o lorem ipsum",
                    "Navegación horizontal exclusiva",
                ],
                "Usa PageHeader con acciones principales a la derecha, fila de KPIs (Stat) arriba, "
                "y DataTable / Table estructurada con filtros (Select / Input) para los registros. "
                "Evita Cards repetitivas.",
                "El dominio contiene métricas, balances o reportes operativos con alta densidad de información.",
            )
        if archetype == BusinessArchetype.STOREFRONT:
            return (
                ShellPattern.TOP_NAV,
                DataDensity.LOW,
                [
                    "PageHeader",
                    "Card",
                    "CardGrid",
                    "Drawer",
                    "Badge",
                    "Button",
                    "Input",
                    "Modal",
                    "Pagination",
                    "Toast",
                    "EmptyState",
                ],
                [
                    "Tablas densas de backoffice sin imágenes ni resúmenes",
                    "Sidebar abrumador de administración",
                    "Interfaces grises sin acentos de color atractivos",
                ],
                "Usa PageHeader claro, filtros por categoría arriba y un grid de Cards con imágenes/iconos, "
                "precios/cantidades y botón de acción principal bien visible.",
                "El dominio está orientado a catálogo, reservas o productos con interacción de selección y compra.",
            )
        if archetype == BusinessArchetype.WORKFLOW:
            return (
                ShellPattern.SIDEBAR,
                DataDensity.MEDIUM,
                [
                    "PageHeader",
                    "Steps",
                    "Card",
                    "Timeline",
                    "BadgeStatus",
                    "Input",
                    "Select",
                    "Switch",
                    "Textarea",
                    "Button",
                    "Alert",
                    "Toast",
                ],
                [
                    "Formularios largos en una sola columna sin pasos ni agrupamiento",
                    "Ausencia de feedback visual de estado (BadgeStatus)",
                    "Ocultar el progreso de la tarea",
                ],
                "Estructura la pantalla con Steps si es un flujo secuencial, usa Card agrupadas con títulos "
                "claros para cada sección de datos, Timeline para auditoría y BadgeStatus para indicar el estado.",
                "El dominio requiere ejecución de trámites, aprobaciones o etapas con trazabilidad de estado.",
            )
        if archetype == BusinessArchetype.CONTENT:
            return (
                ShellPattern.MINIMAL,
                DataDensity.LOW,
                ["PageHeader", "Card", "Tabs", "Accordion", "Breadcrumb", "Separator", "Badge", "Button", "EmptyState"],
                [
                    "Tablas compactas de datos numéricos",
                    "Exceso de botones y controles por pantalla",
                ],
                "Prioriza la legibilidad tipográfica en un contenedor centrado (col-lg-8 mx-auto), "
                "organiza el contenido por Tabs, Accordion o secciones limpias.",
                "El dominio es de documentación, artículos o contenido informativo.",
            )

        return (
            ShellPattern.TOP_NAV,
            DataDensity.MEDIUM,
            [
                "PageHeader",
                "Card",
                "DataTable",
                "Table",
                "CommandPalette",
                "Dropdown",
                "Input",
                "Button",
                "Badge",
                "Alert",
                "Toast",
                "EmptyState",
            ],
            [
                "Diseños sobrecargados",
                "Textos de bienvenida genéricos",
            ],
            "Estructura funcional directa: PageHeader con título, formulario o listado de registros con DataTable, "
            "acciones claras y validación visible.",
            "Aplicación SaaS con herramientas y utilidades interactivas.",
        )

    def _build_prompt_block(self, ctx: UXContext) -> str:
        prohibited_list = "\n".join(f"- {p}" for p in ctx.prohibited_patterns)
        components_list = ", ".join(ctx.recommended_components)

        return (
            "## Directivas de UX y Arquitectura de UI (NON-NEGOTIABLE)\n"
            f"- **Arquetipo de negocio:** `{ctx.archetype.value}`\n"
            f"- **Personalidad visual:** `{ctx.tokens.brand_personality}`\n"
            f"- **Navegación / Shell:** `{ctx.shell_pattern.value}`\n"
            f"- **Densidad de datos requerida:** `{ctx.data_density.value}`\n"
            f"- **Design Tokens:** Definidos en `src/lib/design-tokens.ts` e inyectados en `src/app/globals.css`. "
            f"Color primario: `{ctx.tokens.primary_color}`, secundario: `{ctx.tokens.secondary_color}`, "
            f"acento: `{ctx.tokens.accent_color}`. "
            "Usa clases semánticas de Bootstrap (`text-primary`, `bg-success`, `btn-primary`) o "
            "variables CSS (`var(--app-*)`). PROHIBIDO inventar colores hex arbitrarios.\n"
            f"- **Componentes del Design System recomendados:** `{components_list}`\n"
            f"- **Pauta de Layout:** {ctx.layout_guideline}\n"
            f"- **Fundamento de Diseño:** 100% Bootstrap 5 (clases `container`, `row`, `col-*`, `d-flex`, `gap-*`). "
            "PROHIBIDO el uso de Tailwind CSS.\n\n"
            f"### Patrones PROHIBIDOS en esta Feature:\n"
            f"{prohibited_list}\n\n"
            f"**Razonamiento UX:** {ctx.rationale}"
        )
