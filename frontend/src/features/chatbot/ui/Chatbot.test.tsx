import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { crearMensaje, renderWithProviders } from '@/test';
import { Chatbot } from './Chatbot';

type Props = Parameters<typeof Chatbot>[0];

function renderizar(props: Props = {}) {
	const onSendMessage = vi.fn();
	const utils = renderWithProviders(<Chatbot onSendMessage={onSendMessage} {...props} />);
	return { ...utils, onSendMessage };
}

const campo = () => screen.getByRole('textbox', { name: 'Mensaje para el asistente' });
const botonEnviar = () => screen.getByRole('button', { name: 'Enviar mensaje' });

describe('Chatbot', () => {
	it('sin mensajes muestra el saludo y el título por defecto', () => {
		renderizar();

		expect(screen.getByRole('heading', { name: 'Agente IA' })).toBeInTheDocument();
		expect(screen.getByText('Hola 👋. ¿En qué puedo ayudarte?')).toBeInTheDocument();
	});

	it('acepta título, saludo y placeholder personalizados', () => {
		renderizar({ title: 'Asistente de requisitos', greeting: '¿Qué criterio revisamos?', placeholder: 'ej. agrega un caso' });

		expect(screen.getByRole('heading', { name: 'Asistente de requisitos' })).toBeInTheDocument();
		expect(screen.getByText('¿Qué criterio revisamos?')).toBeInTheDocument();
		expect(campo()).toHaveAttribute('placeholder', 'ej. agrega un caso');
	});

	it('muestra el historial en lugar del saludo', () => {
		renderizar({
			messages: [
				crearMensaje({ role: 'user', content: 'Pregunta' }),
				crearMensaje({ role: 'assistant', content: 'Respuesta' }),
			],
		});

		expect(screen.queryByText(/¿En qué puedo ayudarte\?/)).not.toBeInTheDocument();
		expect(screen.getByText('Pregunta')).toBeInTheDocument();
		expect(screen.getByText('Respuesta')).toBeInTheDocument();
	});

	describe('envío de mensajes', () => {
		it('el botón de enviar está deshabilitado con el campo vacío o en blanco', async () => {
			const { user } = renderizar();
			expect(botonEnviar()).toBeDisabled();

			await user.type(campo(), '   ');

			expect(botonEnviar()).toBeDisabled();
		});

		it('envía con el botón, recorta espacios y limpia el campo', async () => {
			const { user, onSendMessage } = renderizar();

			await user.type(campo(), '  Hola asistente  ');
			await user.click(botonEnviar());

			expect(onSendMessage).toHaveBeenCalledWith('Hola asistente');
			expect(campo()).toHaveValue('');
		});

		it('Enter envía y Shift+Enter agrega una nueva línea', async () => {
			const { user, onSendMessage } = renderizar();

			await user.type(campo(), 'Línea 1{Shift>}{Enter}{/Shift}Línea 2');
			expect(onSendMessage).not.toHaveBeenCalled();
			expect(campo()).toHaveValue('Línea 1\nLínea 2');

			await user.keyboard('{Enter}');
			expect(onSendMessage).toHaveBeenCalledWith('Línea 1\nLínea 2');
		});

		it('mientras se envía muestra el indicador de escritura y bloquea el campo', async () => {
			let resolver!: () => void;
			const onSendMessage = vi.fn(() => new Promise<void>((r) => (resolver = r)));
			const { user } = renderizar({ onSendMessage });

			await user.type(campo(), 'Hola{Enter}');

			expect(campo()).toBeDisabled();
			resolver();
			await vi.waitFor(() => expect(campo()).toBeEnabled());
		});

		it('si el envío falla no rompe la interfaz', async () => {
			const consola = vi.spyOn(console, 'error').mockImplementation(() => {});
			const onSendMessage = vi.fn().mockRejectedValue(new Error('fallo'));
			const { user } = renderizar({ onSendMessage });

			await user.type(campo(), 'Hola{Enter}');

			await vi.waitFor(() => expect(campo()).toBeEnabled());
			expect(consola).toHaveBeenCalled();
		});
	});

	describe('streaming', () => {
		it('muestra el contenido parcial y el botón Detener', async () => {
			const onStop = vi.fn();
			const { user } = renderizar({ isStreaming: true, streamingContent: 'Escribiendo la resp', onStop });

			expect(screen.getByText('Escribiendo la resp')).toBeInTheDocument();
			expect(screen.getByRole('status')).toHaveTextContent('Escribiendo respuesta…');
			await user.click(screen.getByRole('button', { name: 'Detener generación' }));

			expect(onStop).toHaveBeenCalledOnce();
			expect(screen.queryByRole('button', { name: 'Enviar mensaje' })).not.toBeInTheDocument();
		});

		it('antes del primer fragmento anuncia que está generando', () => {
			renderizar({ isStreaming: true, streamingContent: null });

			expect(screen.getByRole('status')).toHaveTextContent('Generando respuesta…');
		});
	});

	it('muestra el error con un botón de reintentar', async () => {
		const onRetry = vi.fn();
		const { user } = renderizar({ errorMessage: 'Sin conexión', onRetry });

		expect(screen.getByRole('alert')).toHaveTextContent('Sin conexión');
		expect(screen.getByRole('status')).toHaveTextContent('Ocurrió un error en el chat.');
		await user.click(screen.getByRole('button', { name: 'Reintentar' }));

		expect(onRetry).toHaveBeenCalledOnce();
	});

	it('permite cargar mensajes anteriores', async () => {
		const onLoadMore = vi.fn();
		const { user, rerender } = renderizar({ hasMore: true, onLoadMore });

		await user.click(screen.getByRole('button', { name: 'Cargar mensajes anteriores' }));
		expect(onLoadMore).toHaveBeenCalledOnce();

		rerender(<Chatbot hasMore loadingMore onLoadMore={onLoadMore} />);
		expect(screen.getByRole('button', { name: 'Cargando…' })).toBeDisabled();
	});

	it('se cierra con el botón de cerrar', async () => {
		const onClose = vi.fn();
		const { user } = renderizar({ onClose });

		await user.click(screen.getByRole('button', { name: 'Cerrar chat' }));

		expect(onClose).toHaveBeenCalledOnce();
	});

	it('usa el selector de sesiones en la cabecera cuando se proporciona', () => {
		renderizar({ sessionSelector: <button type='button'>Selector</button> });

		expect(screen.getByRole('button', { name: 'Selector' })).toBeInTheDocument();
		expect(screen.queryByRole('heading', { name: 'Agente IA' })).not.toBeInTheDocument();
	});
});
