# Feature `chatbot/` — Chat con streaming SSE

> **Destinatario:** Agentes de IA que trabajen en `frontend/src/features/chatbot/`.
> **Ámbito:** UI de chat y mapeo de eventos SSE para refinar artefactos SDD.
> **Nivel superior:** [`../AGENTS.md`](../AGENTS.md) (capa `features`).

---

## 1. Estructura

```
chatbot/
├── ui/
│   ├── ChatPanel.tsx              # Contenedor: useChatStream + sesiones + historial → ChatView
│   ├── RequirementsChatPanel.tsx  # ChatPanel configurado para requisitos EARS
│   ├── ChatView.tsx               # UI presentacional del chat (sin red)
│   ├── ChatMessageBubble.tsx      # Burbuja de mensaje (MarkdownText + sugerencias)
│   ├── TarjetaRecepcionPlan.tsx   # Tarjeta de ChangeSuggestion (diff/rationale)
│   └── SessionSelector.tsx        # Dropdown de sesiones
├── model/
│   ├── useChatStream.ts           # Hook: envía y sigue la respuesta { phase, send, stop }
│   └── useChatStream.test.ts
└── index.ts
```

**Convención de nombres:** `*View` = solo UI, sin red ni stores (`ChatView`); `*Panel` = conectado a datos (`ChatPanel` y sus especializaciones, como `RequirementsChatPanel`). `useChatStream` es el hook que usa `ChatPanel` para enviar y seguir la respuesta.

**Exports:** `ChatPanel`, `RequirementsChatPanel`. El resto (`ChatView`, `ChatMessageBubble`, `useChatStream`) es interno de la feature.

> El chat es **solo SSE**. El antiguo flujo HTTP (`sendChatMessage` / `POST .../chat` en los stores de `characteristic`, `discovery` y `requirements`) se eliminó; esas entidades solo conservan el historial (`loadChatHistory`, `appendUserMessage`, `appendAssistantMessage`).

---

## 2. Flujo de streaming

```
useChatStream.send(url, { content, session_id? })      // features/chatbot: fase + AbortController
  └── streamChatMessage(url, body, handlers, signal)   // entities/chat/api/stream.ts: POST + authHeaders
        └── consumeSse(res, onEvent)                   // shared/lib/sse.ts: parsea bloques SSE
              └── handlers                             // onOpen | onChunk | onMessage | onError
```

- `streamChatMessage` (entidad) traduce `event.type`:
  - `chunk` → `onChunk(content)` (texto en streaming)
  - `message` → `onMessage(ChatMessage)` (normaliza el evento crudo: sugerencias y modificación)
  - `error` → `onError(Error)`
  - `start` se ignora
  - Rechaza con `ApiError` si la respuesta no es `ok`, con `NETWORK_ERROR_MESSAGE` si no hay conexión y con `AbortError` al cancelar.
- `useChatStream` (feature) solo gestiona la UI: fases `idle → connecting → streaming (onOpen) → done | error`. Retorna `{ phase, send, stop }`; `stop` aborta y la fase vuelve a `idle`.
- `ChatStreamBody = { content: string; session_id?: string | null }` (exportado por `entities/chat`).
- **La feature no hace `fetch`**: toda la red del chat (stream y sesiones) vive en `entities/chat/api/`.

---

## 3. Componentes

| Componente | Rol | Notas |
|---|---|---|
| `ChatView` | Presentacional | Header (sessionSelector/título), lista de mensajes, burbuja de streaming, error con reintento, textarea auto-ajustable (Enter envía, Shift+Enter salta línea), botón Enviar/Detener. **Sin lógica de red.** |
| `ChatMessageBubble` | Mensaje individual | Usuario a la derecha (texto plano); asistente con `MarkdownText`, `clarification_message` si no se aplicó, y una `TarjetaRecepcionPlan` por `change_suggestion`. |
| `TarjetaRecepcionPlan` | Sugerencia de cambio | Badge Aplicado/No aplicado, motivo, diff `- Anterior`/`+ Propuesto` (detecta eliminación si `diff_after` vacío) y rationale. |
| `ChatPanel` | Contenedor | Une `useChatStream` + `useChatSessions`; gestiona `streamingContent`, error/retry, rehidratación de historial al cambiar sesión/contexto, crear/eliminar sesión y re-listado tras el primer prompt. |
| `SessionSelector` | Dropdown de sesiones | Lista `ChatSessionSummary` con tiempo relativo; crear/seleccionar/eliminar; cierra con Escape o click externo. |
| `RequirementsChatPanel` | Adaptador EARS | Lee `entities/requirements` (`chatHistories`), construye `streamUrl = /api/v1/features/{featureId}/requirements/chat/stream`, `phase='requirements'`, `contextId=featureId`; refetch de requisitos si `modification.applied`. |

---

## 4. Integración con entidades

- **`entities/chat`** (`sessions-store.ts`): store Zustand por clave `projectId:phase:contextId` (`sessionKey`); expone `listSessions`, `createSession`, `deleteSession`, `setActiveSessionId` y `useChatSessions` (auto-lista). API interna: `listChatSessions`, `createChatSession`, `deleteChatSession` (no se exportan; se usan a través del store).
- **`shared/model/chat-message.ts`**: tipos `ChatMessage`, `ChangeSuggestion`, `ModificationResult`, `ChatHistory` + helpers `createUserMessage`, `createAssistantError`, `appendMessage` (reexportados por `entities/chat/model/types.ts`).
- **`entities/requirements`**: guarda `chatHistories[featureId]` con paginación por cursor (`historyCursor`/`historyHasMore`).

---

## 5. Consumidores

- `pages/project/DiscoveryPage` y `CharacteristicsPage` → `ChatPanel` (fases `discovery`, `features`).
- `pages/project/RequirementsPage` → `RequirementsChatPanel` (fase `requirements`).

---

## 6. Dónde cambiar qué

```
├── Mapeo de eventos SSE            → entities/chat/api/stream.ts
├── Fases / cancelación del stream  → model/useChatStream.ts
├── UI de burbujas/sugerencias      → ui/ChatMessageBubble.tsx, ui/TarjetaRecepcionPlan.tsx
├── Contenedor/sesiones             → ui/ChatPanel.tsx + entities/chat
├── Nuevo dominio (fase nueva)      → nuevo PanelXxx siguiendo RequirementsChatPanel.tsx
└── Parser SSE (consumeSse)         → shared/lib/sse.ts (compartido con entities/implementation)
```

---

## 7. Invariantes

1. **Sin `api/` ni `fetch`:** todo HTTP a través de `entities/chat` (`streamChatMessage` y sesiones).
2. **Presentación separada de red:** `ChatView` no hace red; `ChatPanel` la porta.
3. **Reutilizar tipado de mensajes** de `shared/model/chat-message.ts`.
4. **`index.ts` como API pública.**

---

## 8. Verificación

```bash
bun run typecheck
bun run test:coverage   # cubre model/ y ui/
```

**Pruebas:**

| Archivo                         | Qué verifica                                                                                  |
| ------------------------------- | --------------------------------------------------------------------------------------------- |
| `model/useChatStream.test.ts`   | Fases del stream, propagación de errores y cancelación con `stop()` (red simulada con MSW). |
| `ui/ChatPanel.test.tsx`   | Integración hook + sesiones + `ChatView` contra SSE simulado (`streamControlado`).             |
| `ui/ChatView.test.tsx`           | Envío con Enter, detener generación, cierre y estado deshabilitado.                           |
| `ui/SessionSelector.test.tsx`   | Crear, cambiar y eliminar sesiones (menú con `fireEvent.click`: el hover de user-event lo cierra). |
| `ui/ChatMessageBubble.test.tsx`, `ui/TarjetaRecepcionPlan.test.tsx` | Render de burbujas y tarjetas de sugerencia.              |

`RequirementsChatPanel` se prueba de forma integrada desde `RequirementsPage.test.tsx`.
