import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/shared/api/errors';
import { useAuthStore } from '@/shared/model/auth-store';
import { HttpResponse, apiUrl, delay, http, respuestaSse, server } from '@/test';
import { NETWORK_ERROR_MESSAGE, streamChatMessage } from './stream';

const URL_STREAM = '/api/v1/features/feat_1/chat/stream';

const responder = (eventos: Record<string, unknown>[]) =>
	server.use(http.post(apiUrl(URL_STREAM), () => respuestaSse(eventos)));

describe('streamChatMessage', () => {
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

		await streamChatMessage(URL_STREAM, { content: 'hola', session_id: 'cht_1' });

		expect(cuerpo).toEqual({ content: 'hola', session_id: 'cht_1' });
		expect(authorization).toBe('Bearer access-sse');
	});

	it('avisa con onOpen cuando el servidor acepta la petición', async () => {
		responder([]);
		const onOpen = vi.fn();

		await streamChatMessage(URL_STREAM, { content: 'x' }, { onOpen });

		expect(onOpen).toHaveBeenCalledOnce();
	});

	it('entrega cada evento "chunk" en orden e ignora "start"', async () => {
		responder([
			{ type: 'start' },
			{ type: 'chunk', content: 'Hola' },
			{ type: 'chunk', content: ' mundo' },
		]);
		const onChunk = vi.fn();

		await streamChatMessage(URL_STREAM, { content: 'x' }, { onChunk });

		expect(onChunk.mock.calls.map(([c]) => c)).toEqual(['Hola', ' mundo']);
	});

	it('normaliza el evento "message" a un ChatMessage del asistente', async () => {
		responder([
			{
				type: 'message',
				id: 'm1',
				content: 'Respuesta completa',
				timestamp: '2026-01-01T00:00:00Z',
				suggestions: [
					{
						id: 's1',
						section: 'Sección',
						description: 'desc',
						diff_before: 'antes',
						diff_after: 'después',
						rationale: 'porque sí',
						applied: true,
						not_applied_reason: null,
					},
					'basura',
				],
				modification: {
					applied: true,
					modified_section: 'Sección',
					change_description: 'cambio',
				},
			},
		]);
		const onMessage = vi.fn();

		await streamChatMessage(URL_STREAM, { content: 'x' }, { onMessage });

		const mensaje = onMessage.mock.calls[0][0];
		expect(mensaje).toMatchObject({
			id: 'm1',
			role: 'assistant',
			content: 'Respuesta completa',
			created_at: '2026-01-01T00:00:00Z',
		});
		expect(mensaje.change_suggestions).toHaveLength(1);
		expect(mensaje.change_suggestions[0]).toMatchObject({
			section: 'Sección',
			rationale: 'porque sí',
			applied: true,
		});
		expect(mensaje.modification).toMatchObject({
			applied: true,
			modified_section: 'Sección',
			modified_document: null,
			undo_version_id: null,
		});
	});

	it('usa valores por defecto cuando "message" no trae sugerencias ni modificación', async () => {
		responder([{ type: 'message', content: 'simple' }]);
		const onMessage = vi.fn();

		await streamChatMessage(URL_STREAM, { content: 'x' }, { onMessage });

		const mensaje = onMessage.mock.calls[0][0];
		expect(mensaje.id).toEqual(expect.any(String));
		expect(mensaje.change_suggestions).toEqual([]);
		expect(mensaje.modification).toBeNull();
	});

	it('convierte el evento "error" en un Error con mensaje por defecto', async () => {
		responder([{ type: 'error' }, { type: 'error', message: 'El modelo no respondió' }]);
		const onError = vi.fn();

		await streamChatMessage(URL_STREAM, { content: 'x' }, { onError });

		expect(onError.mock.calls.map(([e]) => (e as Error).message)).toEqual([
			'Error al procesar el mensaje.',
			'El modelo no respondió',
		]);
	});

	it('rechaza con ApiError cuando el servidor responde con error, sin abrir el stream', async () => {
		server.use(
			http.post(apiUrl(URL_STREAM), () =>
				HttpResponse.json({ detail: 'Límite de uso alcanzado' }, { status: 429 }),
			),
		);
		const onOpen = vi.fn();

		const promesa = streamChatMessage(URL_STREAM, { content: 'x' }, { onOpen });

		await expect(promesa).rejects.toBeInstanceOf(ApiError);
		await expect(promesa).rejects.toMatchObject({
			status: 429,
			detail: 'Límite de uso alcanzado',
		});
		expect(onOpen).not.toHaveBeenCalled();
	});

	it('rechaza con ApiError aunque el cuerpo del error no sea JSON', async () => {
		server.use(
			http.post(apiUrl(URL_STREAM), () =>
				HttpResponse.html('<h1>502 Bad Gateway</h1>', { status: 502 }),
			),
		);

		await expect(streamChatMessage(URL_STREAM, { content: 'x' })).rejects.toMatchObject({
			status: 502,
		});
	});

	it('traduce un fallo de red a un mensaje comprensible', async () => {
		server.use(http.post(apiUrl(URL_STREAM), () => HttpResponse.error()));

		await expect(streamChatMessage(URL_STREAM, { content: 'x' })).rejects.toThrow(
			NETWORK_ERROR_MESSAGE,
		);
	});

	it('rechaza con AbortError al cancelar mediante la señal', async () => {
		server.use(
			http.post(apiUrl(URL_STREAM), async () => {
				await delay('infinite');
				return respuestaSse([]);
			}),
		);
		const controller = new AbortController();

		const promesa = streamChatMessage(URL_STREAM, { content: 'x' }, {}, controller.signal);
		controller.abort();

		await expect(promesa).rejects.toMatchObject({ name: 'AbortError' });
	});
});
