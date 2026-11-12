import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/shared/api/errors';
import { useAuthStore } from '@/shared/model/auth-store';
import { HttpResponse, apiUrl, delay, http, server } from '@/test';
import { useSseStream } from './useSseStream';

const URL_STREAM = '/api/v1/features/feat_1/chat/stream';

/** Respuesta `text/event-stream` que emite los eventos dados y cierra el stream. */
function respuestaSse(eventos: Record<string, unknown>[]) {
	const encoder = new TextEncoder();
	const stream = new ReadableStream({
		start(controller) {
			eventos.forEach((e) => controller.enqueue(encoder.encode(`data: ${JSON.stringify(e)}\n\n`)));
			controller.close();
		},
	});
	return new HttpResponse(stream, { headers: { 'Content-Type': 'text/event-stream' } });
}

describe('useSseStream', () => {
	it('inicia en fase idle y sin error', () => {
		const { result } = renderHook(() => useSseStream());

		expect(result.current.phase).toBe('idle');
		expect(result.current.error).toBeNull();
	});

	it('entrega cada evento del stream y termina en fase done', async () => {
		server.use(
			http.post(apiUrl(URL_STREAM), () =>
				respuestaSse([
					{ type: 'token', content: 'Hola' },
					{ type: 'token', content: ' mundo' },
					{ type: 'done' },
				]),
			),
		);
		const onEvent = vi.fn();
		const { result } = renderHook(() => useSseStream());

		await act(() => result.current.start({ url: URL_STREAM, body: {}, onEvent }));

		expect(onEvent.mock.calls.map(([e]) => e)).toEqual([
			{ type: 'token', content: 'Hola' },
			{ type: 'token', content: ' mundo' },
			{ type: 'done' },
		]);
		expect(result.current.phase).toBe('done');
	});

	it('envía el cuerpo como JSON con el token de autenticación', async () => {
		useAuthStore.getState().setTokens('access-sse', 'refresh');
		let cuerpo: unknown;
		let authorization: string | null = null;
		server.use(
			http.post(apiUrl(URL_STREAM), async ({ request }) => {
				cuerpo = await request.json();
				authorization = request.headers.get('Authorization');
				return respuestaSse([]);
			}),
		);
		const { result } = renderHook(() => useSseStream());

		await act(() =>
			result.current.start({ url: URL_STREAM, body: { message: 'hola' }, onEvent: vi.fn() }),
		);

		expect(cuerpo).toEqual({ message: 'hola' });
		expect(authorization).toBe('Bearer access-sse');
	});

	it('pasa por las fases connecting → streaming → done', async () => {
		// El test controla cuándo responde el servidor y cuándo se cierra el stream.
		let responder!: () => void;
		const servidorListo = new Promise<void>((r) => (responder = r));
		let cerrarStream!: () => void;
		server.use(
			http.post(apiUrl(URL_STREAM), async () => {
				await servidorListo;
				const stream = new ReadableStream({
					start(controller) {
						cerrarStream = () => controller.close();
					},
				});
				return new HttpResponse(stream, { headers: { 'Content-Type': 'text/event-stream' } });
			}),
		);
		const { result } = renderHook(() => useSseStream());

		act(() => {
			void result.current.start({ url: URL_STREAM, body: {}, onEvent: vi.fn() });
		});
		await waitFor(() => expect(result.current.phase).toBe('connecting'));

		responder();
		await waitFor(() => expect(result.current.phase).toBe('streaming'));

		act(() => cerrarStream());
		await waitFor(() => expect(result.current.phase).toBe('done'));
	});

	it('expone un ApiError y llama a onError cuando el servidor responde con error', async () => {
		server.use(
			http.post(apiUrl(URL_STREAM), () =>
				HttpResponse.json({ detail: 'Límite de uso alcanzado' }, { status: 429 }),
			),
		);
		const onError = vi.fn();
		const onEvent = vi.fn();
		const { result } = renderHook(() => useSseStream());

		await act(() => result.current.start({ url: URL_STREAM, body: {}, onEvent, onError }));

		expect(result.current.phase).toBe('error');
		expect(result.current.error).toBeInstanceOf(ApiError);
		expect(result.current.error).toMatchObject({ status: 429, detail: 'Límite de uso alcanzado' });
		expect(onError).toHaveBeenCalledWith(result.current.error);
		expect(onEvent).not.toHaveBeenCalled();
	});

	it('reporta el error aunque el servidor responda con un cuerpo que no es JSON', async () => {
		server.use(
			http.post(apiUrl(URL_STREAM), () =>
				HttpResponse.html('<h1>502 Bad Gateway</h1>', { status: 502 }),
			),
		);
		const { result } = renderHook(() => useSseStream());

		await act(() => result.current.start({ url: URL_STREAM, body: {}, onEvent: vi.fn() }));

		expect(result.current.phase).toBe('error');
		expect(result.current.error).toMatchObject({ status: 502 });
	});

	it('traduce un fallo de red a un mensaje comprensible para el usuario', async () => {
		server.use(http.post(apiUrl(URL_STREAM), () => HttpResponse.error()));
		const onError = vi.fn();
		const { result } = renderHook(() => useSseStream());

		await act(() =>
			result.current.start({ url: URL_STREAM, body: {}, onEvent: vi.fn(), onError }),
		);

		expect(result.current.phase).toBe('error');
		expect((result.current.error as Error).message).toBe(
			'No se pudo conectar con el servidor. Reintenta.',
		);
		expect(onError).toHaveBeenCalledOnce();
	});

	it('limpia el error anterior al iniciar un nuevo stream', async () => {
		// server.use antepone handlers: el de un solo uso (fallo) se registra al final.
		server.use(http.post(apiUrl(URL_STREAM), () => respuestaSse([])));
		server.use(http.post(apiUrl(URL_STREAM), () => HttpResponse.error(), { once: true }));
		const { result } = renderHook(() => useSseStream());
		await act(() => result.current.start({ url: URL_STREAM, body: {}, onEvent: vi.fn() }));
		expect(result.current.phase).toBe('error');

		await act(() => result.current.start({ url: URL_STREAM, body: {}, onEvent: vi.fn() }));

		expect(result.current.phase).toBe('done');
		expect(result.current.error).toBeNull();
	});

	it('stop() cancela la conexión sin reportarlo como error', async () => {
		server.use(
			http.post(apiUrl(URL_STREAM), async () => {
				await delay('infinite');
				return respuestaSse([]);
			}),
		);
		const onError = vi.fn();
		const { result } = renderHook(() => useSseStream());

		let peticion: Promise<void> = Promise.resolve();
		act(() => {
			peticion = result.current.start({ url: URL_STREAM, body: {}, onEvent: vi.fn(), onError });
		});
		await waitFor(() => expect(result.current.phase).toBe('connecting'));

		await act(async () => {
			result.current.stop();
			await peticion;
		});

		expect(result.current.error).toBeNull();
		expect(onError).not.toHaveBeenCalled();
	});

	it('stop() sin un stream activo no lanza errores', () => {
		const { result } = renderHook(() => useSseStream());

		expect(() => result.current.stop()).not.toThrow();
	});
});
