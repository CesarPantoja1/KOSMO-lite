# KOSMO

## Descripción

KOSMO (Knowledge Orchestration for Spec-driven MOdeling) es una plataforma de ingeniería de software asistida por inteligencia artificial que transforma necesidades expresadas en lenguaje natural en requisitos estructurados, modelos arquitectónicos y, en futuras versiones, código funcional.

Su objetivo es unificar en un solo flujo de trabajo la especificación, el modelado y la generación de artefactos de software, reduciendo la brecha entre la idea inicial y la implementación técnica.

A diferencia de las herramientas tradicionales de modelado o de las plataformas low-code convencionales, KOSMO incorpora una capa de inteligencia que permite generar requisitos verificables, diagramas deterministas y mantener una trazabilidad bidireccional entre las especificaciones y los modelos.

## Propuesta de Valor

* Generación automática de requisitos bajo el estándar EARS a partir de lenguaje natural.
* Creación automática de diagramas y modelos arquitectónicos asistidos por IA.
* Trazabilidad bidireccional entre requisitos y modelos visuales.
* Detección temprana de inconsistencias entre especificaciones y diseño.
* Base para la futura generación automática de código y documentación.

## Visión

Para ingenieros de software que buscan transformar ideas y necesidades de negocio en especificaciones técnicas y modelos arquitectónicos de forma ágil y precisa, KOSMO es una plataforma de orquestación del conocimiento para operaciones de modelado basadas en especificaciones.

Mediante agentes de inteligencia artificial, KOSMO automatiza la creación de requisitos, diagramas y artefactos técnicos, garantizando trazabilidad, coherencia y alineación entre las necesidades del negocio y el diseño del sistema.

## Arquitectura de la Solución

KOSMO está diseñado sobre una arquitectura distribuida en múltiples capas:

* Frontend: interfaz web interactiva desarrollada con Next.js.
* Backend: API y lógica de negocio implementadas con FastAPI bajo arquitectura hexagonal.
* Capa de Inteligencia Artificial: sistema de agentes basado en el patrón orquestador-trabajador.
* Infraestructura: contenedores Docker para entornos consistentes de desarrollo y despliegue.

## Características Principales

* Transformación de lenguaje natural a requisitos EARS.
* Generación automática de diagramas UML y modelos arquitectónicos.
* Edición interactiva de modelos en un lienzo visual.
* Sincronización bidireccional entre requisitos y diagramas.
* Control de versiones de requisitos y modelos.
* Análisis de impacto y trazabilidad.
* Validación de consistencia entre especificaciones y diseño.

## Stack Tecnológico

* Frontend: Next.js, React, TypeScript.
* Backend: FastAPI, Python.
* Inteligencia Artificial: arquitectura de agentes especializados.
* Contenedores: Docker y Docker Compose.
* Automatización: GitHub Actions.
* Gestión del proyecto: Azure DevOps.

## Infraestructura de Contenedores

La plataforma se orquesta mediante Docker Compose con cinco servicios coordinados que cubren el frontend, el backend y las tres bases de datos del sistema. Cada servicio cuenta con verificaciones de estado reales y dependencias declarativas, de modo que el orden de arranque queda garantizado por la propia herramienta sin requerir scripts auxiliares.

### Servicios definidos

| Servicio | Imagen | Función |
|----------|--------|---------|
| frontend | Build local desde `frontend/` | Interfaz Next.js servida con Bun |
| backend | Build local desde `backend/` | API FastAPI bajo arquitectura hexagonal |
| postgres | `pgvector/pgvector:pg17` | Base relacional con la extensión `vector` activa |
| mongodb | `mongo:7` | Almacén documental para la memoria de agentes |
| redis | `redis:7-alpine` | Caché y persistencia de sesiones JWT |

### Imagen del backend

El `Dockerfile` del backend está diseñado en dos etapas separadas para distinguir la construcción de la ejecución. La etapa builder parte de la imagen oficial de `uv` sobre Debian slim e instala las dependencias declaradas en `pyproject.toml` y `uv.lock` dentro de un entorno virtual aislado en `/opt/venv`. La etapa runtime, en cambio, utiliza `python:3.13-slim-bookworm`, copia únicamente el entorno virtual ya construido y ejecuta el proceso bajo un usuario no privilegiado denominado `kosmo`. Esta separación reduce el tamaño del artefacto desplegable y descarta el toolchain de compilación de la imagen final.

### Inicialización y migraciones

Cada arranque del contenedor del backend invoca el script `entrypoint.sh`, el cual aplica las migraciones de Alembic antes de iniciar Uvicorn. Para los escenarios donde no resulte deseable correr migraciones, como tareas en background o ejecución de pruebas, basta con definir la variable `RUN_MIGRATIONS=0` en el entorno. Por su parte, `alembic/env.py` lee la variable `DATABASE_URL` directamente desde el entorno, lo que permite reutilizar la misma configuración en local y en producción sin modificar archivos.

### Gestión de secretos

Las claves RS256 utilizadas para firmar y verificar los tokens JWT nunca quedan dentro de la imagen. En su lugar, `docker-compose.yml` monta el directorio `backend/.secrets/` como volumen de solo lectura sobre `/app/.secrets`, y la aplicación lee los archivos `jwt_private.pem` y `jwt_public.pem` desde esa ruta en tiempo de ejecución. De esta forma, las claves se mantienen completamente fuera de las capas del artefacto y pueden rotarse sin reconstruir la imagen.

### Verificaciones de estado

Las cuatro piezas críticas de la infraestructura cuentan con healthchecks integrados en la definición de Compose:

* Postgres utiliza `pg_isready` contra el usuario y la base configurados.
* MongoDB ejecuta `db.adminCommand({ping:1})` a través de `mongosh` autenticado.
* Redis responde al ping interno con `redis-cli ping`.
* El backend valida su propio endpoint `/health` mediante la librería estándar de Python, sin necesidad de instalar herramientas adicionales en la imagen.

La generación de código añade OpenCode y un workspace por proyecto en el entorno local.
En staging y producción ese código es persistente y administrado desde la instancia; la
configuración de secretos, respaldo y acceso está documentada en
[`deploy/CODEGEN.md`](deploy/CODEGEN.md).

El servicio del backend declara `depends_on` con la condición `service_healthy` sobre las tres bases. Por lo tanto, Compose espera a que cada una reporte estado saludable antes de iniciar la API.

### Arranque del entorno

Tras clonar el repositorio y copiar `.env.example` como `.env`, un único comando levanta el stack completo:

```bash
docker compose up -d --build
```

Compose construye las imágenes locales, descarga las imágenes oficiales necesarias, espera a que las bases queden saludables, e inicia primero el backend y luego el frontend. La API queda disponible en `http://localhost:8000` mientras que la interfaz web se sirve en `http://localhost:3000`.

## Objetivo del Release 1.0

Validar el flujo completo:
Lenguaje Natural → Requisitos EARS → Modelos Arquitectónicos

## Objetivo del Release 2.0

Completar el flujo integral:
Lenguaje Natural → Requisitos EARS → Modelos Arquitectónicos → Código Fuente

## Beneficios Esperados

* Reducción del tiempo de análisis y diseño.
* Disminución de errores de interpretación.
* Mayor trazabilidad entre requisitos y arquitectura.
* Aceleración del ciclo de desarrollo.
* Mejora en la calidad y consistencia de los artefactos generados.

## Metodología de Desarrollo

El proyecto sigue una metodología ágil basada en Scrum, con entregas incrementales organizadas en sprints quincenales y automatización completa del ciclo de integración y despliegue mediante GitHub Actions.

## Estado del Proyecto 

Actualmente en desarrollo de la versión 1.0, enfocada en la generación asistida por IA de requisitos estructurados y modelos arquitectónicos con trazabilidad bidireccional.

## Licencia

Este proyecto se encuentra en desarrollo con fines académicos y de investigación.

## Versión del Sistema

- **Versión actual:** v0.10.7
- **Notas de versión:** Estabilidad de despliegue, optimización de concurrencia y documentación v1 ([AB#440](https://dev.azure.com/TICEPN/a88c67c0-0fa0-4abd-a4fc-b7f0909de778/_workitems/edit/440)).
