# Guía de Contribución a KOSMO

¡Gracias por tu interés en contribuir a **KOSMO (Knowledge Orchestration for Spec-driven MOdeling)**! 

KOSMO es una plataforma asistida por IA orientada a la unificación de requisitos en lenguaje natural (estándar EARS), diagramado arquitectónico determinista y trazabilidad de software. Esta guía describe el flujo de trabajo, estándares de código y buenas prácticas acordadas por el equipo de desarrollo (EPN TIC).

---

## Tabla de Contenidos

1. [Código de Conducta](#código-de-conducta)
2. [Estrategia de Ramas (Git Flow)](#estrategia-de-ramas-git-flow)
3. [Convención Estricta de Commits](#convención-estricta-de-commits)
4. [Entorno de Desarrollo Local](#entorno-de-desarrollo-local)
5. [Estándares de Código y Arquitectura](#estándares-de-código-y-arquitectura)
   * [Backend (FastAPI & Arquitectura Hexagonal)](#backend-fastapi--arquitectura-hexagonal)
   * [Frontend (Next.js & TypeScript)](#frontend-nextjs--typescript)
6. [Flujo para Enviar un Pull Request (PR)](#flujo-para-enviar-un-pull-request-pr)
7. [Pruebas y Verificación](#pruebas-y-verificación)

---

## Código de Conducta

Al participar en este proyecto, te comprometes a mantener un entorno respetuoso, inclusivo y profesional. Por favor, consulta nuestro [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) para más detalles.

---

## Estrategia de Ramas (Git Flow)

El desarrollo en KOSMO sigue Git Flow y usa las siguientes ramas:

* **`main`**: Código estable y listo para producción.
* **`develop`**: Rama de integración del desarrollo.
* **`feature/hu-<id>-<descripcion-corta>`**: Ramas creadas desde `develop` para implementar historias de usuario o características (ej. `feature/hu-12-generacion-diagrama-actividad-ia`). Sus Pull Requests se dirigen a `develop`.
* **`release/<version>`**: Ramas de preparación de una versión, creadas desde `develop`. Sus Pull Requests de entrega se dirigen a `main`. Si contienen ajustes que deben continuar en desarrollo, la misma rama se integra mediante PR en `develop`; no se fusiona `main` hacia `develop`.
* **`hotfix/<version>-<descripcion-corta>`**: Ramas para corregir incidencias urgentes de producción, creadas desde `main`. Sus Pull Requests se dirigen a `main` y, si procede, la misma rama se integra mediante PR en `develop`; no se fusiona `main` hacia `develop`.
* **`docs/<descripcion-corta>`**: Ramas para cambios exclusivamente documentales, creadas desde `main` (ej. `docs/guia-despliegue`). La misma rama abre Pull Requests hacia `main` y hacia `develop` para mantener ambas líneas actualizadas, sin fusionar `main` hacia `develop`.

> **Nota:** No trabajes directamente sobre `main` ni sobre `develop`. Todas las modificaciones deben integrarse mediante Pull Requests revisados. Los cambios que deban pasar de una línea de trabajo a otra se integran desde su rama de origen, nunca mediante un PR de `main` hacia `develop`.

---

## Convención Estricta de Commits y Azure Boards

En KOSMO seguimos la convención **Conventional Commits** vinculada a Azure Boards para mantener la trazabilidad de tareas:

### Reglas de formato:
1. **Idioma:** Todos los mensajes de commit deben escribirse en **español**.
2. **Estructura:** `tipo(alcance): descripción breve en imperativo AB#ID` (o `tipo: descripción breve AB#ID`).
3. **ID Obligatorio de Azure Boards:** Todo commit en una rama de trabajo debe terminar con `AB#ID` (ej. `AB#191`).

### Tipos de commit permitidos:

| Tipo | Descripción | Ejemplo |
|---|---|---|
| `feat` | Nueva funcionalidad o característica | `feat(chat): definir entidades de dominio AB#191` |
| `fix` | Corrección de errores en código o configuración | `fix(auth): corregir refresco de token expirado AB#145` |
| `docs` | Cambios en documentación | `docs: actualizar arquitectura de CI CD en wiki AB#191` |
| `style` | Cambios de formato, espacios o linting | `style(backend): formatear archivos con ruff AB#191` |
| `refactor` | Refactorización sin modificar comportamiento | `refactor(api): desacoplar repositorios de SQLAlchemy AB#191` |
| `test` | Adición o modificación de pruebas | `test(frontend): agregar pruebas para Zustand store AB#191` |
| `chore` | Tareas de mantenimiento o dependencias | `chore(deps): actualizar uv.lock AB#191` |
| `ci` | Cambios en workflows de CI/CD | `ci: añadir job branch-policy para validar PR AB#191` |

---

## Entorno de Desarrollo Local

### Requisitos Previos:
* [Docker](https://www.docker.com/) y [Docker Compose](https://docs.docker.com/compose/)
* [Python 3.13+](https://www.python.org/) y [`uv`](https://github.com/astral-sh/uv) (para desarrollo de backend)
* [Node.js 20+](https://nodejs.org/) y [`bun`](https://bun.sh/) (para desarrollo de frontend)

### Configuración del proyecto:

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/CesarPantoja1/KOSMO-lite.git
   cd KOSMO-lite
   ```

2. **Configurar variables de entorno:**
   Copia el archivo de ejemplo para crear tu entorno local:
   ```bash
   cp .env.example .env
   ```

3. **Levantar la infraestructura de servicios con Docker Compose:**
   ```bash
   docker compose up -d --build
   ```
   * Frontend: `http://localhost:3000`
   * Backend API: `http://localhost:8000`
   * Documentación Swagger: `http://localhost:8000/docs`

---

## Estándares de Código y Arquitectura

### Backend (FastAPI & Arquitectura Hexagonal)
* Ubicación: `backend/src/kosmo/`
* **Capas de Arquitectura Hexagonal:**
  * `domain/`: Entidades de negocio, agregados, objetos de valor y excepciones de dominio. No depende de ningún marco externo.
  * `application/`: Casos de uso, servicios de aplicación e interfaces de puertos.
  * `infrastructure/`: Adaptadores externos (base de datos con PostgreSQL/pgvector, MongoDB, Redis, API FastAPI, integraciones con LLM).
* **Gestión de dependencias:** Usamos `uv` para gestionar paquetes en `pyproject.toml` y `uv.lock`.

### Frontend (Next.js & TypeScript)
* Ubicación: `frontend/`
* Framework: Next.js (App Router), React, TypeScript.
* Diseño UI: Utilizar la guía de diseño del proyecto, evitando valores arbitrarios en píxeles cuando se puedan usar variables del sistema de diseño.

---

## Flujo para Enviar un Pull Request (PR)

1. Crea tu rama desde la rama base correspondiente:
   ```bash
   # Funcionalidad
   git switch develop
   git pull origin develop
   git switch -c feature/hu-XX-mi-funcionalidad

   # Documentación
   git switch main
   git pull origin main
   git switch -c docs/guia-despliegue
   ```
2. Realiza tus cambios y haz commits siguiendo la [Convención Estricta de Commits](#convención-estricta-de-commits).
3. Asegúrate de que las pruebas pasen y el código construya sin errores.
4. Envía la rama al repositorio remoto:
   ```bash
   git push -u origin <nombre-de-tu-rama>
   ```
5. Abre un **Pull Request** en GitHub / Azure DevOps: hacia `develop` para `feature/*`; hacia `main` para `release/*` y `hotfix/*`; y, para `docs/*`, abre Pull Requests de la misma rama hacia `main` y `develop`. Describe:
   * El objetivo de la historia de usuario o corrección.
   * Los cambios principales realizados.
   * El plan de verificación o pruebas realizadas.
6. Asigna revisores y realiza los ajustes solicitados hasta obtener la aprobación.

---

## Pruebas y Verificación

Antes de enviar tu PR, ejecuta las pruebas en tu entorno local:

### Backend:
```bash
cd backend
uv run pytest
```

### Frontend:
```bash
cd frontend
bun run build
```

---

¡Gracias por contribuir a la evolución de KOSMO! Si tienes dudas o sugerencias, abre un *issue* o contacta al equipo de desarrollo.
