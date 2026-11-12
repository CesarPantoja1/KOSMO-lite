'use client';

import { useCallback } from 'react';
import type { ChangeSuggestion, ChatMessage, ModificationResult } from '@/entities/chat';
import { useSseStream } from '@/shared/lib/useSseStream';

export interface UseChatStreamOptions {
	onChunk?: (content: string) => void;
	onMessage?: (message: ChatMessage) => void;
	onError?: (error: unknown) => void;
}

export type SendChatStreamBody = {
	content: string;
	session_id?: string | null;
};

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null;
}

function toSuggestions(raw: unknown): ChangeSuggestion[] {
	if (!Array.isArray(raw)) return [];
	return raw.filter(isRecord).map((item) => ({
		id: String(item.id ?? crypto.randomUUID()),
		section: String(item.section ?? ''),
		description: String(item.description ?? ''),
		diff_before: String(item.diff_before ?? ''),
		diff_after: String(item.diff_after ?? ''),
		rationale: typeof item.rationale === 'string' ? item.rationale : null,
		applied: item.applied === true,
		not_applied_reason:
			typeof item.not_applied_reason === 'string' ? item.not_applied_reason : null,
	}));
}

function toModification(raw: unknown): ModificationResult | null {
	if (!isRecord(raw)) return null;
	return {
		applied: raw.applied === true,
		modified_section:
			typeof raw.modified_section === 'string' ? raw.modified_section : null,
		change_description:
			typeof raw.change_description === 'string' ? raw.change_description : null,
		modified_document:
			typeof raw.modified_document === 'string' ? raw.modified_document : null,
		before: typeof raw.before === 'string' ? raw.before : null,
		after: typeof raw.after === 'string' ? raw.after : null,
		undo_version_id: typeof raw.undo_version_id === 'string' ? raw.undo_version_id : null,
		clarification_message:
			typeof raw.clarification_message === 'string' ? raw.clarification_message : null,
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

export function useChatStream(options: UseChatStreamOptions = {}) {
	const { onChunk, onMessage, onError } = options;

	const { phase, start, stop } = useSseStream();

	const send = useCallback(
		(url: string, body: SendChatStreamBody) => {
			void start({
				url,
				body,
				onEvent: (event) => {
					if (event.type === 'chunk') {
						onChunk?.(String(event.content ?? ''));
					} else if (event.type === 'message') {
						onMessage?.(toChatMessage(event));
					} else if (event.type === 'error') {
						onError?.(
							new Error(String(event.message ?? 'Error al procesar el mensaje.')),
						);
					}
					// 'start' no requiere acción en la UI
				},
				onError,
			}).catch(() => undefined);
		},
		[start, onChunk, onMessage, onError],
	);

	return { phase, send, stop };
}
