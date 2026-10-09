# `infrastructure/llm/` — Adaptadores de Clientes LLM, Embeddings y Knowledge Tools

## Responsabilidad y Propósito

Este módulo implementa los adaptadores de infraestructura para la interacción con Modelos de Lenguaje (LLM), servicios de embeddings vectoriales y herramientas de contexto (*knowledge tools*) del pipeline de KOSMO dentro de la arquitectura hexagonal:

- **Resolución dinámica de clientes LLM per-User (BYOK)**: Resuelve en tiempo de ejecución si el usuario autenticado tiene configuradas credenciales propias (*Bring Your Own Key*) para OpenAI, Anthropic, Google Gemini o DeepSeek, o si debe utilizar el proveedor predeterminado del sistema. Incluye control de concurrencia global, caché TTL con protección *anti-thundering herd* y rotación LRU de clientes instanciados.
- **Invocación estructurada y tipada vía PydanticAI**: Adaptador robusto que ejecuta completados simples, JSON y modelos tipados de Pydantic v2. Cuenta con un algoritmo propio de escaneo de llaves balanceadas (*balanced brace scanning*) para extraer JSON válido incluso cuando el modelo añade texto conversacional o markdown fences, fallback para esquemas de un solo campo, reintentos con backoff exponencial y timeout estricto.
- **Streaming tipado asíncrono (`stream_typed`)**: Modo dual que permite emitir tokens de texto en tiempo real al frontend vía SSE mientras acumula la salida para validarla y parsearla al esquema Pydantic final.
- **Telemetría y observabilidad**: Registro automático del consumo de tokens de entrada, salida y totales por modelo y usuario autenticado mediante `record_llm_tokens`.
- **Detección y traducción de errores de autenticación**: Detección heurística de claves inválidas, cuotas agotadas o permisos denegados de proveedores de IA para traducirlos a `AIProviderAuthError` RFC 7807 compatible.
- **Generación de embeddings vectoriales**:
  - `OpenAIEmbedder`: Generación remota contra `text-embedding-3-small` (1536 dimensiones) para búsqueda semántica en PostgreSQL (pgvector).
  - `FastembedEmbedder`: Alternativa local sin dependencias de API externa basada en `BAAI/all-MiniLM-L6-v2`, ejecutada en hilos asíncronos (`asyncio.to_thread`) para no bloquear el bucle de eventos.
- **6 Factories de Knowledge Tools**: Herramientas de lectura de contexto inyectables al agente del pipeline SDD para consultar documentos previos, sesiones similares, artefactos downstream, requisitos EARS, diagramas PlantUML y dependencias de trazabilidad.
- **Verificación de conectividad HTTP**: Comprobador sin envío de prompts que consulta endpoints de modelos de los proveedores mediante peticiones HTTP GET limpias.
- **Adaptador No-Op para desarrollo y tests**: Mock completo que devuelve especificaciones sintéticas coherentes (Discovery de 7 secciones, 5 características y requisitos EARS) permitiendo ejecutar el pipeline SDD sin conexión a internet ni consumo de saldo.

---

## Estructura de Archivos y Componentes

```
infrastructure/llm/
├── __init__.py                 # Reexporta HttpAIConnectionTester, NoopLLMClient, PydanticAILLMClient
├── dynamic_llm_client.py       # DynamicUserLLMClient (resolución per-user, semáforo, caché LRU+TTL)
├── pydantic_ai_adapter.py      # PydanticAILLMClient (PydanticAI, extracción JSON, retries, stream_typed)
├── knowledge_tools.py          # 6 factories build_* de herramientas de contexto para el pipeline SDD
├── embedder.py                 # OpenAIEmbedder (text-embedding-3-small, timeout 30s)
├── local_embedder.py           # FastembedEmbedder (BAAI/all-MiniLM-L6-v2, lazy loading en thread)
├── connection_tester.py        # HttpAIConnectionTester (GET endpoints de modelos OpenAI/Anthropic/Google/DeepSeek)
└── noop_adapter.py             # NoopLLMClient (mock con fixtures de Discovery, Features y Requisitos)
```

---

## Arquitectura de Resolución Dinámica per-User (`DynamicUserLLMClient`)

Implementado en [dynamic_llm_client.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/llm/dynamic_llm_client.py).

### Propósito y Funcionamiento
Actúa como fachada única de `LLMClient` para todos los use cases y el pipeline SDD. Evita que las capas de aplicación o dominio tengan que conocer detalles de infraestructura o claves de API.

```
[Pipeline SDD / Use Case]
         │  (invoca complete / complete_typed / stream_typed)
         ▼
[DynamicUserLLMClient]
  ├── 1. current_user_id.get() desde ContextVar de autenticación
  ├── 2. _resolve_config(user_id):
  │        ├── Consulta _config_cache (TTL 60s)
  │        ├── Si venció: Adquiere _config_locks[user_id] (Anti-Thundering Herd)
  │        ├── Double-check en caché
  │        ├── Consulta UserAiConfigRepository en PostgreSQL
  │        ├── Descifra API key con SecretCipher (Fernet AES-128-CBC)
  │        └── Almacena en _config_cache[user_id]
  ├── 3. _resolve_client():
  │        ├── Si provider == "noop" → NoopLLMClient()
  │        ├── Hash de clave: SHA-256(api_key)[:16]
  │        ├── Busca en LRU _clients (capacidad 64)
  │        └── Si miss: build_pydantic_ai_model(...) → instancia PydanticAILLMClient
  └── 4. async with self._semaphore (máximo 15 llamadas globales):
           └── Ejecuta llamada con mapeo a AIProviderAuthError ante 401/403/cuota
```

### Configuración de Modelos por Proveedor (`build_pydantic_ai_model`)
Construye las instancias nativas de modelo de PydanticAI según el proveedor:
- **DeepSeek**: Instancia `OpenAIChatModel` con `OpenAIProvider(base_url="https://api.deepseek.com", api_key=api_key)` y deshabilita explícitamente el modo thinking: `settings=ModelSettings(extra_body={"thinking": {"type": "disabled"}})`.
- **OpenAI**: Instancia `OpenAIChatModel` con `OpenAIProvider(api_key=api_key)`.
- **Anthropic**: Instancia `AnthropicModel` con `AnthropicProvider(api_key=api_key)`.
- **Google / Gemini**: Instancia `GoogleModel` con `GoogleProvider(api_key=api_key)`.
- **Otros / Custom**: Retorna el formato estándar de string `f"{provider}:{model}"`.

### Control de Concurrencia y Cachés
- **Semáforo global**: `asyncio.Semaphore(15)` limita a 15 las operaciones simultáneas hacia LLMs, previniendo saturación de sockets HTTP y límites de tasa (*rate limits*) del proveedor.
- **Caché TTL de configuración**: `_config_cache` con TTL por defecto de `60.0` segundos.
- **Protección Anti-Thundering Herd**: `_config_locks: dict[str, asyncio.Lock]` asegura que ante la expiración simultánea del TTL para un usuario con múltiples peticiones concurrentes, solo una corrutina consulta la base de datos y descifra la clave; las demás leen el valor en el double-check.
- **LRU de Clientes Instanciados**: `_clients: OrderedDict[tuple[str, str, str | None], PydanticAILLMClient]` mantiene hasta `_MAX_CACHED_LLM_CLIENTS = 64` clientes. La clave de caché es `(provider, model, hash_api_key)`. Al superar el límite, descarta el más antiguo (`popitem(last=False)`).
- **Invalidación Manual**: Método `invalidate_cache(user_id)` para purgar inmediatamente la configuración en caché cuando el usuario actualiza sus credenciales en `routers/ai_config.py`.

### Mapeo de Errores de Autenticación
`is_ai_auth_error(exc)` escanea excepciones contra 13 palabras clave (`unauthorized`, `authentication`, `invalid_api_key`, `permission_denied`, `quota`, `insufficient_quota`, `401`, `403`, etc.). Ante coincidencia, traduce la excepción a `AIProviderAuthError`, la cual es serializada como HTTP 401/403 en la capa API con RFC 7807 Problem Details.

---

## Adaptador PydanticAI (`PydanticAILLMClient`)

Implementado en [pydantic_ai_adapter.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/llm/pydantic_ai_adapter.py).

### Ciclo de Ejecución y Parámetros
- **Timeout por defecto**: `_DEFAULT_TIMEOUT_SECONDS = 120` segundos (envuelto en `asyncio.wait_for`).
- **Política de Reintentos**: Usa `tenacity.AsyncRetrying`:
  - Intentos máximos: `_RETRY_ATTEMPTS = 2`.
  - Estrategia de espera: `wait_fixed(retry_wait_seconds)` si se especificó, o `wait_exponential(multiplier=1, min=1, max=5)`.
  - Condición: `retry=retry_if_not_exception_type(ValueError)`. **Nunca reintenta ante `ValueError`** (errores de validación sintáctica de salida).
- **Caché de Agentes**: `_agents: OrderedDict[str, Agent[Any]]` con límite `_MAX_AGENTS = 32`. **La clave de caché es exclusivamente el `system_prompt`**. La temperatura y los tokens se inyectan en tiempo de llamada mediante `ModelSettings(temperature=temperature, max_tokens=max_tokens)` a `agent.run()`.

### Algoritmo de Extracción y Parsing de JSON (`_parse_typed_output`)
Diseñado para maximizar la resiliencia ante modelos que insertan texto conversacional o markdown:
1. **Limpieza de Markdown Fences**: `_extract_json()` elimina bloques ```` ```json ... ``` ```` o ```` ``` ... ``` ````.
2. **Escaneo de Llaves/Corchetes Balanceados (`_extract_balanced`)**:
   - Localiza el primer `{` o `[`.
   - Itera carácter por carácter controlando profundidad de anidamiento (`depth`), cadenas de texto entre comillas (`in_string`) y caracteres de escape (`\\`).
   - Retorna exactamente la subcadena JSON balanceada cuando `depth == 0`.
   - Intenta `output_type.model_validate_json(json_text)`.
3. **Validación Directa**: Si el texto original inicia con `{` o `[`, intenta validación directa.
4. **Fallback para Modelos de Dominio de un Solo Campo**:
   - Modelos como `DiscoveryDocument` (campo `content`), `RequirementsDocument` (campo `content`) o `DiagramSpec` (campo `diagram_syntax`).
   - Si `len(model_fields) == 1`, asigna el texto crudo directamente a ese campo: `output_type.model_validate({field_names[0]: text})`.
   - Si tiene múltiples campos, asigna el texto al campo primario y `None` al resto.
5. Si todas las estrategias fallan, lanza `ValueError("No se pudo convertir la respuesta del LLM a {output_type}")`.

### Tool Calling Nativo (`complete_with_tools`)
- Convierte las definiciones JSON Schema de herramientas en instancias `pydantic_ai.tools.Tool`.
- Cada tool invoca asíncronamente el `tool_handler` inyectado y registra la ejecución en un `ToolCallRecord(name, args, result_snippet)`.
- El snippet del resultado se trunca a 500 caracteres para auditoría ligera.

### Registro de Telemetría
Al completar cualquier invocación (normal o con tools), extrae `result.usage()` y llama a `record_llm_tokens(tokens=usage.total_tokens, model=model_name, user_id=current_user_id.get())`, actualizando métricas de Prometheus y logs estructurados.

---

## Streaming Tipado (`stream_typed` y `StreamedTypedResult`)

Permite alimentar Server-Sent Events (SSE) al cliente web con baja latencia sin perder las garantías de tipado estricto:

1. **Invocación**: `client.stream_typed(prompt, output_type, temperature, max_tokens)`.
2. **Aislamiento de Tools**: Ejecuta el agente en modo texto con `agent.run_stream(prompt.user_prompt, model_settings=...)` dentro de un bloque `asyncio.timeout(120)`. No envía herramientas durante el streaming para evitar bloqueos interactivos.
3. **Consumo de Tokens en Tiempo Real**:
   - El router/servicio consume `streamed_result.stream_text(delta=True)` para enviar fragmentos de texto conforme los emite el LLM.
4. **Parseo Final**:
   - Al finalizar el stream, `await streamed_result.get_data()` invoca `await streamed.get_output()` y ejecuta `_parse_typed_output` sobre la respuesta completa acumulada, retornando la instancia tipada de `output_type`.

---

## Factories de Knowledge Tools (`knowledge_tools.py`)

Implementado en [knowledge_tools.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/llm/knowledge_tools.py).

Provee 6 funciones constructoras que generan tuplas `(KnowledgeToolDef, KnowledgeToolHandler)` para registrar en el `KnowledgeToolRegistry` del pipeline:

| Función Factory | Nombre de Tool | Parámetros de Entrada | Dependencia de Repositorio | Lógica y Formato de Salida | Truncamiento |
|:---|:---|:---|:---|:---|:---|
| `build_get_phase_document` | `get_phase_document` | `phase: SpecPhase`, `project_id: str` | `DocumentRepository` | Si `phase == DESCUBRIMIENTO`, llama a `get_discovery(pid)` y serializa con `document_to_markdown()`. Para otras fases indica usar herramientas de artefactos. | Sin truncar |
| `build_find_similar_sessions` | `find_similar_sessions` | `query: str`, `project_id: str` (opcional) | `AgentMemoryPort`, `Embedder` | Genera embedding de la consulta, busca k-NN (límite 3 sesiones) excluyendo el proyecto actual. Retorna lista con proyecto, fase, llamadas LLM e instrucciones. | Límite 3 sesiones |
| `build_get_downstream_artifacts` | `get_downstream_artifacts` | `feature_id: str` | `FeatureRepository` | Recupera la feature por ID y retorna JSON formateado con `id`, `number`, `title`, `description` y `origin`. | Objeto único |
| `build_get_requirements_for_feature` | `get_requirements_for_feature` | `feature_id: str` | `RequirementRepository` | Llama a `requirement_repo.by_feature_id()`. Retorna el markdown de requisitos EARS de la feature. | Truncado a `4000` chars |
| `build_get_diagram_for_feature` | `get_diagram_for_feature` | `feature_id: str` | `ActivityDiagramRepository` | Llama a `diagram_repo.by_feature_id()`. Retorna la sintaxis PlantUML del diagrama de actividad. | Truncado a `4000` chars |
| `build_get_impact` | `get_impact` | `artifact_id: str` | `TraceabilityRepository` | Llama a `traceability_repo.get_impact(artifact_id)`. Lista artefactos `upstream` (de los que depende) y `downstream` (que dependen de él). | Sin truncar |

---

## Generación de Embeddings Vectoriales

### 1. `OpenAIEmbedder` ([embedder.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/llm/embedder.py))
- **Modelo predeterminado**: `text-embedding-3-small`.
- **Dimensiones**: 1536 (compatible con columna `embedding` en PostgreSQL pgvector).
- **Timeout**: `30` segundos.
- **Truncamiento de entrada**: `text[:8000]` caracteres.
- **Tolerancia a fallos**: Captura cualquier excepción de la API, emite un log de advertencia estructurado (`embedder.failed`) y retorna `None` sin romper el flujo de negocio.
- **Helper de preparación**: `text_for_embedding(output, validation_errors)` genera el texto canónico para indexación combinando los primeros 2000 caracteres de la salida de la sesión con hasta 5 errores de validación formateados.

### 2. `FastembedEmbedder` ([local_embedder.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/llm/local_embedder.py))
- **Modelo predeterminado**: `BAAI/all-MiniLM-L6-v2`.
- **Carga diferida (*Lazy Loading*)**: No importa ni inicializa la librería `fastembed` hasta la primera llamada de embedding.
- **Ejecución Asíncrona sin Bloqueo**: Tanto la carga del modelo como la inferencia se delegan al pool de hilos mediante `asyncio.to_thread(self._lazy_load)` y `asyncio.to_thread(list, embedder.embed([text[:2000]]))`, evitando bloquear el event loop principal de FastAPI.
- **Truncamiento de entrada**: `text[:2000]` caracteres.

---

## Comprobación de Conectividad HTTP (`HttpAIConnectionTester`)

Implementado en [connection_tester.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/llm/connection_tester.py).

Implementa `AIConnectionTester` (de `contracts/ai/ai_config.py`). Verifica las credenciales del usuario antes de guardarlas en base de datos **sin realizar inferencia ni consumir saldo en prompts**:

- **Proveedores bypass**:
  - `AIProvider.KOSMO_DEFAULT`: Retorna éxito inmediato.
  - `AIProvider.CUSTOM`: Retorna éxito inmediato.
- **Validación HTTP por Proveedor**:
  - **OpenAI**: `GET https://api.openai.com/v1/models` con `Authorization: Bearer <api_key>`.
  - **Anthropic**: `GET https://api.anthropic.com/v1/models` con `x-api-key: <api_key>` y `anthropic-version: 2023-06-01`.
  - **Google Gemini**: `GET https://generativelanguage.googleapis.com/v1beta/models/{model}?key=<api_key>`.
  - **DeepSeek**: `GET https://api.deepseek.com/models` con `Authorization: Bearer <api_key>` (con fallback a `/v1/models` si retorna 404).
- **Manejo de Respuestas HTTP**:
  - `200 OK`: Éxito, retorna `TestAIConnectionResult(is_connected=True, detected_model=model, message=...)`.
  - `401 / 403`: Lanza `AIConnectionTestError` ("Clave de API inválida o no autorizada...").
  - `404`: Lanza `AIConnectionTestError` ("El modelo no fue encontrado o la cuenta no tiene permisos...").
  - Timeout / RequestError: Captura `httpx.TimeoutException` y `httpx.RequestError` y lanza `AIConnectionTestError`.
- **Timeout**: `10.0` segundos por defecto.

---

## Cliente de Desarrollo y Pruebas Offline (`NoopLLMClient`)

Implementado en [noop_adapter.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/llm/noop_adapter.py).

No es un simple stub vacío: es un **simulador determinista del pipeline SDD** diseñado para tests unitarios y desarrollo local sin saldo de IA:

- **Respuesta Canónica Combinada (`_NOOP_RESPONSE`)**: Genera un único payload JSON estructurado que contiene:
  - `document`: Markdown de Discovery con las 7 secciones obligatorias ("Visión del producto", "Espacio del problema", "Actores", "Propuesta de valor", "Metas del producto", "Reglas de negocio", "Alcance").
  - `features`: Lista de 5 características con número, título, descripción 4W, slug y origen trazable a metas y reglas.
  - `requirements`: Requisitos EARS canónicos (`REQ-1.1`, ubiquitous) con criterios de aceptación `given/when/then`.
- **Compatibilidad con `complete_typed`**:
  - Si se solicita `output_type is str`, retorna el texto completo.
  - Si se solicita un modelo Pydantic, ejecuta `model_validate(json.loads(response.text))`; cada `PhaseMode.validate_output` del pipeline extrae la sección que necesita.
  - Si el esquema es un contenedor de un solo campo, inyecta la respuesta directa.
- **Soporte de Streaming**: Expone `stream_typed` mediante la clase interna `_NoopStreamed`, emitiendo la respuesta simulada compatible con SSE.

---

## Contratos Implementados (Puertos vs Implementaciones)

| Puerto / Protocolo (`contracts/`) | Clase Concreta de Infraestructura | Archivo de Implementación |
|:---|:---|:---|
| `LLMClient` | `DynamicUserLLMClient` | [dynamic_llm_client.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/llm/dynamic_llm_client.py) |
| `LLMClient` | `PydanticAILLMClient` | [pydantic_ai_adapter.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/llm/pydantic_ai_adapter.py) |
| `LLMClient` | `NoopLLMClient` | [noop_adapter.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/llm/noop_adapter.py) |
| `Embedder` | `OpenAIEmbedder` | [embedder.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/llm/embedder.py) |
| `Embedder` | `FastembedEmbedder` | [local_embedder.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/llm/local_embedder.py) |
| `AIConnectionTester` | `HttpAIConnectionTester` | [connection_tester.py](file:///c:/projects/KOSMO/backend/src/kosmo/infrastructure/llm/connection_tester.py) |

---

## Constantes y Parámetros Operativos

| Constante | Valor | Ubicación | Significado Técnico |
|:---|:---|:---|:---|
| `_MAX_CACHED_LLM_CLIENTS` | `64` | `dynamic_llm_client.py` | Límite LRU de instancias de clientes HTTP instanciados por proveedor/modelo/clave |
| `_max_concurrency` | `15` | `dynamic_llm_client.py` | Semáforo de llamadas simultáneas hacia APIs de LLM externas |
| `_cache_ttl_seconds` | `60.0` s | `dynamic_llm_client.py` | TTL de la configuración de IA resuelta por usuario |
| `_DEFAULT_TIMEOUT_SECONDS` | `120` s | `pydantic_ai_adapter.py` | Timeout para completados y streams de PydanticAI |
| `_MAX_AGENTS` | `32` | `pydantic_ai_adapter.py` | Límite LRU de agentes PydanticAI cacheados por `system_prompt` |
| `_RETRY_ATTEMPTS` | `2` | `pydantic_ai_adapter.py` | Intentos máximos de llamada ante fallos de red en PydanticAI |
| Truncamiento Requirements EARS | `4000` chars | `knowledge_tools.py` | Máximo de caracteres retornado por `get_requirements_for_feature` |
| Truncamiento Diagrama PlantUML | `4000` chars | `knowledge_tools.py` | Máximo de caracteres retornado por `get_diagram_for_feature` |
| Truncamiento Embedding OpenAI | `8000` chars | `embedder.py` | Límite de caracteres enviados a `text-embedding-3-small` |
| Truncamiento Embedding Local | `2000` chars | `local_embedder.py` | Límite de caracteres enviados a FastEmbed |
| Timeout Embedder OpenAI | `30` s | `embedder.py` | Timeout de la petición HTTP a la API de embeddings |
| Timeout Connection Tester | `10.0` s | `connection_tester.py` | Timeout de sondeo HTTP a los endpoints de modelos de proveedores |

---

## Reglas de Implementación y Mantenimiento

1. **Inyección Exclusiva vía `DynamicUserLLMClient`**: Ningún use case ni router debe instanciar `PydanticAILLMClient` directamente. Todas las invocaciones deben transitar por `DynamicUserLLMClient` para respetar el contexto BYOK del usuario autenticado y el límite del semáforo.
2. **Cero Regex para Extracción JSON**: La extracción de JSON estructurado en `pydantic_ai_adapter.py` debe realizarse siempre mediante `_extract_balanced` (análisis de profundidad de corchetes/llaves). Las expresiones regulares fallan con JSON anidado complejo o strings con escapes.
3. **No Reintentar Errores de Validación (`ValueError`)**: En `PydanticAILLMClient._run_with_retry`, `retry_if_not_exception_type(ValueError)` es intencional. Si el modelo devolvió un JSON que no cumple el esquema Pydantic, el reintento debe ser orquestado por el pipeline con un prompt de corrección (`build_retry_prompt`), no por reintento ciego de transporte.
4. **Desactivación de Thinking en DeepSeek**: Al agregar soporte o modelos nuevos de DeepSeek en `build_pydantic_ai_model`, mantener la directiva `extra_body={"thinking": {"type": "disabled"}}` para evitar que el contenido de razonamiento contamine el output tipado esperado por Pydantic.
5. **Aislamiento de Hilos en FastEmbed**: Si se modifica `FastembedEmbedder`, todas las llamadas síncronas de la librería deben envolverse en `asyncio.to_thread` para prevenir el congelamiento del bucle de eventos de FastAPI.
6. **Truncamiento Defensivo en Knowledge Tools**: Las herramientas de conocimiento inyectadas al LLM no deben devolver volcados masivos sin límite. Si se crean nuevas herramientas, limitar su salida para proteger la ventana de contexto.

---

## Directrices de Seguridad y Protección de Credenciales

- **Descifrado Just-in-Time**: Las claves de API de los usuarios se almacenan cifradas en PostgreSQL con Fernet AES-128-CBC. `DynamicUserLLMClient` solo descifra la clave en memoria al momento de construir o renovar el cliente HTTP.
- **Hashing de Claves para Claves de Caché**: La clave del diccionario LRU de clientes no almacena la API key en texto claro; almacena su hash SHA-256 truncado a 16 caracteres (`_hash_api_key(api_key)`).
- **Enmascaramiento en Logs**: Cualquier log estructurado que registre actividad de usuarios o fallos de configuración debe usar `mask_user_id(user_id)` (e.g. `usr_01***9ABC`), asegurando que identificadores o datos personales no queden expuestos.
- **Comprobación de Conectividad Inofensiva**: `HttpAIConnectionTester` nunca envía prompts de prueba que puedan registrar datos de usuario en logs del proveedor de IA. Se limita a consultar catálogos de modelos con peticiones HTTP GET limpias.
