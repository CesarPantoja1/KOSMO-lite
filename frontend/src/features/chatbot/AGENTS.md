# Feature `chatbot/` — Chat con streaming SSE

> **Destinatario:** Agentes de IA que trabajen en `frontend/src/features/chatbot/`.
> **Ámbito:** UI de chat y mapeo de eventos SSE para refinar artefactos SDD.
> **Nivel superior:** [`../AGENTS.md`](../AGENTS.md) (capa `features`).

---

## 1. Estructura

```
chatbot/
├── ui/
│   ├── Chatbot.tsx                  # UI presentacional del chat
│   ├── chatbot-message.tsx          # Burbuja de mensaje (MarkdownText + sugerencias)
│   ├── TarjetaRecepcionPlan.tsx     # Tarjeta de ChangeSuggestion (diff/rationale)
│   ├── ChatStreamPanel.tsx          # Contenedor: hook + sesiones + Chatbot
│   ├── SessionSelector.tsx          # Dropdown de sesiones
│   └── PanelAsistenteRequisito.tsx  # Adaptador específico de requisitos EARS
├── model/
│   ├── useChatStream.ts             # Mapeo de eventos SSE de chat
│   └── useChatStream.test.ts
└── index.ts
```

**Exports:** `Chatbot`, `ChatStreamPanel`, `PanelAsistenteRequisito`, `ChatbotMessage`, `useChatStream`, tipo `SendChatStreamBody`.

---

## 2. Flujo de streaming

```
useChatStream.send(url, { content, session_id? })
  └── useSseStream.start (shared/lib)          // POST + authHeaders + AbortController
        └── consumeSse(res, onEvent)           // parsea bloques SSE
              └── onEvent(event)               // chunk | message | error
```

- `useChatStream` discrimina `event.type`:
  - `chunk` → `onChunk(content)` (texto en streaming)
  - `message` → `onMessage(ChatMessage)` (normaliza `message` crudo con `toSuggestions`/`toModification`)
  - `error` → `onError(Error)`
  - `start` se ignora
- Retorna `{ phase, send, stop }`; `stop` aborta.
- `SendChatStreamBody = { content: string; session_id?: string | null }`.
- El transporte (`useSseStream`, `consumeSse`) vive en `shared/lib`; **la feature no hace `fetch` directo**.

---

## 3. Componentes

| Componente | Rol | Notas |
|---|---|---|
| `Chatbot` | Presentacional | Header (sessionSelector/título), lista de mensajes, burbuja de streaming, error con reintento, textarea auto-ajustable (Enter envía, Shift+Enter salta línea), botón Enviar/Detener. **Sin lógica de red.** |
| `ChatbotMessage` | Mensaje individual | Usuario a la derecha (texto plano); asistente con `MarkdownText`, `clarification_message` si no se aplicó, y una `TarjetaRecepcionPlan` por `change_suggestion`. |
| `TarjetaRecepcionPlan` | Sugerencia de cambio | Badge Aplicado/No aplicado, motivo, diff `- Anterior`/`+ Propuesto` (detecta eliminación si `diff_after` vacío) y rationale. |
| `ChatStreamPanel` | Contenedor | Une `useChatStream` + `useChatSessions`; gestiona `streamingContent`, error/retry, rehidratación de historial al cambiar sesión/contexto, crear/eliminar sesión y re-listado tras el primer prompt. |
| `SessionSelector` | Dropdown de sesiones | Lista `ChatSessionSummary` con tiempo relativo; crear/seleccionar/eliminar; cierra con Escape o click externo. |
| `PanelAsistenteRequisito` | Adaptador EARS | Lee `entities/requirements` (`chatHistories`), construye `streamUrl = /api/v1/features/{featureId}/requirements/chat/stream`, `phase='requirements'`, `contextId=featureId`; refetch de requisitos si `modification.applied`. |

---

## 4. Integración con entidades

- **`entities/chat`** (`sessions-store.ts`): store Zustand por clave `projectId:phase:contextId` (`sessionKey`); expone `listSessions`, `createSession`, `deleteSession`, `setActiveSessionId` y `useChatSessions` (auto-lista). API: `listChatSessions`, `createChatSession`, `deleteChatSession`.
- **`shared/model/chat-message.ts`**: tipos `ChatMessage`, `ChangeSuggestion`, `ModificationResult`, `ChatHistory` + helpers `createUserMessage`, `createAssistantError`, `appendMessage` (reexportados por `entities/chat/model/types.ts`).
- **`entities/requirements`**: guarda `chatHistories[featureId]` con paginación por cursor (`historyCursor`/`historyHasMore`).

---

## 5. Consumidores

- `pages/project/DiscoveryPage` y `CharacteristicsPage` → `ChatStreamPanel` (fases `discovery`, `features`).
- `pages/project/RequirementsPage` → `PanelAsistenteRequisito` (fase `requirements`).

---

## 6. Dónde cambiar qué

```
├── Mapeo de eventos SSE            → model/useChatStream.ts
├── UI de burbujas/sugerencias      → ui/chatbot-message.tsx, ui/TarjetaRecepcionPlan.tsx
├── Contenedor/sesiones             → ui/ChatStreamPanel.tsx + entities/chat
├── Nuevo dominio (fase nueva)      → nuevo PanelXxx siguiendo PanelAsistenteRequisito.tsx
└── Transporte SSE genérico         → shared/lib/useSseStream.ts (fuera de la feature)
```

---

## 7. Invariantes

1. **Sin `api/`:** todo HTTP a través de `shared/lib/useSseStream` (transporte) y `entities/chat` (sesiones).
2. **Presentación separada de red:** `Chatbot` no hace red; `ChatStreamPanel` la porta.
3. **Reutilizar tipado de mensajes** de `shared/model/chat-message.ts`.
4. **`index.ts` como API pública.**

---

## 8. Verificación

```bash
bun run typecheck
bun run test:coverage   # cubre model/useChatStream.test.ts
```
