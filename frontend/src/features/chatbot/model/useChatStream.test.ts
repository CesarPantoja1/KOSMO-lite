import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HttpResponse, apiUrl, delay, http, respuestaSse, server, streamControlado } from '@/test';
import { useChatStream } from './useChatStream';

const URL_STREAM = '/api/v1/features/feat_1/chat/stream';

describe('useChatStream', () => {
	it('inicia en fase idle', () => {
		const { result } = renderHook(() => useChatStream());

		expect(result.current.phase).toBe('idle');
	});

	it('pasa por las fases connecting → streaming → done', async () => {
		const stream = streamControlado();
		server.use(http.post(apiUrl(URL_STREAM), () => stream.respuesta));
		const { result } = renderHook(() => useChatStream());

		act(() => result.current.send(URL_STREAM, { content: 'Hola' }));
		expect(result.current.phase).toBe('connecting');

		await waitFor(() => expect(result.current.phase).toBe('streaming'));

		act(() => stream.cerrar());
		await waitFor(() => expect(result.current.phase).toBe('done'));
	});

	it('entrega los chunks y el mensaje final a sus callbacks', async () => {
		server.use(
			http.post(apiUrl(URL_STREAM), () =>
				respuestaSse([
					{ type: 'chunk', content: 'Ho' },
					{ type: 'chunk', content: 'la' },
					{ type: 'message', id: 'm1', content: 'Hola' },
				]),
			),
		);
		const onChunk = vi.fn();
		const onMessage = vi.fn();
		const { result } = renderHook(() => useChatStream({ onChunk, onMessage }));

		act(() => result.current.send(URL_STREAM, { content: 'x' }));
		await waitFor(() => expect(result.current.phase).toBe('done'));

		expect(onChunk.mock.calls.map(([c]) => c)).toEqual(['Ho', 'la']);
		expect(onMessage).toHaveBeenCalledWith(
			expect.objectContaining({ id: 'm1', role: 'assistant', content: 'Hola' }),
		);
	});

	it('pasa a fase error y notifica a onError cuando el servidor responde con error', async () => {
		server.use(
			http.post(apiUrl(URL_STREAM), () =>
				HttpResponse.json({ detail: 'Límite de uso alcanzado' }, { status: 429 }),
			),
		);
		const onError = vi.fn();
		const { result } = renderHook(() => useChatStream({ onError }));

		act(() => result.current.send(URL_STREAM, { content: 'x' }));

		await waitFor(() => expect(result.current.phase).toBe('error'));
		expect(onError).toHaveBeenCalledWith(
			expect.objectContaining({ status: 429, detail: 'Límite de uso alcanzado' }),
		);
	});

	it('stop() cancela, vuelve a idle y no lo reporta como error', async () => {
		server.use(
			http.post(apiUrl(URL_STREAM), async () => {
				await delay('infinite');
				return respuestaSse([]);
			}),
		);
		const onError = vi.fn();
		const { result } = renderHook(() => useChatStream({ onError }));

		act(() => result.current.send(URL_STREAM, { content: 'x' }));
		expect(result.current.phase).toBe('connecting');

		act(() => result.current.stop());

		await waitFor(() => expect(result.current.phase).toBe('idle'));
		expect(onError).not.toHaveBeenCalled();
	});

	it('stop() sin un stream activo no lanza errores', () => {
		const { result } = renderHook(() => useChatStream());

		expect(() => result.current.stop()).not.toThrow();
	});
});
