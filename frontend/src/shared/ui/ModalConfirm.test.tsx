import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test';
import { ModalConfirm } from './ModalConfirm';

function renderizar(props: Partial<Parameters<typeof ModalConfirm>[0]> = {}) {
	const onCancel = vi.fn();
	const onConfirm = vi.fn();
	const utils = renderWithProviders(
		<ModalConfirm onCancel={onCancel} onConfirm={onConfirm} {...props} />,
	);
	return { ...utils, onCancel, onConfirm };
}

describe('ModalConfirm', () => {
	it('muestra el título y la descripción por defecto', () => {
		renderizar();

		expect(
			screen.getByRole('dialog', { name: 'Cambios sin guardar' }),
		).toBeInTheDocument();
		expect(
			screen.getByText('Si sale ahora, perderá las modificaciones recientes.'),
		).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Cancelar' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Aceptar' })).toBeInTheDocument();
	});

	it('acepta textos personalizados', () => {
		renderizar({
			title: 'Eliminar proyecto',
			description: 'Esta acción no se puede deshacer.',
			cancelText: 'Volver',
			confirmText: 'Eliminar',
		});

		expect(screen.getByRole('dialog', { name: 'Eliminar proyecto' })).toBeInTheDocument();
		expect(screen.getByText('Esta acción no se puede deshacer.')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Volver' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Eliminar' })).toBeInTheDocument();
	});

	it('enfoca el botón de confirmar al abrirse', () => {
		renderizar();

		expect(screen.getByRole('button', { name: 'Aceptar' })).toHaveFocus();
	});

	it('confirma con clic y con la tecla Enter sobre el botón enfocado', async () => {
		const { user, onConfirm, onCancel } = renderizar();

		await user.click(screen.getByRole('button', { name: 'Aceptar' }));
		await user.keyboard('{Enter}');

		expect(onConfirm).toHaveBeenCalledTimes(2);
		expect(onCancel).not.toHaveBeenCalled();
	});

	it('cancela con el botón Cancelar', async () => {
		const { user, onCancel, onConfirm } = renderizar();

		await user.click(screen.getByRole('button', { name: 'Cancelar' }));

		expect(onCancel).toHaveBeenCalledOnce();
		expect(onConfirm).not.toHaveBeenCalled();
	});

	it('cancela con la tecla Escape', async () => {
		const { user, onCancel } = renderizar();

		await user.keyboard('{Escape}');

		expect(onCancel).toHaveBeenCalledOnce();
	});

	it('cancela al hacer clic fuera del diálogo, pero no al hacer clic dentro', async () => {
		const { user, onCancel } = renderizar();
		const dialogo = screen.getByRole('dialog');

		await user.click(screen.getByText('Cambios sin guardar'));
		expect(onCancel).not.toHaveBeenCalled();

		await user.click(dialogo.parentElement!);
		expect(onCancel).toHaveBeenCalledOnce();
	});

	it('deja de escuchar Escape al desmontarse', async () => {
		const { user, onCancel, unmount } = renderizar();

		unmount();
		await user.keyboard('{Escape}');

		expect(onCancel).not.toHaveBeenCalled();
	});
});
