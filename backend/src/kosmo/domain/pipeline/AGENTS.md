# `domain/pipeline/` — Phase Modes, Validadores, Prompts y Registros del Pipeline SDD

## Responsabilidad y Propósito

Este módulo encapsula la lógica de dominio del motor Spec-Driven Development (SDD) para la orquestación de fases de especificación en KOSMO. Forma parte del anillo de dominio puro (capa 2 de la arquitectura hexagonal): sin acceso a I/O, sin dependencias de base de datos ni servicios externos de red.

Responsabilidades principales:
- **Phase Modes (`phase_modes/`)**: Implementaciones concretas del protocolo `PhaseMode` que encapsulan prompts de sistema, configuración de inferencia del LLM (`temperature`, `max_tokens`, `output_type`), construcción de prompts de usuario, validación de salida, retroalimentación para reintentos y construcción de DTOs finales.
- **Validadores de Fase (`phase_validators/`)**: Validadores deterministas que comprueban estructura de documentos, calidad de redacción a nivel de negocio o usuario, ausencia de términos técnicos prohibidos, formato EARS y unicidad semántica mediante distancia Jaccard.
- **Reglas Modulares de Prompts (`prompts/shared_rules.py`)**: Bloques de texto estandarizados reutilizables para garantizar consistencia en directivas de formato, aislamiento entre fases, guardia de upstream y semántica de diffs.
- **Registros de Dominio**:
  - `SkillRegistry`: Registro en memoria de habilidades (`Skill`) que resuelve por nombre o por fase el `PhaseMode` ejecutable.
  - `KnowledgeToolRegistry`: Registro de herramientas de lectura de contexto inyectables al agente LLM con formateo estructurado de ayuda y tolerancia a excepciones.
- **Utilidades de Pipeline**: Resolución unificada de identificadores de características (`feature_resolver.py`), detección heurística de desalineación conversacional entre fases (`phase_detector.py`) y conversión de requisitos a Markdown (`_dict_utils.py`).

---

## Estructura de Archivos y Componentes

```
domain/pipeline/
├── __init__.py                          # Reexporta validadores de estructura y calidad de Descubrimiento
├── _dict_utils.py                       # Sanitización de diccionarios y serialización EARS a Markdown
├── feature_resolver.py                  # Resolución unificada de FeatureId por prefijo o slug
├── knowledge_tool_registry.py            # Registro de herramientas de consulta contextual para LLM
├── phase_detector.py                    # Detección de mismatch conversacional de fase con desempate
├── skill_registry.py                    # Registro y resolución dinámica de Skills y PhaseModes
├── prompts/
│   └── shared_rules.py                  # Reglas reutilizables para prompts de sistema
├── phase_validators/
│   ├── discovery_validator.py            # Validación de 7 secciones, metas, reglas, exclusiones y términos
│   ├── discovery_refine_validator.py     # Verificación de nivel de negocio post-refinamiento
│   ├── features_validator.py             # Estructura, unicidad Jaccard, solapamiento y guardrails de Features
│   └── requirements_refine_validator.py  # Guard de precondición para refinamiento de requisitos
└── phase_modes/
    ├── base_chat_mode.py                # Clase base abstracta para modos conversacionales
    ├── discovery_mode.py                # Generación inicial del documento de Descubrimiento
    ├── discovery_refine_mode.py          # Refinamiento quirúrgico del Descubrimiento
    ├── discovery_chat_mode.py            # Chat conversacional sobre Descubrimiento
    ├── features_mode.py                 # Generación de características (primer lote de 5)
    ├── features_chat_mode.py            # Chat conversacional sobre Características
    ├── ears_mode.py                     # Generación de requisitos EARS por característica
    ├── requirements_chat_mode.py        # Chat conversacional sobre Requisitos
    ├── requirements_refine_mode.py      # Refinamiento quirúrgico de Requisitos EARS
    ├── modelo_mode.py                   # Generación de diagramas de actividad PlantUML con carriles
    ├── consistency_evaluation_mode.py    # Detección de impacto downstream y corrección de artefactos
    └── direct_modification_mode.py       # Aplicación directa de cambios sobre especificaciones
```

---

## Descripción Detallada por Archivo

### 1. `_dict_utils.py` — Sanitización y Serialización EARS

- **`dict_str_keys(d: Any) -> dict[str, Any]`**: Sanitiza diccionarios asegurando que todas las claves sean cadenas de texto (`str`). Retorna diccionario vacío si la entrada no es un diccionario.
- **`extract_requirements_list(content: Any) -> list[dict[str, Any]]`**: Extrae una lista homogénea de diccionarios de requisitos, ya sea que provenga de un diccionario contenedor (`{"requirements": [...]}`) o de una lista directa.
- **`requirements_to_markdown(reqs: list[Any]) -> str`**: Serializa objetos o modelos de requisitos a Markdown estandarizado con separación por bloques (`---`). Formatea cada requisito con su identificador (`### {display_id} {title}`), patrón EARS en negrita, enunciado y tabla de criterios de aceptación con formato BDD (`**Escenario: ...**`, `- **Dado** que ...`, `- **Cuando** ...`, `- **Entonces** ...`).

### 2. `feature_resolver.py` — Resolución de Identificadores de Features

- **`resolve_feature_id(repo: FeatureRepository, project_id: ProjectId, id_or_slug: str) -> FeatureId | None`**:
  - Si `id_or_slug` comienza con el prefijo canónico `feat_`, lo interpreta directamente como `FeatureId`.
  - En caso contrario, consulta las características del proyecto en el repositorio y realiza una búsqueda exacta por `slug`. Retorna `None` si no existe coincidencia.

### 3. `knowledge_tool_registry.py` — Herramientas de Contexto para el Agente

- **`KnowledgeToolDef`** (`dataclass(frozen=True)`): Define los metadatos de una herramienta de conocimiento: `name`, `description` y esquema de `parameters`.
- **`KnowledgeToolRegistry`**:
  - `register(tool_def: KnowledgeToolDef, handler: KnowledgeToolHandler)`: Registra la definición y la función asíncrona de ejecución.
  - `describe_for_llm() -> str`: Genera el bloque de documentación en lenguaje natural con formato `[TOOL: nombre] {"arg": "valor"}` para inyectar en el prompt del sistema.
  - `execute(name: str, tool_input: dict[str, Any]) -> str | None`: Ejecuta la herramienta de forma segura. Captura cualquier excepción imprevista y la convierte en una cadena explicativa de error, protegiendo al agente de caídas.
  - `tool_names` y `defs()`: Expone la lista de nombres y las definiciones en formato compatible con esquemas de herramientas.

### 4. `phase_detector.py` — Detección Heurística de Mismatch de Fase

- **`detect_phase_mismatch(content: str, current_phase: str) -> str | None`**:
  - Analiza el texto del usuario contra un diccionario de palabras clave (`_PHASE_KEYWORDS`) para las fases `descubrimiento`, `caracteristicas` y `requisitos`.
  - **Regla de desempate**: Si la fase actual acumula 2 o más palabras clave presentes en el mensaje, se respeta la fase actual (`None`), evitando falsos positivos cuando el usuario usa vocabulario cruzado.
  - Retorna la fase detectada si difiere de la actual y no se cumple la condición de desempate; de lo contrario retorna `None`.
- **`phase_label(phase_key: str) -> str`**: Traduce la clave normalizada a su etiqueta canónica con acentos (`Descubrimiento`, `Características`, `Requisitos`).

### 5. `skill_registry.py` — Registro Dinámico de Habilidades

- **`SkillRegistry`**:
  - `register(skill: Skill)` / `unregister(name: str)`: Registro y desregistro de habilidades.
  - `get(name: str) -> Skill | None`: Obtiene una habilidad por nombre exacto.
  - `resolve(name: str) -> PhaseMode`: Resuelve directamente el `PhaseMode` asociado; lanza `ValueError` si no existe.
  - `get_for_phase(phase: SpecPhase) -> list[Skill]`: Filtra todas las habilidades configuradas para una fase SDD específica.
  - `resolve_chat_skill(phase: SpecPhase) -> str`: Localiza la habilidad de chat de una fase (convención de sufijo `_chat`). Lanza `ValueError` si no se encuentra.
  - `list_all() -> list[Skill]`: Lista completa de habilidades registradas.

### 6. `prompts/shared_rules.py` — Reglas Compartidas de Prompts

- **`formatting_rules(bold_targets: str) -> str`**: Exige respuesta en español con tildes, separación en párrafos cortos, uso de listas y negritas para elementos clave. Prohíbe bloques monolíticos.
- **`phase_isolation_rule(*, example: str = "") -> str`**: Prohíbe que el chat de una fase modifique documentos pertenecientes a otras fases, instruyendo al agente a redirigir al usuario.
- **`upstream_guard_rule(upstream_documents: str, *, example: str = "") -> str`**: Prohíbe contradecir, reescribir o ampliar el alcance definido por el documento upstream. Si se contradice, ordena rechazar el cambio devolviendo `change_suggestions: null`.
- **`CONVERSATIONAL_NULL_RULE`**: Si el usuario realiza preguntas, comentarios o saludos sin pedir cambios concretos, instruye fijar `change_suggestions: null`.
- **`DIFF_SEMANTICS_RULE`**: Prohíbe copiar el documento completo en `diff_before`. Exige el fragmento mínimo a reemplazar o cadena vacía si es adición pura.
- **`SERVER_APPLIES_RULE`**: Recuerda al LLM que el servidor aplica los cambios de forma automática; el modelo no debe afirmar falsamente que el cambio ya fue aplicado.
- **`NO_EM_DASH_RULE`**: Prohíbe terminantemente el uso del carácter guion largo (`—`), exigiendo puntos, comas o dos puntos.

---

## Validadores por Fase (`phase_validators/`)

### `discovery_validator.py` — Validación Estructural y Cualitativa de Descubrimiento

1. **`validate_discovery_structure(doc: RichTextDocument, min_words_per_section: int = 25) -> ValidationResult`**:
   - Agrupa el contenido por encabezados de nivel <= 2 (los niveles >= 3 se tratan como contenido interno de la sección padre).
   - Verifica la presencia obligatoria de las 7 secciones de `DISCOVERY_SECTIONS`:
     1. `Visión del producto`
     2. `Espacio del problema`
     3. `Actores`
     4. `Propuesta de valor`
     5. `Metas del producto` (mínimo 2 metas numeradas, regex `^\s*\d+\.\s+\S`)
     6. `Reglas de negocio` (mínimo 4 reglas numeradas)
     7. `Alcance` (mínimo 3 exclusiones explícitas bajo bloque `Excluido`, regex `^\s*[-*]\s+\S`)
   - Valida que cada sección contenga al menos 25 palabras.
2. **`validate_discovery_quality(doc: RichTextDocument) -> ValidationResult`**:
   - Escanea cada nodo en busca de términos técnicos prohibidos mediante `detect_technical_terms`.
   - Evalúa ausencia del formato de Historia de Usuario (`_HU_PATTERN_RE = Como... quiero... para...`). El Descubrimiento debe redactarse como declaraciones de negocio verificables.

### `discovery_refine_validator.py` — Nivel de Negocio en Refinamiento

- **`validate_business_level(doc: RichTextDocument) -> ValidationResult`**:
  - Examina tanto encabezados como párrafos del documento refinado para garantizar que ninguna edición introduzca jerga técnica o términos de infraestructura.

### `features_validator.py` — Estructura y Unicidad de Características

1. **`validate_feature_structure(features: Any) -> ValidationResult`**:
   - Valida que la entrada sea una lista no vacía de diccionarios.
   - Campos obligatorios: `number` (entero), `title`, `description`, `origin`.
   - **Límites de longitud**:
     - `title`: mínimo 3 caracteres, máximo 6 palabras (`MAX_TITLE_WORDS = 6`).
     - `description`: mínimo 20 caracteres (`MIN_DESC_CHARS = 20`).
     - `origin`: mínimo 15 caracteres (`MIN_ORIGIN_CHARS = 15`) y debe citar explícitamente al menos una de las secciones de `DISCOVERY_SECTIONS`.
   - **Guardrails**: Comprueba ausencia de términos prohibidos de nivel de feature (`detect_feature_level_violations`) y jerga técnica (`detect_technical_terms`).
2. **`validate_feature_uniqueness(features, existing_titles, existing_features) -> ValidationResult`**:
   - Normaliza texto (remoción de acentos NFKD, puntuación y lista de 36 stopwords comunes).
   - **Similitud Jaccard**:
     - Títulos entre sí: si Jaccard > 0.4, genera error de redundancia semántica.
     - Descripciones entre sí: si Jaccard > 0.5, genera error de redundancia semántica.
     - Títulos generados contra características ya existentes: si Jaccard > 0.4, genera error.
   - **Solapamiento funcional**: Invoca `detect_capability_overlap` para advertencias sobre áreas de capacidad compartida.

### `requirements_refine_validator.py` — Precondición de Refinamiento EARS

- **`validate_refine_input_exists(current_requirements_markdown: str | None) -> ValidationResult`**:
  - Verifica que exista contenido previo de requisitos Markdown antes de permitir una operación de refinamiento.

---

## Modos de Fase (`phase_modes/`)

### 1. `base_chat_mode.py` — Base Conversacional

- Clase base para todos los modos de chat (`DiscoveryChatMode`, `FeaturesChatMode`, `RequirementsChatMode`).
- Parámetros por defecto: `temperature = 0.4`, `max_tokens = 8192`, `output_type = RespuestaChatLLM`.
- `validate_output()`: Verifica que `content` no esté vacío y que cada sugerencia en `change_suggestions` tenga `section`, `description` y `diff_before` no vacíos, y que `diff_before` y `diff_after` no sean idénticos.

### 2. `discovery_mode.py` — Generación de Descubrimiento

- Fase: `SpecPhase.DESCUBRIMIENTO`. `temperature = 0.3`, `max_tokens = 8192`, `output_type = DiscoveryDocument`.
- Herramientas declaradas: `validate_discovery_structure` y `validate_discovery_quality`.
- Prompt de sistema: Establece el rol de analista sénior de negocio, prohíbe User Stories y términos técnicos, define la estructura exacta de las 7 secciones y prohíbe metas basadas en estados emocionales o satisfacción humana.
- `validate_output()`: Aplica `auto_repair_technical_terms` al Markdown generado, lo convierte a `RichTextDocument` y ejecuta validaciones estructurales y de calidad.

### 3. `discovery_refine_mode.py` — Refinamiento de Descubrimiento

- Fase: `SpecPhase.DESCUBRIMIENTO`. `temperature = 0.3`, `max_tokens = 8192`, `output_type = DiscoveryDocument`.
- Especializado en edición quirúrgica del documento manteniendo inalteradas las secciones no afectadas por la instrucción.

### 4. `discovery_chat_mode.py` — Chat sobre Descubrimiento

- Subclase de `BaseChatMode`. Orienta la conversación a refinar la visión, los actores y las reglas de negocio sin saltar a soluciones técnicas.

### 5. `features_mode.py` — Generación de Características

- Fase: `SpecPhase.CARACTERISTICAS`. `temperature = 0.4`, `max_tokens = 8192`, `output_type = FeatureSet`.
- Constante: `FIRST_GENERATION_COUNT = 5` (exactamente 5 características en la primera generación).
- Herramientas: `validate_feature_structure` y `validate_feature_uniqueness`.
- Construcción de entidades: Mapea cada elemento a `Feature` con `id = IdGenerator.generate("feature")`, `number`, `title`, `slug = slugify_spanish(title)`, `description` y `origin`.

### 6. `features_chat_mode.py` — Chat sobre Características

- Subclase de `BaseChatMode`. Permite discutir y sugerir modificaciones sobre los atributos de características existentes (`Titulo`, `Descripcion`, `Origen`).

### 7. `ears_mode.py` — Requisitos en Sintaxis EARS

- Fase: `SpecPhase.REQUISITOS`. `temperature = 0.3`, `max_tokens = 8192`, `output_type = EARSSet`.
- Requisitos generados: 3 a 15 por característica, distribuidos en al menos 4 de las 6 categorías EARS (Ubicuo, Basado en Eventos, Determinado por el Estado, Opcional, Respuesta ante Comportamiento no Deseado, Complejo).
- Valida sintaxis EARS mediante regex, calidad estructural y cobertura de software (`validate_ears_syntax`, `validate_ears_quality`, `validate_ears_software_level`).
- Serializa la salida a Markdown con `requirements_to_markdown`.

### 8. `requirements_chat_mode.py` — Chat sobre Requisitos

- Subclase de `BaseChatMode`. Valida que las modificaciones propuestas apunten a secciones editables (`"Título"`, `"Enunciado EARS"`, `"Criterios de aceptación"`).

### 9. `requirements_refine_mode.py` — Refinamiento de Requisitos

- Fase: `SpecPhase.REQUISITOS`. `temperature = 0.3`, `max_tokens = 8192`, `output_type = RequirementsDocument`.
- Modifica quirúrgicamente requisitos existentes asegurando que los bloques comiencen con `### REQ-`.

### 10. `modelo_mode.py` — Diagramas de Actividad PlantUML

- Fase: `SpecPhase.MODELO`. `temperature = 0.2`, `max_tokens = 8192`, `output_type = DiagramSpec`.
- Exige uso estricto de carriles (`swimlanes`) con sintaxis `|#color|NombreCarril|`.
- Restricciones: máximo 20 nodos de acción, máximo 4 carriles, balance estricto de condicionales (`if`/`endif`) y forks (`fork`/`end merge`).
- Valida la sintaxis con `validate_activity_diagram_syntax`.

### 11. `consistency_evaluation_mode.py` — Detección y Corrección de Inconsistencias

- **`ConsistencyEvaluationMode`**:
  - `temperature = 0.2`, `max_tokens = 16384`, `output_type = ConsistencyDetectionReport`.
  - Analiza cambios upstream y clasifica cada artefacto downstream en una acción (`update`, `delete`, `keep`).
  - Utiliza `_FIDELITY_RULES` y directivas direccionales (`_DIRECTION_DOWNSTREAM`).
- **`ConsistencyCorrectionMode`**:
  - `temperature = 0.2`, `max_tokens = 16384`, `output_type = ConsistencyCorrection`.
  - Redacta la propuesta exacta de corrección (texto sustituto o parche) para los artefactos afectados.

### 12. `direct_modification_mode.py` — Modificación Directa

- Fase configurable (`SpecPhase`). `temperature = 0.1`, `max_tokens = 8192`, `output_type = DirectModificationResult`.
- Aplica cambios directos sobre documentos completos cuando la instrucción del usuario es explícita, o solicita aclaración (`applied: false`) si la instrucción es ambigua.

---

## Tabla Resumen de Phase Modes

| Modo | Fase SDD | Temperatura | Max Tokens | Output Type (Pydantic / DTO) | Tools Disponibles |
|:---|:---|:---:|:---:|:---|:---|
| `DiscoveryMode` | DESCUBRIMIENTO | 0.3 | 8192 | `DiscoveryDocument` | `validate_discovery_structure`, `validate_discovery_quality` |
| `DiscoveryRefineMode` | DESCUBRIMIENTO | 0.3 | 8192 | `DiscoveryDocument` | `validate_business_level` |
| `DiscoveryChatMode` | DESCUBRIMIENTO | 0.4 | 8192 | `RespuestaChatLLM` | Ninguna |
| `FeaturesMode` | CARACTERISTICAS | 0.4 | 8192 | `FeatureSet` | `validate_feature_structure`, `validate_feature_uniqueness` |
| `FeaturesChatMode` | CARACTERISTICAS | 0.4 | 8192 | `RespuestaChatLLM` | Ninguna |
| `EARSMode` | REQUISITOS | 0.3 | 8192 | `EARSSet` | `validate_ears_syntax`, `validate_ears_quality`, `validate_ears_software_level` |
| `RequirementsChatMode` | REQUISITOS | 0.4 | 8192 | `RespuestaChatLLM` | Ninguna |
| `RequirementsRefineMode` | REQUISITOS | 0.3 | 8192 | `RequirementsDocument` | Ninguna |
| `ModeloMode` | MODELO | 0.2 | 8192 | `DiagramSpec` | `validate_activity_diagram_syntax` |
| `ConsistencyEvaluationMode` | Transversal | 0.2 | 16384 | `ConsistencyDetectionReport` | `get_requirements_for_feature`, `get_diagram_for_feature` |
| `ConsistencyCorrectionMode` | Transversal | 0.2 | 16384 | `ConsistencyCorrection` | Ninguna |
| `DirectModificationMode` | Configurable | 0.1 | 8192 | `DirectModificationResult` | Ninguna |

---

## Constantes y Valores Clave

| Constante | Valor | Archivo | Propósito |
|:---|:---:|:---|:---|
| `FIRST_GENERATION_COUNT` | `5` | `features_mode.py` | Cantidad exacta de características en primera generación |
| `MAX_TITLE_WORDS` | `6` | `features_validator.py` | Límite máximo de palabras en títulos de características |
| `MIN_TITLE_CHARS` | `3` | `features_validator.py` | Longitud mínima de título de característica |
| `MIN_DESC_CHARS` | `20` | `features_validator.py` | Longitud mínima de descripción de característica |
| `MIN_ORIGIN_CHARS` | `15` | `features_validator.py` | Longitud mínima de justificación de origen |
| Umbral Jaccard títulos | `0.4` | `features_validator.py` | Límite de similitud léxica antes de error por redundancia |
| Umbral Jaccard descripciones | `0.5` | `features_validator.py` | Límite de similitud léxica antes de error por redundancia |
| `MIN_GOALS` | `2` | `discovery_validator.py` | Mínimo de metas numeradas en Descubrimiento |
| `MIN_RULES` | `4` | `discovery_validator.py` | Mínimo de reglas de negocio en Descubrimiento |
| `MIN_EXCLUSIONS` | `3` | `discovery_validator.py` | Mínimo de exclusiones bajo sección Alcance |
| `min_words_per_section` | `25` | `discovery_validator.py` | Mínimo de palabras por cada una de las 7 secciones |
| Umbral desempate de fase | `≥ 2` | `phase_detector.py` | Palabras clave en fase actual para evitar cambio erróneo |
| `temperature` modificación directa | `0.1` | `direct_modification_mode.py` | Máximo determinismo al editar documentos |

---

## Reglas de Implementación y Mantenimiento

1. **Aislamiento de Dominio Puro**: Este módulo no debe importar módulos de `infrastructure/` ni `application/`. Solo interactúa con `contracts/` y submódulos hermanos de `domain/`.
2. **Encapsulación de Prompts**: Todo prompt de sistema pertenece a su respectivo `PhaseMode`. No crear plantillas huérfanas en otros módulos. Las reglas reutilizables deben residir exclusivamente en `prompts/shared_rules.py`.
3. **Validadores no Arrojan Excepciones**: Todos los validadores deben retornar instancias de `ValidationResult`. La decisión de reintento o fallo es potestad de la capa de aplicación (`KOSMOAgent`).
4. **Few-Shot Examples**: Los ejemplos de referencia se cargan vía `domain.sdd.few_shot.loader` con caché LRU e inyección en el prompt de sistema del modo correspondiente.
5. **Inmutabilidad de Registros en Runtime**: `SkillRegistry` se inicializa y puebla durante el arranque en la raíz de composición (`composition/skill_registration.py`). No debe mutarse durante el manejo de peticiones concurrentes.
6. **Tolerancia a Fallos en Knowledge Tools**: `KnowledgeToolRegistry.execute()` debe capturar cualquier excepción imprevista producida por los adaptadores y devolver un mensaje descriptivo sin interrumpir la ejecución del pipeline.
7. **Resolución Única de Identificadores**: `feature_resolver.resolve_feature_id` es el mecanismo canónico para resolver si una cadena corresponde a un ID o a un slug. No duplicar lógica de inspección de prefijos `feat_` en enrutadores o casos de uso.

---

## Directrices de Seguridad

- **Prevención de Inyección de Prompts**: Las instrucciones del usuario deben ser validadas en la capa de aplicación mediante `sanitize_user_instructions` antes de llegar a los modos de fase.
- **Sin Ejecución de Código Arbitrario**: Los modos de fase procesan texto estructurado mediante Pydantic. Ninguna salida del modelo se evalúa con `eval()`, `exec()` ni intérpretes dinámicos.
- **Tolerancia y Truncamiento de Errores**: La información interna del sistema que devuelven las herramientas de conocimiento se limita en caracteres para evitar saturación de la ventana de contexto y fuga de datos sensibles.
