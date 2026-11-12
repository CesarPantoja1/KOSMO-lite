'use client';
import { useCallback, useRef, useState } from 'react';
import { API_BASE_URL, authHeaders, parseApiError } from '../api';
import { consumeSse, SseEventHandler } from './sse';

export type SsePhase = 'idle' | 'connecting' | 'streaming' | 'done' | 'error';

export interface SseStartOptions {
	url: string;
	body: Record<string, unknown>;
	onEvent: SseEventHandler;
	onError?: (error: unknown) => void;
}

export function useSseStream() {
	const [phase, setPhase] = useState<SsePhase>('idle');
	const [error, setError] = useState<unknown>(null);
	const abortRef = useRef<AbortController | null>(null);

	const start = useCallback(async ({ url, body, onEvent, onError }: SseStartOptions) => {
		const controller = new AbortController();
		abortRef.current = controller;
		setError(null);
		setPhase('connecting');

		try {
			const res = await fetch(`${API_BASE_URL}${url}`, {
				method: 'POST',
				headers: authHeaders({ 'Content-Type': 'application/json' }),
				body: JSON.stringify(body),
				signal: controller.signal,
			});

			if (!res.ok) {
				throw parseApiError(res, await res.json().catch(() => null));
			}

			setPhase('streaming');
			await consumeSse(res, onEvent);
			setPhase('done');
		} catch (err) {
			if ((err as Error).name === 'AbortError') return;
			const mapped =
				err instanceof TypeError
					? new Error('No se pudo conectar con el servidor. Reintenta.')
					: err;
			setError(mapped);
			setPhase('error');
			onError?.(mapped);
		}
	}, []);

	const stop = useCallback(() => {
		abortRef.current?.abort();
	}, []);

	return { phase, error, start, stop };
}
