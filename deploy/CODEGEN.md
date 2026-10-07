# Operación de generación y custodia de código

> Para variables de autenticación, Redis y claves JWT de Staging/Producción,
> consulta [AUTH_REDIS_CONFIGURATION.md](AUTH_REDIS_CONFIGURATION.md). Este
> documento solo cubre las variables adicionales de generación de código.

Cada proyecto generado tiene un directorio identificado por su `project_id`.
PostgreSQL conserva metadata, propiedad y trazabilidad; el código, su template y su
historial Git se conservan en filesystem.

| Ambiente | Persistencia | Contenedores con acceso |
| --- | --- | --- |
| Desarrollo | volumen `kosmo_workspaces` | `backend`, `opencode`, `preview` |
| Staging | `/opt/kosmo/staging/workspaces` | backend, lanzador interno (solo lectura), OpenCode efímero con acceso a un único proyecto |
| Producción | `/opt/kosmo/production/workspaces` | backend, lanzador interno (solo lectura), OpenCode efímero con acceso a un único proyecto |

El CD crea estos directorios y asigna UID/GID `1000`. El usuario accede a sus archivos mediante
las rutas autenticadas de KOSMO; un administrador los inspecciona únicamente por SSH. Las previews
públicas se publican en Staging y Producción sin exponer el rango interno de puertos. Al borrar un
proyecto, el backend borra su workspace y retira su hostname exacto de Staging.

## Secretos de GitHub Environments

Crear el secreto protegido `STAGING_CODEGEN_ENV_FILE` en el Environment `staging` y
`PRODUCTION_CODEGEN_ENV_FILE` en el Environment `Production`. El workflow los agrega al
archivo existente de cada ambiente, de modo que no es necesario revelar ni reemplazar el
secreto histórico `*_ENV_FILE`.

```dotenv
CODE_RUNNER_TOKEN=<secreto-aleatorio-para-el-runner>
# OPENCODE_LAUNCHER_TOKEN se genera automáticamente en cada despliegue si no se proporciona.
# Solo en Production: el wildcard existente.
PREVIEW_PUBLIC_HOST_SUFFIX=preview-kosmo.cespan.dev
```

Staging recibe su sufijo y las credenciales de Cloudflare desde `deploy-staging.yml`;
no incluir `PREVIEW_PUBLIC_HOST_SUFFIX` ni las variables `CLOUDFLARE_PREVIEW_*` en
`STAGING_CODEGEN_ENV_FILE`.

La implementación exige una API key personal configurada por el usuario en Preferencias de IA.
No configurar `OPENCODE_MODEL` ni claves globales de proveedor para OpenCode. El backend
descifra la clave del usuario solo al iniciar el trabajo; el lanzador la escribe en el `tmpfs`
del contenedor efímero y OpenCode la lee mediante `{file:...}`. El modelo principal y el
auxiliar son exactamente el elegido por el usuario; si no está en el catálogo de la versión
fijada de OpenCode, la implementación falla con un error explícito. El CD publica
`kosmo-opencode:sha-<commit>` y nunca instala `latest` al iniciar el contenedor.

## Inspección y backup

```bash
# En la VM de producción, lectura exclusivamente
sudo find /opt/kosmo/production/workspaces -mindepth 1 -maxdepth 1 -type d -printf '%f\n'
sudo du -sh /opt/kosmo/production/workspaces/*
sudo -u '#1000' git -C /opt/kosmo/production/workspaces/<project_id> log --oneline -n 20

# Backup diario: conservar también el backup consistente de PostgreSQL
sudo install -d -m 0700 /var/backups/kosmo
sudo tar -C /opt/kosmo/production -czf /var/backups/kosmo/workspaces-$(date +%F).tgz workspaces
```

Respaldar PostgreSQL y `workspaces` juntos en almacenamiento cifrado externo, con al menos
30 días de retención. Para restaurar: detener `backend` y `opencode-launcher`, restaurar primero
PostgreSQL, extraer el archive en `/opt/kosmo/production`, volver a asignar UID 1000 y
validar la lectura autenticada de un archivo antes de reanudar generación.

## Límites de despliegue

Cada trabajo OpenCode tiene 1.5 CPU, **1 GiB máximo de RAM** y 256 PIDs; hay un máximo de
dos trabajos simultáneos por instancia. No existe tiempo máximo para un trabajo activo.
Un heartbeat cada 20 segundos mantiene su lease; si el backend desaparece, el lanzador
elimina el contenedor abandonado tras 90 segundos sin heartbeat. El lanzador es el único
servicio con acceso al socket Docker y exige un token interno distinto al del runner.
Los trabajos usan la red dedicada `kosmo-codegen-network` (o su equivalente de Staging),
que solo comparten con backend y el lanzador; no se publican puertos al host.
El lanzador tiene su propio tope de 256 MiB, 0.5 CPU y 64 PIDs; no ejecuta
prompts ni recibe el volumen de otros proyectos en modo escritura.
`code-runner` tiene 1.5 CPU, 5 GiB,
256 PIDs y un `/tmp` ejecutable de 4 GiB; no posee capacidades Linux añadidas.
El runner recibe un archive temporal del workspace, no el volumen persistente ni secretos de
la aplicación; se destruye tras validar. El broker de eventos usa Redis para los cuatro workers
de producción y renueva su estado activo durante implementaciones largas. En producción, la preview se publica exclusivamente mediante
hosts `prj-<id>-preview-kosmo.cespan.dev`: el gateway lee el puerto interno asignado y Nginx
no expone el rango 3000-3015. Cloudflare debe enrutar el wildcard `*.cespan.dev` al mismo
Tunnel; Nginx rechaza cualquier host que no siga ese patrón. No habilitar 4096 ni 3000-3015
en el firewall ni crear rutas de Tunnel hacia esos puertos. Protege el wildcard en
Cloudflare Access antes de habilitarlo para usuarios: el código generado se ejecuta
en el contenedor `kosmo-preview` y no debe quedar disponible para Internet abierto.

## Previews por ambiente

Cada ambiente usa su propio Tunnel y sus propios hostnames para no mezclar workspaces ni tráfico:

| Ambiente | Sufijo configurado | Host público por proyecto | Ruta del Tunnel |
| --- | --- | --- | --- |
| Staging | `preview-staging-kosmo.cespan.dev` | `prj-<id>-preview-staging-kosmo.cespan.dev` | CNAME exacto automático -> Tunnel de Staging |
| Producción | `preview-kosmo.cespan.dev` | `prj-<id>-preview-kosmo.cespan.dev` | `*.cespan.dev` -> `http://nginx:80` |

Al completar una implementación en Staging, KOSMO crea un CNAME proxied exacto hacia
`<tunnel-id>.cfargotunnel.com` y agrega el ingress exacto `http://nginx:80` al Tunnel remoto.
Los registros exactos prevalecen sobre el wildcard de Producción y quedan cubiertos por el
certificado Universal de `*.cespan.dev`; no se necesita Advanced Certificate Manager. El token
`STAGING_PREVIEW_CLOUDFLARE_TOKEN` debe limitarse a Tunnel Edit, DNS Edit y Zone Read. No habilitar
4096 ni los puertos 3000-3015 en el firewall.
