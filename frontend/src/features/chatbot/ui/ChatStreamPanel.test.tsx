/**
 * Integración: ChatStreamPanel + useChatStream + useSseStream + store de sesiones,
 * contra un backend SSE simulado con MSW.
 */
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi, type Mock } from 'vitest';
import type { ChatMessage } from '@/entities/chat';
import { useChatSessionsStore } from '@/entities/chat';
import {
	HttpResponse,
	apiUrl,
	crearMensaje,
	crearSesionChat,
	http,
	renderWithProviders,
	respuestaSse,
	server,
	streamControlado,
} from '@/test';
import { ChatStreamPanel } from './ChatStreamPanel';

const URL_STREAM = '/api/v1/features/feat_1/chat/stream';
const URL_SESIONES = '/api/v1/projects/:projectId/chat-sessions';

type Callbacks = {
	onUserMessage: Mock<(content: string) => void>;
	onMessage: Mock<(message: ChatMessage) => void>;
	onRedirect: Mock<(message: string) => void>;
	onError: Mock<(error: unknown) => void>;
	onLoadHistory: Mock<(sessionId: string | null) => void>;
};

/** Contenedor que mantiene la lista de mensajes como lo haría una página real. */
function Arnes({ cb, sinSesiones = false }: { cb: Callbacks; sinSesiones?: boolean }) {
	const [mensajes, setMensajes] = useState<ChatMessage[]>([]);
	return (
		<ChatStreamPanel
			messages={mensajes}
			streamUrl={URL_STREAM}
			projectId={sinSesiones ? null : 'prj_1'}
			phase={sinSesiones ? null : 'features'}
			contextId='feat_1'
			onLoadHistory={cb.onLoadHistory}
			onUserMessage={(content) => {
				cb.onUserMessage(content);
				setMensajes((m) => [...m, crearMensaje({ role: 'user', content })]);
			}}
			onMessage={(message) => {
				cb.onMessage(message);
				setMensajes((m) => [...m, message]);
			}}
			onRedirect={cb.onRedirect}
			onError={cb.onError}
		/>
	);
}

function renderizar(opciones: { sinSesiones?: boolean } = {}) {
	const cb: Callbacks = {
		onUserMessage: vi.fn(),
		onMessage: vi.fn(),
		onRedirect: vi.fn(),
		onError: vi.fn(),
		onLoadHistory: vi.fn(),
	};
	const utils = renderWithProviders(<Arnes cb={cb} {...opciones} />);
	return { ...utils, cb };
}

/** Clic dentro del menú de sesiones sin mover el puntero (ver SessionSelector.test.tsx). */
const clicEnMenu = (el: HTMLElement) => fireEvent.click(el);

const campoMensaje = () => screen.getByRole('textbox', { name: 'Mensaje para el asistente' });

async function enviar(user: ReturnType<typeof renderizar>['user'], texto = 'Mejora el login') {
	await user.type(campoMensaje(), texto);
	await user.keyboard('{Enter}');
}

describe('ChatStreamPanel (integración con SSE)', () => {
	it('muestra la respuesta del asistente a medida que llega y luego el mensaje final', async () => {
		const stream = streamControlado();
		let cuerpo: unknown;
		server.use(
			http.post(apiUrl(URL_STREAM), async ({ request }) => {
				cuerpo = await request.json();
				return stream.respuesta;
			}),
		);
		const { user, cb } = renderizar();

		await enviar(user);
		expect(cb.onUserMessage).toHaveBeenCalledWith('Mejora el login');
		expect(screen.getByText('Mejora el login')).toBeInTheDocument();

		stream.emitir({ type: 'start' });
		stream.emitir({ type: 'chunk', content: 'Propongo ' });
		stream.emitir({ type: 'chunk', content: 'usar PKCE' });
		expect(await screen.findByText('Propongo usar PKCE')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Detener generación' })).toBeInTheDocument();
		expect(campoMensaje()).toBeDisabled();

		stream.emitir({ type: 'message', id: 'msg_final', content: 'Listo: **PKCE** añadido' });
		stream.cerrar();

		expect(await screen.findByText('PKCE')).toBeInTheDocument();
		expect(cb.onMessage).toHaveBeenCalledWith(
			expect.objectContaining({ id: 'msg_final', role: 'assistant' }),
		);
		expect(cuerpo).toEqual({ content: 'Mejora el login', session_id: null });
		await waitFor(() => expect(campoMensaje()).toBeEnabled());
	});

	it('convierte las sugerencias del evento final en tarjetas de cambio', async () => {
		server.use(
			http.post(apiUrl(URL_STREAM), () =>
				respuestaSse([
					{
						type: 'message',
						content: 'Te sugiero un cambio',
						suggestions: [
							{ id: 's1', description: 'Añadir 2FA', diff_before: '', diff_after: 'Usar 2FA', applied: true },
						],
					},
				]),
			),
		);
		const { user } = renderizar();

		await enviar(user);

		expect(await screen.findByRole('heading', { name: 'Añadir 2FA' })).toBeInTheDocument();
		expect(screen.getByText('Aplicado')).toBeInTheDocument();
	});

	it('un evento de error del stream muestra el error y permite reintentar', async () => {
		let intentos = 0;
		server.use(
			http.post(apiUrl(URL_STREAM), () => {
				intentos++;
				return intentos === 1
					? respuestaSse([{ type: 'error', message: 'El modelo no respondió' }])
					: respuestaSse([{ type: 'message', content: 'Respuesta tras reintentar' }]);
			}),
		);
		const { user, cb } = renderizar();

		await enviar(user);

		expect(await screen.findByRole('alert')).toHaveTextContent('El modelo no respondió');
		expect(cb.onError).toHaveBeenCalled();

		await user.click(screen.getByRole('button', { name: 'Reintentar' }));

		expect(await screen.findByText('Respuesta tras reintentar')).toBeInTheDocument();
		expect(screen.queryByRole('alert')).not.toBeInTheDocument();
		expect(intentos).toBe(2);
		// Reintentar no duplica el mensaje del usuario.
		expect(cb.onUserMessage).toHaveBeenCalledOnce();
	});

	it('un 400 (cambio de otra fase) se redirige en lugar de mostrarse como error', async () => {
		server.use(
			http.post(apiUrl(URL_STREAM), () =>
				HttpResponse.json(
					{ detail: 'Ese cambio corresponde a la fase de Requisitos' },
					{ status: 400 },
				),
			),
		);
		const { user, cb } = renderizar();

		await enviar(user);

		await waitFor(() =>
			expect(cb.onRedirect).toHaveBeenCalledWith('Ese cambio corresponde a la fase de Requisitos'),
		);
		expect(cb.onError).not.toHaveBeenCalled();
		expect(screen.queryByRole('alert')).not.toBeInTheDocument();
	});

	it('un error del servidor (500) se muestra con opción de reintentar', async () => {
		server.use(
			http.post(apiUrl(URL_STREAM), () =>
				HttpResponse.json({ detail: 'Servicio de IA saturado' }, { status: 503 }),
			),
		);
		const { user, cb } = renderizar();

		await enviar(user);

		expect(await screen.findByRole('alert')).toHaveTextContent('Servicio de IA saturado');
		expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument();
		expect(cb.onError).toHaveBeenCalledOnce();
	});

	it('Detener cancela la generación en curso', async () => {
		const stream = streamControlado();
		server.use(http.post(apiUrl(URL_STREAM), () => stream.respuesta));
		const { user, cb } = renderizar();
		await enviar(user);
		stream.emitir({ type: 'chunk', content: 'Respuesta parcial' });
		await screen.findByText('Respuesta parcial');

		await user.click(screen.getByRole('button', { name: 'Detener generación' }));

		expect(cb.onError).not.toHaveBeenCalled();
		expect(screen.queryByRole('alert')).not.toBeInTheDocument();
	});

	describe('sesiones de chat', () => {
		it('carga las sesiones del contexto y el historial de la sesión activa', async () => {
			const consultas: string[] = [];
			server.use(
				http.get(apiUrl(URL_SESIONES), ({ request }) => {
					consultas.push(new URL(request.url).search);
					return HttpResponse.json({ sessions: [crearSesionChat({ title: 'Login' })] });
				}),
			);
			const { cb } = renderizar();

			await waitFor(() => expect(consultas).toHaveLength(1));
			expect(consultas[0]).toBe('?phase=features&context_id=feat_1');
			await waitFor(() => expect(cb.onLoadHistory).toHaveBeenCalledWith(null));
		});

		it('crear un chat lo activa y los mensajes se envían en esa sesión', async () => {
			server.use(
				http.post(apiUrl(URL_SESIONES), () =>
					HttpResponse.json({ ...crearSesionChat({ id: 'ses_nueva', title: '' }), session_id: 'ses_nueva' }),
				),
			);
			let cuerpo: unknown;
			server.use(
				http.post(apiUrl(URL_STREAM), async ({ request }) => {
					cuerpo = await request.json();
					return respuestaSse([]);
				}),
			);
			const { user, cb } = renderizar();
			const selector = await screen.findByRole('button', { name: 'Seleccionar chat' });
			await waitFor(() => expect(selector).toBeEnabled());

			await user.hover(selector);
			clicEnMenu(screen.getByRole('button', { name: 'Nuevo chat' }));

			await waitFor(() => expect(cb.onLoadHistory).toHaveBeenLastCalledWith('ses_nueva'));
			await enviar(user, 'Hola');
			await waitFor(() => expect(cuerpo).toEqual({ content: 'Hola', session_id: 'ses_nueva' }));
		});

		it('eliminar un chat lo quita de la lista', async () => {
			server.use(
				http.get(apiUrl(URL_SESIONES), () =>
					HttpResponse.json({ sessions: [crearSesionChat({ id: 'ses_1', title: 'Viejo' })] }),
				),
				http.delete(apiUrl(`${URL_SESIONES}/:sessionId`), () => new HttpResponse(null, { status: 204 })),
			);
			const { user } = renderizar();
			const selector = await screen.findByRole('button', { name: 'Seleccionar chat' });
			await waitFor(() => expect(selector).toBeEnabled());
			await user.hover(selector);

			clicEnMenu(await screen.findByRole('button', { name: 'Eliminar chat Viejo' }));

			await waitFor(() =>
				expect(useChatSessionsStore.getState().sessions['prj_1:features:feat_1']).toEqual([]),
			);
		});

		it('si no se puede crear el chat muestra el error', async () => {
			server.use(
				http.post(apiUrl(URL_SESIONES), () =>
					HttpResponse.json({ detail: 'Límite de chats alcanzado' }, { status: 429 }),
				),
			);
			const { user } = renderizar();
			const selector = await screen.findByRole('button', { name: 'Seleccionar chat' });
			await waitFor(() => expect(selector).toBeEnabled());
			await user.hover(selector);

			clicEnMenu(screen.getByRole('button', { name: 'Nuevo chat' }));

			expect(await screen.findByRole('alert')).toHaveTextContent('Límite de chats alcanzado');
		});

		it('sin proyecto ni fase no muestra selector de sesiones', () => {
			renderizar({ sinSesiones: true });

			expect(screen.queryByRole('button', { name: 'Seleccionar chat' })).not.toBeInTheDocument();
			expect(screen.getByRole('heading', { name: 'Agente IA' })).toBeInTheDocument();
		});
	});
});
