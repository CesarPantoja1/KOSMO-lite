# `domain/codegen/` — Reglas de Dominio Puro para Generación e Integración de Código

## Responsabilidad y Propósito

El módulo `domain/codegen/` concentra la lógica de dominio pura que gobierna la fase de implementación de software en el motor Spec-Driven Development (SDD) de KOSMO.

Opera estrictamente en la Capa 2 (Dominio) de la arquitectura hexagonal:
- **Cero I/O y Cero Async**: No realiza llamadas de red, invocaciones a bases de datos ni lecturas directas del sistema de archivos mediante llamadas nativas del SO. Cualquier inspección de workspace se realiza a través de puertos de lectura (`FileSystemReader`).
- **Determinismo Algorítmico**: Todas las reglas de inferencia de actores, detección de solapamiento semántico de características, cálculo de paletas OKLCH, validación de seguridad de rutas, análisis de AST/regex de linters y validación estructural son funciones puras y predecibles.
- **Integridad de Producto y Workspaces**: Garantiza que el código generado respete la disposición arquitectónica del Product Map (`CREATE`, `EXTEND`, `INTEGRATE`, `COMPOSE`, `SKIP`), previene la sobreescritura de archivos protegidos del workspace y asegura la coherencia visual con Bootstrap 5 prohibiendo el uso inadvertido de utilidades de Tailwind CSS o colores hexadecimales sin parametrizar.

---

## Estructura de Archivos y Componentes

```
domain/codegen/
├── __init__.py                 # Reexporta símbolos públicos (validadores, parsers, paths, plan rules)
├── integration_rules.py        # Inferencia de ProductMap, actores, entidades y disposiciones (CREATE, EXTEND, etc.)
├── palette_generator.py        # Conversor OKLCH -> RGB y generador de tokens visuales Bootstrap por arquetipo
├── parse_validation_output.py  # Parsers deterministas de salida de tsc, eslint, vitest, next build y directivas de fix
├── path_safety.py              # Validación y sanitización estricta de rutas (prevención de Directory Traversal)
├── plan_rules.py               # Validación de ImplementationPlan y protección de PROTECTED_WORKSPACE_FILES
├── registry_edit.py            # Edición sintáctica del registro de características (feature-registry.ts)
├── site_config.py              # Generadores de src/lib/site.ts, src/lib/design-tokens.ts y globals.css
├── structural_validator.py     # Verificación de estructura de archivos (page.tsx, slices, registry) según disposición
└── token_linter.py             # Linter de cumplimiento de design tokens y detección de clases Tailwind prohibidas
```

---

## Descripción Detallada por Archivo

### 1. `integration_rules.py` — Inferencia de ProductMap y Disposiciones de Integración

Este componente analiza semánticamente las características del proyecto para inferir el mapa de producto (`ProductMap`) y determinar cómo debe integrarse una nueva característica respecto al código existente.

- **Normalización de Texto y Tokens (`_normalize_tokens`)**:
  - Aplica normalización Unicode NFKD y remueve acentos.
  - Elimina puntuación mediante `re.sub(r"[^\w\s]", " ", text)`.
  - Filtra palabras de longitud menor o igual a 2 caracteres y una lista de 42 stopwords en español (`_STOPWORDS`: "sistema", "usuario", "permite", "debe", "gestionar", etc.).
- **Detección de Solapamiento (`detect_capability_overlap`)**:
  - Calcula la similitud de Jaccard entre los conjuntos de tokens de dos características (`_jaccard_similarity`).
  - Detecta relaciones de sub-capacidad si la característica contiene palabras clave de paso (`_STEP_KEYWORDS`: "terminos", "condiciones", "consentimiento", "confirmacion", "politicas", "aviso", "captcha", "verificacion").
  - Si la similitud supera `0.35` o se reconoce una sub-capacidad, emite un objeto `OverlapDetection(feature_a_id, feature_b_id, similarity, shared_tokens, is_subcapability, message)`.
- **Extracción de Actores**:
  - `extract_actors_from_discovery(discovery_text)`: Extrae nombres de la sección `## Actores` del documento de descubrimiento.
  - `extract_actors_from_text(origin, description, discovery_actors)`: Cruza el texto contra los actores de descubrimiento o una lista de actores canónicos ("Administrador", "Cliente", "Paciente", "Doctor", "Médico", "Empleado", "Vendedor", "Comprador", "Estudiante", "Profesor", "Usuario"). Si no identifica ninguno, retorna `("General",)`.
  - `extract_actor_from_text`: Retorna el actor principal (primer elemento de la tupla).
- **Inferencia de Entidades de Dominio (`infer_domain_entities`)**:
  - Agrupa tokens presentes en los títulos y descripciones de las características.
  - Los tokens que aparecen en 2 o más características (excluyendo palabras de paso y composición) se declaran como `DomainEntityRef(name, description, table_name, feature_ids)`.
- **Disposiciones de Implementación (`determine_feature_disposition`)**:
  Calcula determinísticamente una de las disposiciones de `ImplementationDisposition`:
  1. `COMPOSE`: Si contiene palabras clave de vista agregada (`_COMPOSITION_KEYWORDS`: "dashboard", "panel", "resumen", "metricas", "kpi", "balance", "vista global", "estadisticas", "consolidado").
  2. `INTEGRATE`: Si contiene `_STEP_KEYWORDS` y se acopla como sub-capacidad dentro del flujo de una característica ya implementada.
  3. `EXTEND`: Si comparte entidades de dominio o tokens con características ya implementadas en el workspace, extendiendo modelos sin duplicar persistencia.
  4. `CREATE`: Característica fundacional que crea su propia página, entidades y módulo aislado.
- **Construcción del ProductMap (`build_product_map`)**:
  Consolida en un `ProductMap` inmutable las entidades inferidas, los actores (`ActorRef`), las capacidades (`CapabilityRef`), los flujos de usuario ordenados (`ProductFlow` y `ProductFlowStep`) y el diccionario de disposiciones por característica (`dispositions`).

### 2. `palette_generator.py` — Paletas de Color OKLCH y Design Tokens Bootstrap

Genera paletas de color matemáticamente coherentes y accesibles para personalizar visualmente el workspace generado según el arquetipo de negocio.

- **Estructura `RGB`**: Tupla nombrada `RGB(r, g, b)` con métodos `to_hex()` (`#rrggbb`) y `to_rgb_str()` (`r, g, b`).
- **Conversión de Espacio de Color `oklch_to_rgb(lightness, c, h_deg)`**:
  - Transforma coordenadas OKLCH (Lightness, Chroma, Hue) a OKLab.
  - Convierte coordenadas OKLab al espacio de conos LMS (L³, M³, S³).
  - Transforma LMS a sRGB lineal mediante matriz estándar.
  - Aplica función de transferencia sRGB (gamma correction) para obtener valores enteros [0, 255].
- **Rangos de Tono por Arquetipo (`ARCHETYPE_HUE_RANGES`)**:
  - `BusinessArchetype.DASHBOARD`: Tonos 240.0° a 265.0° ("analítico, preciso, sobrio").
  - `BusinessArchetype.STOREFRONT`: Tonos 160.0° a 185.0° ("energético, fresco, confiable").
  - `BusinessArchetype.WORKFLOW`: Tonos 215.0° a 235.0° ("ordenado, corporativo, enfocado").
  - `BusinessArchetype.CONTENT`: Tonos 280.0° a 310.0° ("creativo, accesible, claro").
  - `BusinessArchetype.SAAS_TOOL`: Tonos 170.0° a 200.0° ("moderno, eficiente, productivo").
- **Generación de Tokens (`generate_domain_tokens`)**:
  - Varianza determinista basada en el hash de los caracteres de `seed_text`.
  - Calcula colores semánticos con luminancia y croma calibrados:
    - Primario: L=0.52, C=0.15 en `primary_hue`.
    - Secundario: L=0.55, C=0.03 en complementario (`(primary_hue + 180) % 360`).
    - Éxito: L=0.58, C=0.16, H=142.0°.
    - Advertencia: L=0.68, C=0.15, H=75.0°.
    - Peligro: L=0.55, C=0.20, H=27.0°.
    - Acento: L=0.60, C=0.14, H=(primary_hue + 50) % 360.
    - Fondos sutilmente tintados: `body_bg` (L=0.985, C=0.008) y `muted_bg` (L=0.95, C=0.015).
  - Configura radios de borde, tipografías (`system-ui` o serif para `CONTENT`) y clases de densidad de tablas (`table-sm` para dashboards/herramientas vs `table` para tiendas/contenido) en un `BootstrapDesignTokens`.

### 3. `parse_validation_output.py` — Parsers Deterministas de Validación y Directivas de Fix

Parsea la salida de las herramientas del pipeline de verificación (TypeScript, ESLint, Vitest, Next.js build) abstrayendo el formato de texto plano a modelos estructurados.

- **Expresiones Regulares Especializadas**:
  - `_TSC_REGEX`: Captura formato `archivo(line,col): error/warning TSxxxx: mensaje` o `archivo:line:col: error/warning TSxxxx: mensaje`.
  - `_ESLINT_LINE_REGEX` y `_ESLINT_COMPACT_REGEX`: Capturan salidas de ESLint tanto en formato `stylish` multilínea como en formato `compact`.
  - `_VITEST_FAIL_REGEX`, `_VITEST_LOC_REGEX`, `_VITEST_ERROR_REGEX`: Capturan fallos de test suites, trazas de ubicación (`❯ archivo:line:col`) y tipos de aserción (`AssertionError`, `TypeError`, etc.).
  - `_NEXT_LOC_REGEX` y `_NEXT_FILE_REGEX`: Capturan errores de compilación de Next.js y problemas de resolución de módulos (`Module not found`).
- **Funciones de Parseo por Paso**:
  - `parse_tsc_output(raw_output) -> tuple[ValidationErrorDetail, ...]`.
  - `parse_eslint_output(raw_output) -> tuple[ValidationErrorDetail, ...]`.
  - `parse_vitest_output(raw_output) -> tuple[ValidationErrorDetail, ...]`.
  - `parse_next_build_output(raw_output) -> tuple[ValidationErrorDetail, ...]`.
  - `parse_validation_output(step, raw_output)`: Despachador según el `ValidationStep`.
  - `parse_step_output(step, raw_output, exit_code, duration_ms) -> ValidationStepResult`: Ensambla el resultado final evaluando si `exit_code == 0` y no existen errores parseados.
- **Truncamiento para Presupuesto de Tokens (`truncate_error_output`)**:
  - Si la salida supera `max_chars` (por defecto 6000 caracteres), divide el presupuesto en dos mitades conservando el inicio (head) y el final (tail) separados por `... [Output truncated for token budget] ...`.
- **Formateo para Fix Prompt (`format_validation_errors_for_prompt`)**:
  - Agrupa fallos por paso (`### Fallo en paso: TYPECHECK`, `LINT`, etc.) para inyectar en el prompt de reintento del agente de código.
- **Derivación de Directivas de Corrección (`derive_fix_directives`)**:
  - Inspecciona las categorías de fallo y emite directivas priorizadas:
    - `STRUCTURE`: Instrucciones para crear `page.tsx`, `src/features/<slug>/` y registrar el manifest.
    - `IMPORT`: Corrección de rutas relativas o alias `@/` ante errores `Module not found` o `TS2307`.
    - `TYPECHECK`: Corrección de firmas y contratos TypeScript.
    - `TESTS`: Ajuste de lógica en `logic.ts` para satisfacer aserciones de Vitest sin desactivar tests.
    - `LINT`: Limpieza de imports no usados y formato ESLint.
    - `BASE DE DATOS / DRIZZLE`: Ajustes en `src/db/schema.ts` ante referencias a SQLite o Drizzle.
    - `BUILD`: Instrucciones para incluir directiva `'use client'` en componentes interactivos de Next.js.

### 4. `path_safety.py` — Validación y Seguridad de Rutas

Primera línea de defensa del sistema para prevenir vulnerabilidades de Directory Traversal y garantizar que ninguna operación de archivo escape del directorio asignado al workspace.

- **Excepción de Dominio**: `UnsafePathError(ValueError)`.
- **`validate_safe_path(path, workspace_root) -> bool`**:
  - Rechaza rutas vacías o que contengan bytes nulos (`\0`).
  - Rechaza explícitamente cualquier segmento de navegación hacia arriba (`..` en `path.parts`).
  - Rechaza letras de unidad de Windows (`C:`) si el servidor corre en entornos POSIX no-NT.
  - Resuelve ambas rutas de forma absoluta (`.resolve()`) y verifica que `target_resolved.is_relative_to(root_resolved)`.
- **`is_safe_path(path, workspace_root) -> bool`**: Alias directo de `validate_safe_path`.
- **`ensure_safe_path(path, workspace_root) -> Path`**: Valida la ruta y retorna la instancia resuelta de `Path`; lanza `UnsafePathError` si la validación falla.
- **`sanitize_relative_path(path: str) -> str`**:
  - Convierte separadores a barras estándar (`/`).
  - Colapsa secuencias de barras duplicadas (`/+` -> `/`).
  - Remueve prefijos `./` o `/`.
  - Verifica la inexistencia de `..` (lanzando `UnsafePathError`).
  - Retorna una ruta relativa limpia y canónica dentro del workspace.

### 5. `plan_rules.py` — Reglas de Validación de Planes de Implementación

Valida la lista de operaciones de archivo (`ImplementationPlan`) que el modelo de lenguaje propone antes de su ejecución.

- **Archivos Protegidos del Workspace (`PROTECTED_WORKSPACE_FILES`)**:
  Conjunto inmutable (`frozenset`) de 15 archivos de infraestructura que el agente **nunca** puede eliminar:
  ```python
  PROTECTED_WORKSPACE_FILES = frozenset({
      "package.json",
      "tsconfig.json",
      "next.config.ts",
      "next.config.mjs",
      "next.config.js",
      "drizzle.config.ts",
      "vitest.config.ts",
      "eslint.config.mjs",
      "eslint.config.js",
      "tailwind.config.ts",
      "tailwind.config.js",
      "postcss.config.mjs",
      "postcss.config.js",
      "opencode.json",
      "AGENTS.md",
  })
  ```
- **Violaciones de Reglas (`PlanRuleViolationType`)**:
  - `UNSAFE_PATH`: Ruta insegura o que escapa del workspace.
  - `FILE_ALREADY_EXISTS`: Operación `CREATE` sobre un archivo que ya existe en el manifiesto (debe ser `MODIFY`).
  - `FILE_NOT_FOUND`: Operación `MODIFY` o `DELETE` sobre un archivo inexistente en el manifiesto.
  - `DUPLICATE_OPERATION`: Dos o más operaciones dirigidas a la misma ruta en un mismo plan.
  - `EMPTY_OPERATIONS`: Plan sin operaciones de archivo declaradas.
  - `PROTECTED_FILE_MODIFICATION`: Intento de eliminación (`DELETE`) sobre un archivo de `PROTECTED_WORKSPACE_FILES`.
- **Estructuras**: `PlanRuleViolation`, `PlanValidationResult(is_valid, violations, error_summary)` e `InvalidPlanError(ValueError)`.
- **Funciones**:
  - `validate_plan(plan, manifest_files, workspace_root="/workspace") -> PlanValidationResult`.
  - `ensure_valid_plan(plan, manifest_files, workspace_root) -> ImplementationPlan`: Retorna el plan si es válido o lanza `InvalidPlanError` con el resumen consolidado de violaciones.

### 6. `registry_edit.py` — Modificación Sintáctica del Registro de Características

Provee manipulación determinista de código TypeScript sobre `src/lib/feature-registry.ts` para desregistrar características eliminadas o revertidas.

- **Patrón Regex `_IMPORT_PATTERN`**:
  Detecta declaraciones de importación bajo la convención:
  `import { <symbol> } from "@/features/<slug>/manifest";`
  Soporta identificadores con alias (`import { myFeature as feat } ...`).
- **Función `remove_feature_from_registry(content: str, slug: str) -> str`**:
  - Identifica los símbolos exportados por la característica a partir del import.
  - Remueve la línea del import del manifiesto.
  - Remueve las referencias a dichos identificadores dentro de la declaración del array de características registradas.
  - Modo fallback: Si la declaración de importación no sigue la convención exacta, elimina preventivamente cualquier línea que contenga `@/features/{slug}/`.
  - Preserva saltos de línea finales (`_join_preserving_trailing_newline`).

### 7. `site_config.py` — Generación de Configuración del Sitio y CSS

Produce el contenido de los archivos de configuración visual e identidad del proyecto en el workspace.

- **`_typescript_string(value: str) -> str`**: Serializa cadenas de texto a literales TypeScript válidos usando `json.dumps(..., ensure_ascii=False)` para escapar comillas y caracteres de control sin romper acentos ni caracteres internacionales.
- **`format_site_config(name, description, archetype="saas_tool", primary_color="#0f766e") -> str`**:
  - Genera `src/lib/site.ts` exportando la constante inmutable `siteConfig` (`as const`).
  - Restringe `archetype` al tipo unión: `"storefront" | "dashboard" | "workflow" | "saas_tool" | "content"`.
- **`format_design_tokens_ts(tokens: BootstrapDesignTokens, domain="general") -> str`**:
  - Genera `src/lib/design-tokens.ts` exportando el objeto fuertemente tipado `designTokens: DesignTokens`.
  - Estructura secciones de `brand`, `colors`, `typography`, `shape` y `layout` (`shell: "sidebar"`, densidad `"compact"` o `"comfortable"`).
- **`format_globals_css(tokens: BootstrapDesignTokens) -> str`**:
  - Genera `src/app/globals.css`.
  - Incluye `@import "bootstrap/dist/css/bootstrap.min.css";`.
  - Inyecta variables CSS semánticas personalizadas (`--app-primary`, `--app-body-bg`, `--app-radius`, `--app-shadow`, etc.).
  - Sobreescribe las variables CSS de Bootstrap 5 (`--bs-primary`, `--bs-body-font-family`, `--bs-border-radius`, etc.).
  - Provee estilos base universales: `.card`, `.table-responsive`, `.app-sidebar`, animación `@keyframes kosmo-shimmer` con `.kosmo-skeleton`, y el componente de línea de tiempo `.kosmo-timeline` con sus puntos y conectores.

### 8. `structural_validator.py` — Validación de Estructura de Workspace y Features

Verifica que el código generado para una característica cumpla con la arquitectura limpia y convenciones del workspace según su disposición de implementación.

- **Estructura `StructuralValidationResult`**:
  `is_valid: bool`, `errors: tuple[str, ...]`, `missing_page: bool`, `missing_slice: bool`, `missing_registry: bool`.
- **Lógica por Disposición en `validate_feature_structure`**:
  - `SKIP`: Siempre válido (`StructuralValidationResult(is_valid=True)`).
  - `INTEGRATE`: Valida que la sub-capacidad haya generado archivos en su slice (`src/features/<slug>/`) o en `src/domain/`. No exige página `page.tsx` aislada ni entrada independiente en el registro. Si no generó archivos, falla con `missing_slice=True`.
  - `CREATE`, `EXTEND`, `COMPOSE`:
    1. Verifica la existencia de `src/app/<slug>/page.tsx` (o extensiones .jsx, .ts, .js).
    2. Si se suministra el contenido de la página, comprueba la presencia obligatoria de `export default`.
    3. Verifica la existencia de la carpeta del slice `src/features/<slug>/` o archivos en `src/domain/`.
    4. Verifica que el slug de la característica esté registrado en `src/lib/feature-registry.ts`.
- **Inspección sin I/O en `validate_workspace_feature_structure`**:
  - Recibe un puerto `FileSystemReader` (`contracts/sdd/codegen`).
  - Utiliza `fs_reader.list_files` y `fs_reader.read_text` para inspeccionar la estructura sin invocar llamadas al sistema operativo directamente en la capa de dominio.

### 9. `token_linter.py` — Linter de Cumplimiento de Tokens y Detección de Tailwind

Audita los archivos generados en el workspace para asegurar que la presentación visual se construya exclusivamente con Bootstrap 5 y las variables de diseño del proyecto.

- **Detección de Colores Hardcoded (`HEX_COLOR_PATTERN`)**:
  Regex que detecta atributos `style` con propiedades CSS directas (`color`, `background`, `border`) asignadas a valores hexadecimales (`#xxx` o `#xxxxxx`). Genera una advertencia sugiriendo el uso de clases Bootstrap o variables CSS `--app-*`.
- **Clases de Tailwind CSS Prohibidas (`TAILWIND_PROHIBITED_CLASSES`)**:
  Tupla de clases utilitarias de Tailwind prohibidas:
  `"bg-blue-"`, `"text-blue-"`, `"bg-red-"`, `"text-red-"`, `"bg-green-"`, `"text-green-"`, `"bg-gray-"`, `"text-gray-"`, `"items-center"`, `"justify-between"`, `"space-y-"`, `"space-x-"`.
  Su presencia genera un error bloqueante exigiendo sustitutos equivalentes de Bootstrap 5 (`d-flex`, `align-items-center`, `text-primary`, etc.).
- **Rutas Ignoradas (`IGNORED_PATHS`)**:
  `src/lib/site.ts`, `src/lib/design-tokens.ts`, `src/app/globals.css` están exentos del linter, ya que allí residen las definiciones fuente de los tokens.
- **Funciones**:
  - `lint_source_for_token_compliance(file_path, content) -> tuple[list[str], list[str]]`: Retorna tupla de `(errors, warnings)`.
  - `validate_token_compliance(files_content: dict[str, str]) -> TokenLintResult`: Valida en bloque un diccionario de archivos `{ruta: contenido}`.

---

## Flujo de Datos en la Generación de Código

```
[Feature + Contexto de Proyecto]
               │
               ▼
[integration_rules.determine_feature_disposition()]
  ├── Analiza overlap de tokens Jaccard (> 0.35)
  ├── Comprueba palabras clave de composición (COMPOSE) o paso (INTEGRATE)
  ├── Detecta entidades de dominio compartidas (EXTEND)
  └── Emite FeatureDisposition (CREATE, EXTEND, INTEGRATE, COMPOSE, SKIP)
               │
               ▼
[plan_rules.ensure_valid_plan(plan, manifest_files)]
  ├── path_safety.validate_safe_path() (Anti-traversal)
  ├── path_safety.sanitize_relative_path()
  ├── Valida precondiciones CREATE (no existe), MODIFY/DELETE (existe)
  └── Rechaza eliminación de PROTECTED_WORKSPACE_FILES (15 archivos)
               │
               ▼ (Ejecución del Plan por OpenCode / Workspace Manager)
               │
               ▼
[structural_validator.validate_workspace_feature_structure()]
  ├── Inspecciona vía FileSystemReader (pureza de dominio)
  ├── CREATE/EXTEND/COMPOSE: exige page.tsx con export default, slice y registry
  └── INTEGRATE: exige archivos en slice o domain sin exigir page.tsx aislada
               │
               ▼
[token_linter.validate_token_compliance()]
  ├── Prohíbe clases de Tailwind (TAILWIND_PROHIBITED_CLASSES)
  └── Advierte sobre colores hexadecimales hardcoded en estilos inline
               │
               ▼
[parse_validation_output.parse_step_output()]
  ├── Parsea salidas crudas de tsc, eslint, vitest, next build
  ├── Si hay fallos: derive_fix_directives() genera directivas accionables
  └── format_validation_errors_for_prompt() trunca a 6000 caracteres para el agente
```

---

## Constantes y Valores Clave

| Constante / Configuración | Valor | Archivo de Definición | Propósito Operativo |
|---|---|---|---|
| Umbral de Similitud Jaccard | `0.35` | `integration_rules.py` | Detección de solapamiento semántico y sub-capacidades |
| Stopwords en Español | 42 palabras | `integration_rules.py` | Limpieza de ruido lingüístico en títulos y descripciones |
| Palabras Clave de Paso | 8 términos | `integration_rules.py` | Inferencia de sub-capacidades (`_STEP_KEYWORDS`) |
| Palabras Clave de Composición | 9 términos | `integration_rules.py` | Inferencia de vistas agregadoras (`_COMPOSITION_KEYWORDS`) |
| Arquetipos de Negocio | 5 arquetipos | `palette_generator.py` | Rangos de tono Hue en OKLCH (`ARCHETYPE_HUE_RANGES`) |
| Truncamiento Máximo de Errores | `6000` caracteres | `parse_validation_output.py` | Presupuesto de contexto LLM en `truncate_error_output` |
| `PROTECTED_WORKSPACE_FILES` | 15 archivos | `plan_rules.py` | Archivos de configuración protegidos contra eliminación |
| Tipos de Violación de Plan | 6 variantes | `plan_rules.py` | Enumeración `PlanRuleViolationType` |
| Clases Tailwind Prohibidas | 12 patrones | `token_linter.py` | `TAILWIND_PROHIBITED_CLASSES` bloqueantes |
| Rutas Ignoradas por Token Linter | 3 rutas | `token_linter.py` | Exenciones en `IGNORED_PATHS` para definiciones de tokens |

---

## Reglas de Implementación y Mantenimiento

1. **Aislamiento Total de Dominio**: Ningún módulo de `domain/codegen/` puede importar de `infrastructure/` ni de `application/`. El flujo de dependencias hexagonal debe ser estrictamente entrante: `infrastructure` → `application` → `domain` → `contracts`.
2. **Pureza Funcional**: No invocar `open()`, `os.walk()` o `Path.write_text()` directamente en este directorio. Cualquier interacción con el árbol de archivos debe delegarse en puertos (`FileSystemReader`) provistos como argumentos.
3. **Inmutabilidad de `PROTECTED_WORKSPACE_FILES`**: No reducir la lista de archivos protegidos. Cualquier adición de configuración base del workspace (como linters o configuradores de empaquetado) debe registrarse en este frozenset para evitar su eliminación accidental durante rollbacks o limpiezas de características.
4. **Respeto a las Disposiciones del Product Map**: Los validadores estructurales nunca deben exigir `src/app/<slug>/page.tsx` para características clasificadas como `INTEGRATE` o `SKIP`. Modificar esta lógica rompería flujos que añaden pasos o sub-pantallas a vistas ya existentes.
5. **Calibración de Parsers de Salida**: Si se actualizan las versiones de TypeScript, ESLint o Vitest en el template del workspace y cambian sus formatos de diagnóstico, las expresiones regulares en `parse_validation_output.py` deben actualizarse de inmediato para evitar que errores reales sean clasificados erróneamente como pasos exitosos.

---

## Directrices de Seguridad

- **Inviolabilidad de Rutas con `path_safety`**: Las funciones `validate_safe_path` y `ensure_safe_path` son defensas críticas contra ataques de path traversal. Jamás deben omitirse en use cases o adaptadores al resolver operaciones de archivo.
- **Detección de Bytes Nulos y Escapes**: `validate_safe_path` y `sanitize_relative_path` rechazan activamente bytes nulos (`\0`) y secuencias `..` tanto antes como después de la resolución canónica de rutas (`.resolve()`).
- **Escapado Seguro en Generación de Código**: En `site_config.py`, todos los valores suministrados por usuarios (nombres de proyecto, descripciones, etc.) se procesan con `_typescript_string` mediante `json.dumps(..., ensure_ascii=False)` para evitar inyecciones de código TypeScript al interpolar cadenas en plantillas.
- **Fail-Safe en Planes de Implementación**: Si un plan incluye operaciones duplicadas sobre la misma ruta o intenta crear archivos preexistentes, `validate_plan` invalida el plan por completo, forzando un ciclo de auto-reparación antes de ejecutar comandos sobre el disco.
