# `domain/sdd/` — Lógica de Dominio SDD: Validación, Diffs, Guardrails e IDs

## Responsabilidad y Propósito

Este módulo contiene el núcleo de lógica de dominio pura del motor Spec-Driven Development (SDD) de KOSMO. Opera estrictamente en la Capa 2 de la arquitectura hexagonal: algoritmos deterministas, funciones puras, cero llamadas de I/O, cero interacción directa con base de datos o APIs de red, y dependencia exclusiva de la biblioteca estándar de Python y los contratos definidos en `contracts/`.

Responsabilidades principales:
- **Generación determinista de identificadores**: Prefijos tipados por entidad combinados con identificadores ULID ordenables lexicográficamente.
- **Defensa en profundidad y guardrails**: Detección de términos técnicos en fases de negocio/usuario, auto-reparación léxica de jerga técnica y defensa contra inyección de prompts y evasión de rol (31 patrones regex).
- **Conversión bidireccional de especificaciones**: Transformación sin pérdida entre Markdown y el Árbol de Sintaxis Abstracta (`RichTextDocument`), junto con validación estructural de secciones mínimas y palabras.
- **Motor de diffing tolerante en 4 niveles**: Aplicación de sugerencias de edición sobre documentos con resolución en cascada (coincidencia exacta, extremos limpios, ventana deslizante normalizada e idempotencia segura).
- **Clasificación semántica de versiones**: Categorización de cambios en Descubrimiento (`COSMETIC`, `SEMANTIC`, `STRUCTURAL`, `BUSINESS_RULE`) evaluando términos comerciales clave.
- **Parsing y serialización de requisitos EARS**: Extracción estructurada de modelos `EARSRequirement` con criterios de aceptación en formato BDD a partir de bloques Markdown `### REQ-X.Y`.
- **Validadores formales de ingeniería**:
  - Requisitos EARS: Sintaxis por categoría (Ubicuo, Basado en Eventos, Determinado por el Estado, Opcional, Respuesta ante Comportamiento no Deseado, Complejo), reglas de calidad (3 a 15 requisitos, mínimo 4 categorías) y cobertura de software.
  - Diagramas de actividad PlantUML: Verificación de etiquetas `@startuml`/`@enduml`, balance estricto de condicionales `if`/`endif` y bifurcaciones `fork`/`end merge`, uso de carriles (`swimlanes`) y control de complejidad ciclomática.
- **Control de consistencia y concurrencia**: Hashing criptográfico SHA-256 de estados de documento para detectar evaluaciones obsoletas (*stale*) y pre-filtrado léxico de artefactos downstream dependientes.
- **Repositorio de ejemplos canónicos (Few-Shot)**: Carga en memoria con caché LRU de plantillas de alta fidelidad para guiar la inferencia de los modelos de lenguaje.

---

## Estructura de Archivos y Componentes

```
domain/sdd/
├── __init__.py                          # Reexporta IdGenerator, guardrails léxicos y converters
├── id_generator.py                      # IdGenerator determinista con 32 prefijos de entidad y ULID
├── output_guardrails.py                 # Detección de términos prohibidos, reparación y filtro anti-inyección
├── document_converters.py               # Markdown ↔ RichTextDocument AST, slugify_spanish y validación
├── chat_edit_applier.py                 # Aplicación de sugerencias de chat a Markdown y atributos
├── plan_diffs.py                        # Diff multi-estrategia en 4 niveles y fusión de cambios
├── discovery_diff.py                    # Clasificación estructural y semántica de versiones de Descubrimiento
├── requirements_markdown.py             # Parser y contador de requisitos EARS en bloques Markdown
├── section_parser.py                    # Extracción de spans (offset inicio/fin) y preservación de encabezados
├── session_title.py                     # Derivación de títulos limpios para sesiones de chat
├── text_normalizer.py                   # Normalización de whitespace y eliminación de metadatos de origen
├── traceability_tracer.py               # Consulta de fases downstream según la matriz unidireccional
├── consistency_snapshot.py              # Cálculo de hash SHA-256 para verificación de frescura
├── consistency_filter.py                # Pre-filtrado léxico de artefactos downstream (52 stopwords)
├── few_shot/
│   ├── __init__.py
│   ├── loader.py                        # Carga de ejemplos canónicos con caché LRU
│   ├── discovery_example.md             # Ejemplo de referencia para Descubrimiento
│   ├── features_example.md              # Ejemplo de referencia para Características
│   ├── ears_example.md                  # Ejemplo de referencia para Requisitos EARS
│   └── modelo_example.md                # Ejemplo de referencia para Modelo PlantUML
└── validators/
    ├── __init__.py
    ├── activity_diagram_validator.py    # Validación sintáctica, balance y métricas de diagramas
    └── ears_validator.py                # Validación de sintaxis EARS, calidad y nivel software
```

---

## Descripción Detallada por Archivo

### 1. `id_generator.py` — Generación Determinista de Identificadores

- **Clase principal**: `IdGenerator`
- **Método**: `generate(entity: str) -> str`
- **Mapeo de prefijos (`_PREFIX_MAP`)**: Contiene exactamente 32 entidades registradas:
  - `project → prj_`, `feature → feat_`, `spec → spec_`, `task → tsk_`, `user → usr_`, `apikey → apk_`, `audit → aud_`, `pipeline → pipe_`, `requirement → req_`, `agent_memory → agm_`, `activity_diagram → dia_`, `knowledge_pattern → kpat_`, `chat_history → chh_`, `chat_message → msg_`, `plan_change → chg_`, `outbox → out_`, `doc_version → dver_`, `trace_edge → ted_`, `user_pref → upf_`, `consistency_evaluation → cev_`, `chat_session → cht_`, `operation → ope_`, `workspace / code_workspace → ws_`, `implementation / feature_implementation → impl_`, `ai_config / user_ai_config → uai_`, `user_integration / integration → uint_`, `project_integration → pint_`, `code_sync_log → csync_`.
- **Estructura resultante**: `{prefix}{ULID}` (ejemplo: `feat_01J8Y...`). Garantiza unicidad temporal y ordenamiento lexicográfico natural. Arroja `ValueError` ante entidades no registradas.

### 2. `output_guardrails.py` — Guardrails Léxicos, Reparación y Anti-Inyección

- **`detect_technical_terms(text: str, section: str = "") -> GuardrailResult`**:
  - Escanea la presencia de términos prohibidos definidos en `PROHIBITED_TERMS` mediante límites de palabra (`\b`).
  - Extrae un contexto circundante de hasta ±30 caracteres por cada violación detectada.
- **`auto_repair_technical_terms(text: str) -> str`**:
  - Aplica un diccionario canónico de 10 sustituciones orientadas al negocio:
    - `"base de datos"` → `"registro y mantenimiento"`
    - `"almacenará en base de datos"` → `"registrará y mantendrá"`
    - `"enviará una petición HTTP"` → `"comunicará a"`
    - `"validará con el servidor"` → `"verificará"`
    - `"consultará la base de datos"` → `"consultará los registros"`
    - `"guardará en la base de datos"` → `"registrará y mantendrá"`
    - `"almacenar en base de datos"` → `"registrar y mantener"`
    - `"en la base de datos"` → `"en los registros del sistema"`
    - `"via API"` / `"a través de API"` → `"mediante la interfaz del sistema"`
- **`detect_feature_level_violations(text: str, section: str = "") -> GuardrailResult`**:
  - Inspecciona la unión de `PROHIBITED_TERMS` y `FEATURE_LEVEL_PROHIBITED_TERMS` (bloquea tanto jerga técnica como conceptos abstractos de solución).
- **`detect_implementation_leaks(requirements: list[dict[str, str]]) -> GuardrailResult`**:
  - Verifica enunciados y respuestas de requisitos para advertir fugas de detalles de implementación.
- **`sanitize_user_instructions(text: str) -> str`**:
  - Valida que la instrucción no exceda `_INSTRUCTION_MAX_LENGTH = 2000` caracteres.
  - Evalúa 31 expresiones regulares compiladas contra inyección de prompts, evasión de sistema y jailbreak (ej. `"ignora las instrucciones"`, `"you are now a"`, `"cambia tu rol a"`, `"[system]"`, `"<|im_start|>"`, `"system:"`, `"[INST]"`). Arroja `ValueError` ante detección.

### 3. `document_converters.py` — Conversión AST ↔ Markdown y Normalización

- **`slugify_spanish(text: str) -> str`**:
  - Normaliza texto a NFKD, elimina marcas diacríticas (conservando compatibilidad ASCII), transforma `ñ` en `n`, descarta caracteres especiales y sustituye secuencias de espacios/guiones por un único guion `-`.
- **`document_to_markdown(doc: RichTextDocument) -> str`**:
  - Serializa nodos `DocumentNode` y marcas tipográficas (`TextMark`: negrita, cursiva, código, enlaces) a formato Markdown estándar con doble salto de línea entre bloques.
- **`markdown_to_document(markdown: str) -> RichTextDocument`**:
  - Deserializa Markdown a una estructura jerárquica de nodos `heading` (con `SectionHeading` detallando nivel y slug generado) y nodos `paragraph`.
- **`coerce_markdown_output(raw_output: object) -> str`**:
  - Extrae de manera segura el contenido textual desde entradas heterogéneas (`None`, `str`, o `dict` con claves `document` o `raw_text`). Retorna cadena vacía ante valores nulos, evitando generar la cadena `"None"`.
- **`validate_document_structure(doc: RichTextDocument, required_sections: list[str], min_words_per_section: int = 50) -> tuple[bool, list[str]]`**:
  - Verifica la presencia de encabezados obligatorios y que cada sección cumpla con un conteo mínimo de palabras (por defecto 50).

### 4. `chat_edit_applier.py` — Aplicación Quirúrgica de Sugerencias de Chat

- **`apply_markdown_suggestion(markdown, *, section, diff_before, diff_after) -> str | None`**:
  - Aplica parches sobre el documento Markdown invocando `apply_change_diff`.
- **`apply_feature_attribute(current, *, diff_before, diff_after) -> str | None`**:
  - Permite sustituir valores de atributos específicos de una característica (`title`, `description`, `origin`), manejando adiciones puras (`diff_before` vacío), reemplazo exacto, idempotencia y sustitución con espacios normalizados (`_replace_normalized`).
- **`check_fragment_terms(phase: SpecPhase, fragment: str) -> list[str]`**:
  - Identifica términos prohibidos en fragmentos generados durante el chat según la fase activa (`DESCUBRIMIENTO` verifica términos técnicos; `CARACTERISTICAS` verifica violaciones de nivel de característica).

### 5. `plan_diffs.py` — Motor de Diffs Multi-Estrategia

- **`apply_change_diff(markdown: str, *, before: str, after: str, section: str | None = None) -> str | None`**:
  - Ejecuta la sustitución tolerante en cascada a través de cuatro niveles:
    1. **Nivel 1 (Coincidencia exacta)**: `norm_before in norm_text`.
    2. **Nivel 2 (Extremos limpios)**: `norm_before.strip() in norm_text`. Si la línea queda vacía tras la eliminación, limpia saltos de línea redundantes.
    3. **Nivel 3 (Ventana deslizante normalizada)**: Descompone el texto y el bloque objetivo en líneas y compara mediante `collapse_whitespace()`, sustituyendo la subsecuencia exacta.
    4. **Nivel 4 (Idempotencia segura)**: Si `after` ya se encuentra presente en el documento y `before` ya no existe, devuelve el texto sin cambios en lugar de fallar.
- **`find_section(markdown: str, section: str) -> tuple[str | None, int, int]`**:
  - Localiza los límites (texto, índice inicial, índice final) de una sección delimitada por encabezados Markdown (`## ...`).
- **`merge_changes_with_diffs(originals: list[AppliedChange], diffs: list[SectionChange]) -> list[AppliedChange]`**:
  - Combina las intenciones de cambio con los diffs reales generados, asignando descripciones contextuales e IDs deterministas `chg_diff_{ULID().hex}`.

### 6. `discovery_diff.py` — Clasificación Semántica de Cambios

- **Enums**:
  - `ChangeType`: `MODIFIED`, `ADDED`, `REMOVED`.
  - `ChangeClass`: `COSMETIC`, `SEMANTIC`, `STRUCTURAL`, `BUSINESS_RULE`.
- **`SectionChange`** (`dataclass(frozen=True)`): Representa la mutación de una sección (`section`, `change_type`, `change_class`, `before`, `after`).
- **Términos comerciales (`_BUSINESS_TERMS`)**: Frozenset con 15 términos económicos y de negocio:
  `precio`, `costo`, `moneda`, `peso`, `unidad`, `plazo`, `porcentaje`, `impuesto`, `descuento`, `garantia`, `reembolso`, `suscripcion`, `factura`, `presupuesto`, `comision`.
- **`diff_discovery_versions(previous: str, current: str) -> list[SectionChange]`**:
  - Divide ambos documentos por encabezados `## `.
  - Clasifica las modificaciones: si difieren únicamente en espacios o puntuación es `COSMETIC`; si cambia la presencia de términos comerciales es `BUSINESS_RULE`; si se añaden/eliminan encabezados es `STRUCTURAL`; de lo contrario es `SEMANTIC`.

### 7. `requirements_markdown.py` — Parser y Serializador EARS

- **`parse_requirements_markdown(markdown, feature_id, feature_number, *, created_at=None) -> list[EARSRequirement]`**:
  - Analiza bloques separados por `### REQ-{feature_number}.{correlativo}`.
  - Extrae título, categoría del patrón EARS (vía `_PATTERN_MAP`), enunciado principal, origen y lista de `AcceptanceCriterion` (con escenarios BDD: `scenario`, `given`, `when`, `then`).
  - Asigna identificadores `RequirementId(IdGenerator.generate("requirement"))`.
- **`parse_requirement_from_markdown(...) -> EARSRequirement | None`**:
  - Parsea un único requisito a partir de un fragmento Markdown con ID prefijado.
- **`count_requirements(markdown: str) -> int`**:
  - Conteo rápido mediante expresión regular del número de requisitos presentes (`### REQ-\d+\.\d+`).

### 8. `section_parser.py` — Spans y Preservación de Encabezados

- **`section_spans(markdown: str) -> list[tuple[str, int, int]]`**:
  - Retorna una lista con la tupla `(título, inicio, fin)` de todas las secciones encontradas en el documento basadas en encabezados `#{1,6}`.
- **`section_heading_preserved(original: str, rewritten: str) -> bool`**:
  - Comprueba de forma insensible a espacios que el primer encabezado del bloque original siga presente en el texto reescrito.

### 9. `session_title.py` — Derivación de Títulos de Sesión

- **`derive_session_title(content: str, max_words: int = 4) -> str`**:
  - Limpia ruido de formato Markdown (`*`, `_`, `#`, `>`, `|`, etc.) y signos de puntuación de la primera interacción del usuario.
  - Selecciona hasta 4 palabras y formatea con mayúscula inicial y minúsculas subsiguientes. Retorna cadena vacía si no existe texto legible.

### 10. `text_normalizer.py` — Normalización y Limpieza de Metadatos

- **`normalize_for_match(text: str) -> str`**:
  - Estandariza retornos de carro (`\r\n` → `\n`), colapsa múltiples espacios horizontales en uno y reduce saltos de línea consecutivos.
- **`strip_origin_line(text: str) -> str`**:
  - Remueve líneas finales que comiencen con `"Origen:"` o `"**Origen:**"`. Esto garantiza que los metadatos de trazabilidad internos del agente no contaminen la descripción funcional persistida.

### 11. `traceability_tracer.py` — Propagación Downstream

- **`trace_downstream_phases(source: SpecPhase) -> list[SpecPhase]`**:
  - Consulta la matriz unidireccional canónica `DOWNSTREAM_TARGETS`:
    - `DESCUBRIMIENTO` → `[CARACTERISTICAS, REQUISITOS, MODELO, IMPLEMENTACION]`
    - `CARACTERISTICAS` → `[REQUISITOS, MODELO, IMPLEMENTACION]`
    - `REQUISITOS` → `[MODELO, IMPLEMENTACION]`
    - `MODELO` → `[IMPLEMENTACION]`
    - `IMPLEMENTACION` → `[]`

### 12. `consistency_snapshot.py` — Hashing Criptográfico de Estados

- **`compute_snapshot_hash(*parts: str) -> str`**:
  - Concatena las cadenas provistas mediante el separador `|` y computa el digest hexadecimal `SHA-256`. Utilizado para garantizar que una propuesta de corrección de consistencia solo se aplique si el artefacto fuente no ha mutado entre la detección y la aplicación.

### 13. `consistency_filter.py` — Pre-filtrado Léxico Downstream

- **`extract_key_terms(changes: list[AppliedChange]) -> set[str]`**:
  - Extrae palabras clave (>= 2 caracteres) a partir de la descripción y los diffs (`before` y `after`) de los cambios aplicados, descartando una lista exhaustiva de 52 stopwords comunes en español.
- **`filter_downstream_artifacts(artifacts, changes) -> list[DownstreamArtifact]`**:
  - Filtra los artefactos cuyo título o descripción contenga al menos uno de los términos clave extraídos.
  - **Mecanismo de seguridad (*fail-safe*)**: Si no se extrae ningún término o ningún artefacto coincide, retorna la lista completa para no perder impactos potenciales.

### 14. `few_shot/loader.py` — Gestor de Ejemplos Canónicos

- **`load_example(phase: SpecPhase) -> str | None`**:
  - Carga el contenido textual del archivo Markdown canónico de la fase mediante `importlib.resources`.
  - Mapeo:
    - `DESCUBRIMIENTO` → `discovery_example.md`
    - `CARACTERISTICAS` → `features_example.md`
    - `REQUISITOS` → `ears_example.md`
    - `MODELO` → `modelo_example.md`
  - Utiliza `@lru_cache(maxsize=8)` para eliminar sobrecarga de lectura en disco durante ejecuciones repetidas.

### 15. `validators/activity_diagram_validator.py` — Validador PlantUML

- **`wrap_diagram_fragment(fragment: str) -> str`**:
  - Asegura que cualquier fragmento de diagrama cuente con las directivas `@startuml` y `@enduml`.
- **`validate_activity_diagram_syntax(diagram: str, ...) -> ValidationResult`**:
  - **Errores sintácticos**:
    - Presencia obligatoria de encabezado `@startuml` y cierre `@enduml`.
    - Balance de condicionales: cantidad de `if` / `if(` debe coincidir exactamente con `endif` / `end if`.
    - Balance de concurrencia: cantidad de `fork` debe coincidir exactamente con `end merge` / `endmerge`.
  - **Advertencias y límites de complejidad**:
    - Presencia recomendada de nodo inicial `start` y nodo final (`stop` o `end`).
    - Presencia obligatoria de carriles/swimlanes (`|NombreCarril|`).
    - Nodos de acción máximos recomendados: 20 (`_DEFAULT_MAX_ACTION_NODES = 20`).
    - Carriles máximos recomendados: 4 (`_DEFAULT_MAX_SWIMLANES = 4`).
    - Nivel de anidamiento máximo recomendado: 3 (`_DEFAULT_MAX_NESTING_DEPTH = 3`).

### 16. `validators/ears_validator.py` — Validador de Requisitos EARS

- **`validate_ears_syntax(requirements: list[Any]) -> ValidationResult`**:
  - Evalúa la estructura léxica del enunciado contra la categoría EARS declarada:
    - `Ubicuo`: Regex `^(el sistema|la aplicación)\s+(shall|debe|deberá)\s+`.
    - `Basado en eventos`: Regex `^(cuando|al|al\s+producirse|al\s+ocurrir|al\s+recibir)\s+`.
    - `Determinado por el estado`: Regex `^(mientras|durante|en\s+estado\s+de|bajo\s+la\s+condición\s+de)\s+`.
    - `Opcional`: Regex `^(donde|si|en\s+caso\s+de\s+que|opcionalmente)\s+`.
    - `Comportamiento no deseado`: Regex `^(si\s+.+\s+(no\s+funciona|falla|error))\s*,?\s*(el sistema)\s+(debe|deberá)\s+`.
    - `Complejo`: Regex `^(mientras|durante)\s+.+\s+(y|cuando|al)\s+`.
- **`validate_ears_quality(requirements: list[Any]) -> ValidationResult`**:
  - Mínimo 3 y máximo 15 requisitos por característica.
  - Requisito de diversidad: al menos 4 categorías EARS distintas en el lote.
  - Enunciado no vacío y mínimo 2 criterios de aceptación por requisito.
- **`validate_ears_software_level(requirements: list[Any]) -> ValidationResult`**:
  - Comprueba que cada criterio de aceptación contenga los campos `scenario`, `given`, `when` y `then` no vacíos.

---

## Constantes y Valores Clave

| Constante | Valor | Archivo | Propósito |
|:---|:---:|:---|:---|
| `_PREFIX_MAP` | 32 entidades | `id_generator.py` | Prefijos canónicos ULID por tipo de entidad |
| `_TECH_REPLACEMENTS` | 10 pares | `output_guardrails.py` | Reemplazos directos de jerga técnica por conceptos de negocio |
| `_INJECTION_PATTERNS` | 31 expresiones regulares | `output_guardrails.py` | Detección de jailbreak e inyección de instrucciones |
| `_INSTRUCTION_MAX_LENGTH` | `2000` caracteres | `output_guardrails.py` | Longitud máxima permitida en entradas de usuario |
| `_BUSINESS_TERMS` | 15 términos | `discovery_diff.py` | Palabras clave para clasificar cambios como `BUSINESS_RULE` |
| `_STOPWORDS` | 52 palabras | `consistency_filter.py` | Filtro de términos irrelevantes en consistencia downstream |
| `_DEFAULT_MAX_ACTION_NODES` | `20` | `activity_diagram_validator.py` | Umbral recomendado de nodos de acción por diagrama |
| `_DEFAULT_MAX_SWIMLANES` | `4` | `activity_diagram_validator.py` | Umbral recomendado de carriles por diagrama |
| `_DEFAULT_MAX_NESTING_DEPTH` | `3` | `activity_diagram_validator.py` | Máximo nivel de anidamiento recomendado en diagramas |
| Rango de requisitos por feature | `3` a `15` | `ears_validator.py` | Cantidad admisible de requisitos EARS por característica |
| Mínimo de categorías EARS | `4` | `ears_validator.py` | Cobertura mínima de patrones sintácticos distintos |
| Mínimo de criterios por requisito | `2` | `ears_validator.py` | Escenarios de aceptación mínimos requeridos por requisito |

---

## Reglas de Implementación y Mantenimiento

1. **Aislamiento Funcional Estricto**: Todo el código de este módulo es puro. Queda estrictamente prohibido introducir llamadas a bases de datos, librerías de red (`httpx`, `urllib`), o importaciones de `application/` o `infrastructure/`.
2. **Registro Centralizado de IDs**: Al crear una nueva entidad de base de datos o DTO que requiera ID único, es obligatorio agregar su prefijo en `IdGenerator._PREFIX_MAP`.
3. **Manejo de Errores en Validadores**: Los validadores nunca deben lanzar excepciones durante el análisis de documentos del usuario; deben devolver instancias de `ValidationResult` con los arrays de `errors` y `warnings` correspondientes. La única excepción es `sanitize_user_instructions`, que arroja `ValueError` como barrera defensiva de seguridad.
4. **Idempotencia de Parches**: La aplicación de diffs debe respetar el orden en cascada de `plan_diffs.py`. No remover el Nivel 4 de idempotencia segura, ya que evita fallos espurios ante reintentos automáticos.
5. **Preservación de Trazabilidad**: En cualquier modificación de requisitos o características, los metadatos de `origin` deben preservarse o actualizarse mediante `text_normalizer.strip_origin_line` y los esquemas de contratos respectivos.

---

## Directrices de Seguridad

- **Defensa contra Prompt Injection**: `sanitize_user_instructions` es el primer filtro de seguridad de la aplicación ante peticiones del usuario. Cualquier nuevo patrón de jailbreak descubierto debe incorporarse en `_INJECTION_PATTERNS`.
- **Sanitización de Salidas y Exclusiones de Jerga**: `output_guardrails.py` previene que detalles internos del sistema (tecnologías de persistencia, endpoints o protocolos) se filtren a documentos de nivel de negocio o usuario.
- **Integridad de Estado con SHA-256**: Los hashes computados por `consistency_snapshot.py` deben validarse en la capa de aplicación antes de aplicar cualquier parche, evitando inconsistencias por condiciones de carrera o ediciones concurrentes.
