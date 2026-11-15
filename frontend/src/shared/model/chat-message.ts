/**
 * Primitivas genéricas de "mensaje de chat" (turno usuario/asistente),
 * sin ninguna dependencia de dominio de negocio.
 *
 * Viven en `shared` porque son consumidas por múltiples entidades
 * (chat, characteristic, discovery, requirements) que no deben
 * depender entre sí. La gestión de *sesiones* de chat (ChatPhase,
 * ChatSessionSummary, sessions-store, etc.) sigue siendo responsabilidad
 * exclusiva de `entities/chat`.
 */

export type ChatRole = 'user' | 'assistant' | 'system';

export interface ChangeSuggestion {
	id: string;
	section: string;
	description: string;
	diff_before: string;
	diff_after: string;
	rationale: string | null;
	applied: boolean;
	not_applied_reason: string | null;
}

export interface ModificationResult {
	applied: boolean;
	modified_section: string | null;
	change_description: string | null;
	modified_document: string | null;
	before: string | null;
	after: string | null;
	undo_version_id: string | null;
	clarification_message: string | null;
}

export interface ChatMessage {
	id: string;
	role: ChatRole;
	content: string;
	created_at: string;
	change_suggestions: ChangeSuggestion[] | null;
	modification: ModificationResult | null;
}

export interface ChatHistory {
	phase: string;
	context: string;
	messages: ChatMessage[];
	has_more: boolean;
	next_cursor: string | null;
}

export function createUserMessage(content: string): ChatMessage {
	return {
		id: crypto.randomUUID(),
		role: 'user',
		content,
		created_at: new Date().toISOString(),
		change_suggestions: null,
		modification: null,
	};
}

export function createAssistantError(content: string): ChatMessage {
	return {
		id: crypto.randomUUID(),
		role: 'assistant',
		content,
		created_at: new Date().toISOString(),
		change_suggestions: null,
		modification: null,
	};
}

export function appendMessage(messages: ChatMessage[], message: ChatMessage): ChatMessage[] {
	return [...messages, message];
}
