'use client';

import type { ChatMessage, ChatStreamBody } from '@/entities/chat';
import { streamChatMessage } from '@/entities/chat';
import { useCallback, useRef, useState } from 'react';

export type ChatStreamPhase = 'idle' | 'connecting' | 'streaming' | 'done' | 'error';

export interface UseChatStreamOptions {
	onChunk?: (content: string) => void;
	onMessage?: (message: ChatMessage) => void;
	onError?: (error: unknown) => void;
}

/**
 * Estado de UI de una conversación en streaming: fase y cancelación.
 * La red y el parseo de eventos viven en `entities/chat` (`streamChatMessage`).
 */
export function useChatStream(options: UseChatStreamOptions = {}) {
	const { onChunk, onMessage, onError } = options;
	const [phase, setPhase] = useState<ChatStreamPhase>('idle');
	const abortRef = useRef<AbortController | null>(null);

	const send = useCallback(
		(url: string, body: ChatStreamBody) => {
			const controller = new AbortController();
			abortRef.current = controller;
			setPhase('connecting');

			streamChatMessage(
				url,
				body,
				{
					onOpen: () => setPhase('streaming'),
					onChunk,
					onMessage,
					onError,
				},
				controller.signal,
			)
				.then(() => setPhase('done'))
				.catch((err: unknown) => {
					// Cancelado por el usuario: no es un error, se libera el chat
					if ((err as Error).name === 'AbortError') {
						setPhase('idle');
						return;
					}
					setPhase('error');
					onError?.(err);
				});
		},
		[onChunk, onMessage, onError],
	);

	const stop = useCallback(() => {
		abortRef.current?.abort();
	}, []);

	return { phase, send, stop };
}
