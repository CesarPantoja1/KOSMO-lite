// MODELS
export { sessionKey, useChatSessions, useChatSessionsStore } from './model/store';
export type { ChatPhase, ChatSessionSummary } from './model/types';

// STREAMING DE MENSAJES (SSE)
export { NETWORK_ERROR_MESSAGE, streamChatMessage } from './api/stream';
export type { ChatStreamBody, ChatStreamHandlers } from './api/stream';

// PRIMITIVAS DE MENSAJE
// Viven en `shared/model/chat-message.ts` porque también las consumen
// characteristic, discovery y requirements (las entidades no se importan entre sí).
// Se reexportan aquí para que features y pages tengan un único punto de entrada.
export { createAssistantError } from '@/shared/model/chat-message';
export type {
	ChangeSuggestion,
	ChatHistory,
	ChatMessage,
	ModificationResult,
} from '@/shared/model/chat-message';
