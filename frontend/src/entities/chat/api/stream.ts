import { API_BASE_URL, authHeaders, parseApiError } from '@/shared/api';
import { consumeSse } from '@/shared/lib';
import type { ChangeSuggestion, ChatMessage, ModificationResult } from '@/shared/model';

export interface ChatStreamBody {
	content: string;
	session_id?: string | null;
}

export interface ChatStreamHandlers {
	/** El servidor aceptó la petición y empieza a emitir eventos. */
	onOpen?: () => void;
	/** Fragmento de texto del asistente (evento `chunk`). */
	onChunk?: (content: string) => void;
	/** Mensaje final del asistente ya normalizado (evento `message`). */
	onMessage?: (message: ChatMessage) => void;
	/** Error informado por el servidor dentro del stream (evento `error`). */
	onError?: (error: Error) => void;
}

export const NETWORK_ERROR_MESSAGE = 'No se pudo conectar con el servidor. Reintenta.';

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null;
}

const stringOrNull = (value: unknown) => (typeof value === 'string' ? value : null);

function toSuggestions(raw: unknown): ChangeSuggestion[] {
	if (!Array.isArray(raw)) return [];
	return raw.filter(isRecord).map((item) => ({
		id: String(item.id ?? crypto.randomUUID()),
		section: String(item.section ?? ''),
		description: String(item.description ?? ''),
		diff_before: String(item.diff_before ?? ''),
		diff_after: String(item.diff_after ?? ''),
		rationale: stringOrNull(item.rationale),
		applied: item.applied === true,
		not_applied_reason: stringOrNull(item.not_applied_reason),
	}));
}

function toModification(raw: unknown): ModificationResult | null {
	if (!isRecord(raw)) return null;
	return {
		applied: raw.applied === true,
		modified_section: stringOrNull(raw.modified_section),
		change_description: stringOrNull(raw.change_description),
		modified_document: stringOrNull(raw.modified_document),
		before: stringOrNull(raw.before),
		after: stringOrNull(raw.after),
		undo_version_id: stringOrNull(raw.undo_version_id),
		clarification_message: stringOrNull(raw.clarification_message),
	};
}

function toChatMessage(event: Record<string, unknown>): ChatMessage {
	return {
		id: String(event.id ?? crypto.randomUUID()),
		role: 'assistant',
		content: String(event.content ?? ''),
		created_at: String(event.timestamp ?? new Date().toISOString()),
		change_suggestions: toSuggestions(event.suggestions),
		modification: toModification(event.modification),
	};
}

/**
 * Envía un mensaje a un endpoint de chat SSE y despacha cada evento ya tipado.
 *
 * Resuelve cuando el stream se cierra. Rechaza con `ApiError` si el servidor
 * responde con error, con un `Error` legible si no hay conexión, o con
 * `AbortError` si se cancela mediante `signal`.
 */
export async function streamChatMessage(
	url: string,
	body: ChatStreamBody,
	handlers: ChatStreamHandlers = {},
	signal?: AbortSignal,
): Promise<void> {
	try {
		const res = await fetch(`${API_BASE_URL}${url}`, {
			method: 'POST',
			headers: authHeaders({ 'Content-Type': 'application/json' }),
			body: JSON.stringify(body),
			signal,
		});

		if (!res.ok) {
			throw parseApiError(res, await res.json().catch(() => null));
		}

		handlers.onOpen?.();

		await consumeSse(res, (event) => {
			if (event.type === 'chunk') {
				handlers.onChunk?.(String(event.content ?? ''));
			} else if (event.type === 'message') {
				handlers.onMessage?.(toChatMessage(event));
			} else if (event.type === 'error') {
				handlers.onError?.(
					new Error(String(event.message ?? 'Error al procesar el mensaje.')),
				);
			}
			// 'start' no requiere acción
		});
	} catch (err) {
		// fetch rechaza con TypeError cuando no hay conexión (o se corta a mitad del stream)
		if (err instanceof TypeError) throw new Error(NETWORK_ERROR_MESSAGE);
		throw err;
	}
}
