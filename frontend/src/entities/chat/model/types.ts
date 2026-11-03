// Primitivas genéricas de mensaje: viven en `shared` (ver shared/model/chat-message.ts)
// y se re-exportan aquí para mantener compatibilidad con los consumidores de esta entidad.
export type {
	ChatRole,
	ChangeSuggestion,
	ModificationResult,
	RedirectInfo,
	ChatMessage,
	ChatResponse,
	ChatHistory,
} from '@/shared/model/chat-message';

export type ChatPhase = 'discovery' | 'features' | 'requirements';

export interface ChatSessionSummary {
	id: string;
	phase: ChatPhase;
	context_id: string | null;
	created_at: string;
	message_count: number;
	last_message_at: string | null;
	title: string;
}

export interface CreateChatSessionRequest {
	phase: ChatPhase;
	context_id: string | null;
}

export interface CreateChatSessionResponse extends ChatSessionSummary {
	session_id: string;
}

export interface ChatSessionListResponse {
	sessions: ChatSessionSummary[];
}
