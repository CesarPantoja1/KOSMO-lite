import { fireEvent, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatSessionSummary } from '@/entities/chat';
import { crearSesionChat, renderWithProviders } from '@/test';
import { SessionSelector } from './SessionSelector';

const AHORA = new Date('2026-01-15T12:00:00.000Z');
const haceMinutos = (min: number) => new Date(AHORA.getTime() - min * 60_000).toISOString();

function renderizar(
	sessions: ChatSessionSummary[] = [],
	props: Partial<Parameters<typeof SessionSelector>[0]> = {},
) {
	const onSelect = vi.fn();
	const onCreate = vi.fn();
	const onDelete = vi.fn();
	const utils = renderWithProviders(
		<SessionSelector
			sessions={sessions}
			activeSessionId={null}
			loading={false}
			onSelect={onSelect}
			onCreate={onCreate}
			onDelete={onDelete}
			{...props}
		/>,
	);
	return { ...utils, onSelect, onCreate, onDelete };
}

const selector = () => screen.getByRole('button', { name: 'Seleccionar chat' });

/**
 * El menú se abre con hover y se cierra con mouseleave. En jsdom (sin layout) user-event mueve
 * el puntero con un `mouseout` sin `relatedTarget`, que React interpreta como salir de la
 * ventana y cierra el menú antes del clic. Por eso, dentro del menú se usa fireEvent.click,
 * que hace clic sin mover el puntero.
 */
const clicEnMenu = (el: HTMLElement) => fireEvent.click(el);

describe('SessionSelector', () => {
	beforeEach(() => {
		vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['Date'] });
		vi.setSystemTime(AHORA);
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('cerrado muestra el título y no la lista', () => {
		renderizar();

		expect(selector()).toHaveAttribute('aria-expanded', 'false');
		expect(screen.getByRole('heading', { name: 'Agente IA' })).toBeInTheDocument();
		expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
	});

	it('se abre al pasar el ratón y se cierra al salir', async () => {
		const { user } = renderizar();

		await user.hover(selector());
		expect(screen.getByRole('listbox', { name: 'Chats' })).toBeInTheDocument();
		expect(selector()).toHaveAttribute('aria-expanded', 'true');

		await user.unhover(selector());
		expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
	});

	it('se cierra con Escape', async () => {
		const { user } = renderizar();
		await user.hover(selector());

		await user.keyboard('{Escape}');

		expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
	});

	it('sin sesiones indica que no hay otros chats', async () => {
		const { user } = renderizar();

		await user.hover(selector());

		expect(screen.getByText('Aún no hay otros chats.')).toBeInTheDocument();
	});

	it('lista las sesiones con su antigüedad relativa', async () => {
		const { user } = renderizar([
			crearSesionChat({ title: 'Minutos', last_message_at: haceMinutos(5) }),
			crearSesionChat({ title: 'Horas', last_message_at: haceMinutos(180) }),
			crearSesionChat({ title: 'Días', last_message_at: null, created_at: haceMinutos(60 * 48) }),
		]);

		await user.hover(selector());

		expect(screen.getByRole('option', { name: /Minutos.*hace 5 min/ })).toBeInTheDocument();
		expect(screen.getByRole('option', { name: /Horas.*hace 3 h/ })).toBeInTheDocument();
		expect(screen.getByRole('option', { name: /Días.*hace 2 d/ })).toBeInTheDocument();
	});

	it('nombra "Chat N" a las sesiones sin título', async () => {
		const { user } = renderizar([crearSesionChat({ title: '' }), crearSesionChat({ title: '  ' })]);

		await user.hover(selector());

		expect(screen.getByRole('option', { name: /Chat 1/ })).toBeInTheDocument();
		expect(screen.getByRole('option', { name: /Chat 2/ })).toBeInTheDocument();
	});

	it('marca la sesión activa y muestra su nombre al abrir', async () => {
		const sesiones = [crearSesionChat({ id: 'ses_a', title: 'Login' }), crearSesionChat({ id: 'ses_b', title: 'Pagos' })];
		const { user } = renderizar(sesiones, { activeSessionId: 'ses_b' });

		await user.hover(selector());

		expect(screen.getByRole('option', { name: /Pagos/ })).toHaveAttribute('aria-selected', 'true');
		expect(screen.getByRole('option', { name: /Login/ })).toHaveAttribute('aria-selected', 'false');
		expect(selector()).toHaveTextContent('Pagos');
	});

	it('elegir una sesión la selecciona y cierra la lista', async () => {
		const { user, onSelect } = renderizar([crearSesionChat({ id: 'ses_a', title: 'Login' })]);
		await user.hover(selector());

		clicEnMenu(screen.getByRole('option', { name: /Login/ }));

		expect(onSelect).toHaveBeenCalledWith('ses_a');
		expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
	});

	it('crea un nuevo chat', async () => {
		const { user, onCreate } = renderizar();
		await user.hover(selector());

		clicEnMenu(screen.getByRole('button', { name: 'Nuevo chat' }));

		expect(onCreate).toHaveBeenCalledOnce();
	});

	it('está deshabilitado mientras carga', () => {
		renderizar([], { loading: true });

		expect(selector()).toBeDisabled();
	});
});
