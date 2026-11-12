# Capa `shared/` — Núcleo transversal

> **Destinatario:** Agentes de IA que trabajen en `frontend/src/shared/`.
> **Ámbito:** `src/shared/` — código sin lógica de negocio, importable por cualquier capa superior.
> **Regla:** `shared` **nunca** importa de `entities`, `features`, `widgets` ni `pages`.
> **Nivel superior:** [../AGENTS.md](../AGENTS.md).

---

## 1. Estructura

```
shared/
├── api/
│   ├── client.ts        # apiClient<T>: fetch + auth + refresh 401 + errores
│   ├── config.ts        # API_BASE_URL, USE_MOCKS, PUBLIC_APP_DOMAIN
│   ├── errors.ts        # ApiError, parseApiError, formatApiError, ApiViolation
│   ├── auth.ts          # authApi (register, authorize, exchangeToken, getMe, login, logout)
│   ├── headers.ts       # authHeaders(extra): Bearer o X-Mock-User
│   └── index.ts         # Barrel (reexporta tipos de ../model/auth-types)
├── lib/
│   ├── sse.ts               # consumeSse(response, onEvent)
│   ├── useSseStream.ts      # useSseStream() → { phase, error, start, stop }
│   ├── pkce.ts              # generateCodeVerifier / generateCodeChallenge (S256)
│   ├── zod.ts               # re-export de zod
│   ├── normalize-repo-name.ts
│   ├── session-events.ts    # emitSessionExpired / onSessionExpired
│   └── index.ts
├── model/
│   ├── auth-store.ts    # useAuthStore (persist 'kosmo-auth-store'), clearAuthStore
│   ├── auth-types.ts    # DTOs de auth (RegisterRequest, UserPublic, TokenPairResponse, PrincipalView, ...)
│   ├── chat-message.ts  # tipos de mensaje + createUserMessage/appendMessage
│   └── index.ts
└── ui/
    ├── AuthGuard.tsx
    ├── Loading.tsx
    ├── ModalConfirm.tsx
    ├── markdown-text.tsx        # MarkdownText (remark)
    ├── CharacterCounter.tsx
    ├── OAuthIntegration.tsx
    ├── ConfirmacionVisibilidadRepositorio.tsx
    ├── FormularioCreacionRepositorio.tsx
    ├── VideoIntro.tsx
    ├── toast/       # toast(), ToasterProvider, types, icons
    ├── icons/       # 53 iconos SVG (default export mayormente)
    └── index.ts
```

---

## 2. `api/` — Cliente HTTP y autenticación

### `client.ts:25` — `apiClient<T>(url, options)`
Única puerta de salida HTTP del proyecto.
- Inyecta `authHeaders`, `Content-Type: application/json; charset=utf-8` y `cache: 'no-store'` (default).
- **Refresh automático en `401`** (excepto auth deshabilitada, sin `refreshToken`, o URLs `/auth/token|/auth/refresh`): usa `isRefreshing` + `failedQueue` para encolar peticiones concurrentes, hace `POST /api/v1/auth/refresh` (`grant_type=refresh_token`), y reintenta.
- Si el refresh falla: `emitSessionExpired()` + redirección a `/?session_expired=true`.
- `204` → `null`; si no, `res.json()`. Errores vía `parseApiError`.

### `config.ts`
- `API_BASE_URL`: `NEXT_PUBLIC_API_URL` o `''` en producción (mismo origen Nginx) / `http://localhost:8000` en dev.
- `USE_MOCKS`: `NEXT_PUBLIC_USE_MOCKS === 'true'`.
- `PUBLIC_APP_DOMAIN`: `NEXT_PUBLIC_DOMAIN_APP` o `http://localhost:3000`.

### `errors.ts` — manejo de errores
- `ApiError`: `status, type, title, detail, traceId, violations, errorCode, retryAfter`.
- `parseApiError(res, body)`: soporta FastAPI 422, OAuth RFC 6749, RFC 7807 y `Retry-After`.
- `formatApiError(err, fallback)`: mensaje amigable; traduce errores de API key IA.

### `auth.ts` / `headers.ts`
- `authApi`: `register`, `authorize` (PKCE S256), `exchangeToken`, `getMe`, `login` (authorize→exchange→setTokens→getMe), `logout`.
- Los DTOs viven en `model/auth-types.ts` (no en `api/`); `shared/api/index.ts` los reexporta para conveniencia.
- `authHeaders(extra)`: `Authorization: Bearer <accessToken>`; si `NEXT_PUBLIC_AUTH_DISABLED==='true'` y hay `mockUserId`, usa `X-Mock-User`. No sobrescribe headers existentes.

---

## 3. `lib/` — Utilidades

| Export                                           | Archivo                  | Descripción                                                                                                                             |
| ------------------------------------------------ | ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| `consumeSse(response, onEvent)`                  | `sse.ts`                 | Lee `ReadableStream`, separa bloques SSE por doble salto de línea y despacha cada `data:` JSON.                                         |
| `useSseStream()`                                 | `useSseStream.ts`        | Hook de transporte SSE: `{ phase: idle\|connecting\|streaming\|done\|error, error, start, stop }`. `stop` aborta con `AbortController`. |
| `generateCodeVerifier` / `generateCodeChallenge` | `pkce.ts`                | PKCE S256 (SHA-256 + base64url).                                                                                                        |
| `normalizeRepoName(input)`                       | `normalize-repo-name.ts` | Slugifica nombres de repositorio (máx. 100).                                                                                            |
| `emitSessionExpired` / `onSessionExpired`        | `session-events.ts`      | Bus de eventos desacoplado (shared no conoce consumidores).                                                                             |
| `export * from 'zod'`                            | `zod.ts`                 | Re-export central de Zod.                                                                                                               |

---

## 4. `model/` — Estado compartido

### `auth-store.ts` — `useAuthStore`
Zustand + `persist` (clave `kosmo-auth-store`).
- Estado: `accessToken`, `refreshToken`, `user`, `mockUserId`.
- Acciones: `setTokens`, `setUser`, `clearAuth`, `initMockUser`.
- `clearAuthStore()` limpia storage + estado.

### `chat-message.ts` — Primitivas de chat
- Tipos: `ChatRole`, `ChangeSuggestion`, `ModificationResult`, `RedirectInfo`, `ChatMessage`, `ChatResponse`, `ChatHistory`.
- Helpers: `createUserMessage`, `createAssistantError`, `appendMessage`.
- Genéricos; la gestión de sesiones de chat vive en `entities/chat`.

---

## 5. `ui/` — Componentes atómicos

| Componente                           | Archivo                                  | Uso                                                                                                    |
| ------------------------------------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `AuthGuard`                          | `AuthGuard.tsx`                          | Client component: espera montaje, bloquea/renderiza según `accessToken` (no reexportado en el barrel). |
| `Loading`                            | `Loading.tsx`                            | Modal de carga con mensajes rotativos.                                                                 |
| `ModalConfirm`                       | `ModalConfirm.tsx`                       | Modal genérico accesible de confirmación.                                                              |
| `MarkdownText`                       | `markdown-text.tsx`                      | Render de Markdown (remark) con resaltado Gherkin. Memoizado.                                          |
| `CharacterCounter`                   | `CharacterCounter.tsx`                   | Contador con color según límite.                                                                       |
| `OAuthIntegration`                   | `OAuthIntegration.tsx`                   | Fila conectado/desconectado para OAuth.                                                                |
| `ConfirmacionVisibilidadRepositorio` | `ConfirmacionVisibilidadRepositorio.tsx` | Diálogo de confirmación de repo público.                                                               |
| `FormularioCreacionRepositorio`      | `FormularioCreacionRepositorio.tsx`      | Form (react-hook-form + Zod) de creación de repo.                                                      |
| `VideoIntro`                         | `VideoIntro.tsx`                         | Video intro (no reexportado en el barrel).                                                             |

### `ui/toast/`
- `toast` (métodos `success/error/warning/info/add/close`), cola `queue` (`maxVisibleToasts: 5`, timeout 5000 ms).
- `ToasterProvider` (`{ position = 'top-right' }`) montado en `app/layout.tsx`.
- Tipos: `ToastVariant`, `ToastPosition`, `ToastContent`, `ToastOptions`.

### `ui/icons/`
- 53 iconos SVG `.tsx` con props típicas `{ size?, color?, className? }`.
- Mayoría `export default`; excepciones nombradas: `Logo`, `Lightbulb`, `AiOrb`, `KeyIcon`.
- Todos reexportados en `ui/index.ts`. **Importar desde `@/shared/ui`**, no del archivo suelto, salvo necesidad puntual.

---

## 6. Reglas específicas de `shared`

1. **No importar capas superiores.** Si un componente necesita limpiar stores de `entities`, emite un evento (ej. `session-events`) y que un composition root en `app/` lo consuma.
2. **Toda salida HTTP pasa por `apiClient`.** No usar `fetch` suelto en entidades/features.
3. **Reutilizar antes de crear:** busca aquí (`Loading`, `ModalConfirm`, `toast`, iconos) antes de escribir un componente nuevo.
4. **`useAuthStore` es la fuente de sesión;** el refresh transparente vive en `apiClient`.

---

## 7. Verificación

```bash
bun run typecheck
bun run test:coverage   # mide todo src/ (incluye ui/ y model/)
```

**Pruebas de la capa (unitarias y de componente aislado):**

| Segmento | Qué se prueba                                                                                   | Ejemplos                                             |
| -------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| `lib/`   | Funciones puras y hooks genéricos, con tablas `it.each` de casos válidos/inválidos.             | `pkce`, `sse`, `useSseStream`, `normalize-repo-name` |
| `api/`   | Cliente HTTP contra MSW: token, refresh ante 401 y reintento, formato de errores.               | `client`, `auth`, `errors`, `config`                 |
| `model/` | Store de sesión y primitivas de chat.                                                           | `auth-store`, `chat-message`                         |
| `ui/`    | Componentes atómicos aislados: render por props, callbacks y estados (sin stores de dominio).   | `ModalConfirm`, `AuthGuard`, `OAuthIntegration`      |

Un test nuevo de `shared` no debe depender de `entities`, `features` ni de datos de negocio.
