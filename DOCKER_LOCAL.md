# KOSMO Local Docker Stack

This stack runs the full local development environment:

- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- Backend docs: http://localhost:8000/docs
- Postgres: localhost:5432
- Redis: localhost:6379
- Vistas previas de proyectos implementados: un puerto por proyecto activo, rango
  `3001-3016` (servicio `preview`). La URL correcta de cada proyecto la expone
  `GET /api/v1/projects/{id}/preview` y la usa el botón "Ver aplicación" de la UI.

## Start

```bash
docker compose up --build
```

The backend container automatically:

- generates a local-only RS256 JWT key pair under `/tmp/kosmo-secrets`
- applies Alembic migrations with `alembic upgrade head`
- starts FastAPI with Uvicorn

## Optional Overrides

Copy `.env.example` to `.env` only when you need to change ports, passwords, or app settings:

```bash
cp .env.example .env
```

Para generar `FERNET_MASTER_KEY` (requerida cuando la autenticación está habilitada):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The committed defaults are enough for normal local development.

Generación de código con opencode y DeepSeek:

- `OPENCODE_MODEL` define el modelo que usa el agente (default `deepseek/deepseek-v4-flash`).
- `DEEPSEEK_API_KEY` (o `LLM_API_KEY`) provee la clave de la API de DeepSeek al contenedor opencode.

## Useful Commands

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose exec backend alembic upgrade head
docker compose exec backend python -m kosmo.infrastructure.scripts.seed_dev_user
```

## Troubleshooting

- **El agente no genera archivos tras cambiar un `opencode.json` de workspace:** el servidor
  opencode cachea la config por directorio en memoria. Reinícialo para que la recargue:
  ```bash
  docker compose restart opencode
  ```
- **Lock de workspace clavado tras matar el backend a mitad de una generación:** el lock se
  libera solo tras 30 minutos (staleness) o manualmente:
  ```bash
  docker compose exec postgres psql -U kosmo -d kosmo_dev -c \
    "UPDATE workspaces SET is_locked=false, locked_at=NULL, locked_by=NULL WHERE project_id='<prj_id>';"
  ```

## Reset Local Data

This deletes Postgres, MongoDB, Redis, and frontend cache volumes:

```bash
docker compose down -v
```

Then start again:

```bash
docker compose up --build
```

## Health Checks

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/openapi.json
```
