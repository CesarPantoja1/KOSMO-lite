# `infrastructure/telemetry/` — Observabilidad, Tracing Distribuido y Métricas

## Responsabilidad y Propósito

Este módulo centraliza la infraestructura de observabilidad del backend de KOSMO. Sus responsabilidades técnicas comprenden:
- **Logging estructurado contextual** mediante `structlog`, adaptando la salida según el entorno (`ConsoleRenderer` con colores para `development`, `JSONRenderer` plano para producción/staging).
- **Inyección automática de contexto OpenTelemetry** (`trace_id` de 32 caracteres hex y `span_id` de 16 caracteres hex) en cada evento de log mediante procesadores de structlog.
- **Tracing distribuido y métricas de negocio** mediante `OpenTelemetryProvider`, implementando el puerto formal `TelemetryPort` definido en `contracts/telemetry.py`.
- **Integración con Logfire** para auto-instrumentación de I/O en bases de datos (SQLAlchemy 2.0 async con motor `asyncpg`) y almacenamiento clave-valor (Redis), condicionado a la configuración de token (`send_to_logfire="if-token-present"`).
- **Métricas personalizadas de Prometheus** con protección contra registro duplicado en hot-reload (`ACTIVE_SSE_CONNECTIONS`, `ACTIVE_CODE_RUNNERS`).
- **Exposición del endpoint `/metrics` de Prometheus** mediante `prometheus-fastapi-instrumentator`.

**Principio de diseño:** Ningún caso de uso de la capa de aplicación o dominio importa directamente de este módulo. La aplicación consume exclusivamente los contratos y el decorador `@traced` expuestos en `kosmo.contracts.telemetry`.

---

## Estructura de Archivos y Componentes

```
infrastructure/telemetry/
├── __init__.py      # Reexporta símbolos públicos del subsistema
├── bootstrap.py     # Inicialización de structlog, Logfire, OTel y Prometheus
├── metrics.py       # Definición de Gauges Prometheus para monitoreo en tiempo real
└── otel.py          # Implementación de OpenTelemetryProvider y helper get_current_trace_id
```

---

## Descripción Detallada por Archivo

### 1. `metrics.py` — Métricas Prometheus Personalizadas

- **Función interna**: `_get_or_create_gauge(name: str, documentation: str) -> Any`
  - Consulta el diccionario interno `REGISTRY._names_to_collectors.get(name)`. Si el collector ya existe (por ejemplo, durante reinicios en caliente con Uvicorn o ejecución repetida de suites de prueba), retorna la instancia existente en lugar de crear una nueva.
  - Previene excepciones de tipo `ValueError: Duplicated timeseries in CollectorRegistry`.

- **Métricas expuestas**:
  1. `ACTIVE_SSE_CONNECTIONS` (`kosmo_active_sse_connections`):
     - **Tipo:** Gauge de Prometheus.
     - **Descripción:** *"Número actual de conexiones SSE activas transmitiendo al cliente."*
     - **Consumo:** Se incrementa (`.inc()`) al abrir una conexión SSE de chat o de implementación (`infrastructure/api/async_generation.py:with_heartbeat`), y se decrementa (`.dec()`) en el bloque `finally`.
  2. `ACTIVE_CODE_RUNNERS` (`kosmo_active_code_runners`):
     - **Tipo:** Gauge de Prometheus.
     - **Descripción:** *"Número actual de runners de validación de código ejecutándose concurrentemente."*
     - **Consumo:** Se incrementa (`.inc()`) inmediatamente antes de crear un subproceso de validación (`infrastructure/sandbox/code_runner.py`), y se decrementa (`.dec()`) en el bloque `finally` tras culminar la ejecución o timeout.

---

### 2. `bootstrap.py` — Inicialización del Ecosistema de Observabilidad

Punto central de configuración. Gestiona la inicialización de logging, tracing y métricas en diferentes etapas del ciclo de vida de FastAPI (`infrastructure/api/main.py`).

#### Pipeline de Procesadores de Structlog (`_build_processors`):
1. `structlog.contextvars.merge_contextvars`: Combina variables de contexto por coroutine (`request_id`, `ip_address`, `user_agent`).
2. `structlog.processors.add_log_level`: Inserta el nivel del log (`info`, `warning`, `error`, etc.).
3. `structlog.processors.TimeStamper(fmt="iso", utc=True)`: Marca temporal ISO 8601 en UTC.
4. `structlog.processors.StackInfoRenderer()`: Renderizado de stack traces en errores.
5. `structlog.processors.format_exc_info`: Formateo de excepciones capturadas.
6. `_inject_otel_context`: Extrae el span actual de OpenTelemetry (`trace.get_current_span()`) y, si el contexto es válido, inyecta:
   - `trace_id`: Formato hexadecimal de 32 caracteres (`format(context.trace_id, "032x")`).
   - `span_id`: Formato hexadecimal de 16 caracteres (`format(context.span_id, "016x")`).
7. **Renderizador final según entorno:**
   - Si `settings.env == "development"`: `structlog.dev.ConsoleRenderer(colors=True)` para legibilidad en terminal local.
   - En cualquier otro entorno (producción, staging): `structlog.processors.JSONRenderer()` para ingesta estructurada en sistemas de agregación de logs (Datadog, Loki, CloudWatch).

#### Funciones de Configuración:
- **`_configure_structlog(settings: Settings) -> None`**: Configura `logging.basicConfig` estándar en `sys.stdout` con el nivel definido en `settings.log_level` y vincula structlog con `make_filtering_bound_logger`.
- **`_configure_logfire(settings: Settings) -> None`**: Inicializa Logfire con:
  - `token`: Valor descifrado de `settings.logfire_token`.
  - `service_name`: `settings.otel_service_name`.
  - `environment`: `settings.otel_environment`.
  - `send_to_logfire="if-token-present"`: Si no se provee token en variables de entorno, no realiza envíos remotos a Logfire SaaS.
  - `console=False`: Deshabilita la salida duplicada en consola (manejada exclusivamente por structlog).
- **`configure_telemetry(settings: Settings) -> None`**:
  - Invocada dentro de `lifespan(app)` en `infrastructure/api/main.py`.
  - Ejecuta `_configure_structlog` y `_configure_logfire`.
  - Registra globalmente la instancia activa del proveedor de telemetría llamando a `set_telemetry_provider(OpenTelemetryProvider())` en `contracts/telemetry.py`.
- **`instrument_prometheus(app: FastAPI) -> None`**:
  - Invocada a nivel de módulo en `infrastructure/api/main.py` inmediatamente después de instanciar `app = FastAPI(...)` para asegurar que todos los routers queden instrumentados.
  - Utiliza `prometheus_fastapi_instrumentator.Instrumentator().instrument(app).expose(app)`.
  - Expone el endpoint `/metrics` en la aplicación de manera idempotente (guarda estado en `app.state._kosmo_prometheus_instrumented`).
  - Protegido contra `ImportError` o fallos en entornos de prueba donde el paquete no esté disponible.
- **`instrument_app(settings: Settings, *, app: FastAPI, db_engine: AsyncEngine) -> None`**:
  - Invocada dentro de `lifespan(app)` tras inicializar los componentes de base de datos (`AppContainer`).
  - Idempotente: guarda estado en `app.state._kosmo_instrumented`.
  - `logfire.instrument_sqlalchemy(engine=db_engine)`: Captura trazas y tiempos de consulta SQL en PostgreSQL.
  - `logfire.instrument_redis(capture_statement=False)`: Captura comandos Redis sin registrar el contenido de las claves (evita leak de tokens o datos sensibles).

---

### 3. `otel.py` — Proveedor OpenTelemetry y Helpers de Traza

#### Función `get_current_trace_id() -> str`:
- Obtiene el identificador de la traza activa de OpenTelemetry.
- Si existe un span activo con contexto válido: devuelve su `trace_id` en formato hexadecimal de 32 caracteres (`format(context.trace_id, "032x")`).
- Si no hay span activo o el contexto no es válido: genera y retorna un ULID en hexadecimal (`ULID().hex`), asegurando siempre un identificador único de correlación para logging o respuestas HTTP.
- **Consumo:** Usado por `async_generation.py` (`sse_chat_response` y `sse_consistency_response`) para etiquetar eventos de error SSE con el `trace_id` exacto para depuración desde el frontend.

#### Clase `OpenTelemetryProvider(TelemetryPort)`:
Implementa la interfaz formal `TelemetryPort` definida en `kosmo.contracts.telemetry`.

- **Inicialización (`__init__`)**:
  - `tracer`: `trace.get_tracer(tracer_name)` (por defecto `"kosmo.business"`).
  - `meter`: `metrics.get_meter(meter_name)` (por defecto `"kosmo.auth"`).
  - **Instrumentos métricos registrados**:
    1. `_auth_events` (Counter): `"kosmo.auth.events"`, unidad `"1"`. Descripción: *"Authentication events by type"*.
    2. `_codegen_duration` (Histogram): `"kosmo.codegen.phase_duration_seconds"`, unidad `"s"`. Descripción: *"Duration of codegen pipeline phases in seconds"*.
    3. `_codegen_retries` (Counter): `"kosmo.codegen.retries"`, unidad `"1"`. Descripción: *"Number of codegen validation retries"*.
    4. `_llm_tokens` (Counter): `"kosmo.llm.tokens"`, unidad `"1"`. Descripción: *"LLM tokens consumed"*.

- **Métodos de Tracing de Spans**:
  - **`trace_sync(span_name, attributes, func, *args, **kwargs) -> Any`**:
    - Ejecuta `func` dentro de un span activo (`self._tracer.start_as_current_span(span_name, attributes=attributes)`).
    - En caso de excepción: registra el error en el span (`span.record_exception(exc)`), establece el estado como `trace.StatusCode.ERROR` y re-lanza la excepción sin alterar el flujo original.
  - **`trace_async(span_name, attributes, func, *args, **kwargs) -> Any`**:
    - Versión asíncrona. Si el resultado es awaitable (`inspect.isawaitable`), lo aguarda dentro del contexto del span.
    - Captura y anota cualquier excepción con `StatusCode.ERROR` antes de propagarla.

- **Métodos de Registro de Métricas**:
  - **`record_auth_event(event_type: str, user_id: str | None = None) -> None`**:
    - Incrementa el contador `kosmo.auth.events` en 1 con atributos `{"event_type": event_type}` y opcionalmente `user_id`.
  - **`record_codegen_duration(phase: str, duration_seconds: float, status: str = "success") -> None`**:
    - Registra el valor temporal en el histograma `kosmo.codegen.phase_duration_seconds` con atributos `{"phase": phase, "status": status}`.
  - **`record_codegen_retries(retries_count: int, success: bool) -> None`**:
    - Incrementa el contador `kosmo.codegen.retries` con la cantidad de reintentos y atributo `{"success": "true" | "false"}`.
  - **`record_llm_tokens(tokens: int, model: str = "", user_id: str | None = None) -> None`**:
    - Incrementa el contador `kosmo.llm.tokens` con el volumen de tokens consumidos y atributos opcionales `model` y `user_id`.

---

## Interacción con la Capa de Contratos (`contracts/telemetry.py`)

Para preservar la arquitectura hexagonal, la relación entre `infrastructure/telemetry` y el resto de la aplicación se gestiona a través de `contracts/telemetry.py`:

```
[infrastructure/api/main.py]
       │
       ├── instrument_prometheus(app) ──> Exposición de /metrics
       │
       ├── (Dentro del Lifespan Startup)
       │     ├── configure_telemetry(settings)
       │     │     ├── Inicializa structlog (JSON / Console)
       │     │     ├── Inicializa Logfire
       │     │     └── set_telemetry_provider(OpenTelemetryProvider())
       │     │
       │     └── instrument_app(settings, app=app, db_engine=engine)
       │           ├── logfire.instrument_sqlalchemy
       │           └── logfire.instrument_redis
       │
       ▼ (Registrado como _provider global en contracts)
[Cualquier Caso de Uso o Servicio de Dominio]
       │
       ├── @traced("nombre_operacion", {"attr": "val"})
       ├── record_auth_event("login_success", user_id)
       ├── record_codegen_duration("build", 14.2)
       └── record_llm_tokens(350, model="gemini-3.8-flash")
```

Si no se ha inicializado ningún proveedor (por ejemplo, en tests unitarios que se ejecutan sin llamar a `configure_telemetry`), las funciones del contrato actúan como un **no-op transparente**: el decorador `@traced` ejecuta la función directamente sin crear spans ni añadir sobrecarga de rendimiento.

---

## Constantes y Valores Clave

| Identificador / Métrica | Valor / Formato | Archivo |
|:---|:---|:---|
| Gauge SSE | `kosmo_active_sse_connections` | `metrics.py` |
| Gauge Code Runners | `kosmo_active_code_runners` | `metrics.py` |
| Tracer Name | `"kosmo.business"` | `otel.py` |
| Meter Name | `"kosmo.auth"` | `otel.py` |
| Contador Auth | `"kosmo.auth.events"` | `otel.py` |
| Histograma Codegen | `"kosmo.codegen.phase_duration_seconds"` | `otel.py` |
| Contador Retries | `"kosmo.codegen.retries"` | `otel.py` |
| Contador Tokens LLM | `"kosmo.llm.tokens"` | `otel.py` |
| Longitud Trace ID | 32 caracteres hexadecimales | `bootstrap.py` / `otel.py` |
| Longitud Span ID | 16 caracteres hexadecimales | `bootstrap.py` |
| Fallback Trace ID | ULID hexadecimal (32 chars) | `otel.py` |

---

## Contratos Implementados

| Puerto (en `contracts/telemetry.py`) | Implementación Concreta | Archivo |
|:---|:---|:---|
| `TelemetryPort` | `OpenTelemetryProvider` | `infrastructure/telemetry/otel.py` |

---

## Reglas de Implementación y Mantenimiento

1. **Invocación en el orden correcto:**
   - `instrument_prometheus(app)` se ejecuta en el módulo `main.py` antes de que la aplicación empiece a aceptar peticiones.
   - `configure_telemetry(settings)` e `instrument_app(settings, app=app, db_engine=engine)` se ejecutan en el `lifespan(app)`.
2. **Idempotencia obligatoria:** Cualquier adición de métricas o instrumentación debe utilizar guardas de idempotencia (como `_get_or_create_gauge` o flags booleanos en `app.state`) para tolerar hot-reloading de Uvicorn sin errores.
3. **No registrar datos sensibles en trazas:** Los atributos de Redis están configurados con `capture_statement=False` para no registrar tokens o payloads en claro. Cualquier atributo nuevo en spans debe ser auditado contra leaks de credenciales.
4. **Formato de logs:** Nunca instanciar ni reconfigurar `logging.basicConfig` en módulos individuales. Todo log debe emitirse a través de `structlog.get_logger()`.
5. **Uso de `@traced`:** Es la vía estándar para añadir trazabilidad a métodos críticos. No instanciar `tracer.start_as_current_span()` manualmente en casos de uso.
