import { act, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test';
import { toast } from './toast';

const mostrar = (fn: () => unknown) => act(() => void fn());

describe('toast + ToasterProvider', () => {
	it.each([
		['success', () => toast.success('Proyecto creado')],
		['error', () => toast.error('Proyecto creado')],
		['warning', () => toast.warning('Proyecto creado')],
		['info', () => toast.info('Proyecto creado')],
	])('muestra un toast de tipo %s con su mensaje', async (_variante, lanzar) => {
		renderWithProviders(<div />);

		mostrar(lanzar);

		expect(await screen.findByText('Proyecto creado')).toBeInTheDocument();
	});

	it('muestra el título cuando se indica', async () => {
		renderWithProviders(<div />);

		mostrar(() => toast.warning('Se parece a F-001', undefined, 'Advertencia de solapamiento'));

		const alerta = await screen.findByRole('alertdialog');
		expect(within(alerta).getByText('Advertencia de solapamiento')).toBeInTheDocument();
		expect(within(alerta).getByText('Se parece a F-001')).toBeInTheDocument();
	});

	it('se cierra con el botón de cerrar', async () => {
		const { user } = renderWithProviders(<div />);
		mostrar(() => toast.info('Mensaje temporal'));
		const alerta = await screen.findByRole('alertdialog');

		await user.click(within(alerta).getByRole('button', { name: /cerrar|close|dismiss/i }));

		expect(screen.queryByText('Mensaje temporal')).not.toBeInTheDocument();
	});

	it('ejecuta la acción del toast y lo cierra', async () => {
		const onAction = vi.fn();
		const { user } = renderWithProviders(<div />);
		mostrar(() =>
			toast.add({ variant: 'error', message: 'Falló el guardado', action: { label: 'Reintentar', onAction } }),
		);

		await user.click(await screen.findByRole('button', { name: 'Reintentar' }));

		expect(onAction).toHaveBeenCalledOnce();
		expect(screen.queryByText('Falló el guardado')).not.toBeInTheDocument();
	});

	it('toast.close() cierra un toast por su clave', async () => {
		renderWithProviders(<div />);
		let clave = '';
		mostrar(() => (clave = toast.success('Para cerrar')));
		await screen.findByText('Para cerrar');

		mostrar(() => toast.close(clave));

		expect(screen.queryByText('Para cerrar')).not.toBeInTheDocument();
	});

	it('desaparece solo tras el tiempo de espera', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		renderWithProviders(<div />);
		mostrar(() => toast.info('Efímero', { timeout: 1_000 }));
		expect(await screen.findByText('Efímero')).toBeInTheDocument();

		await act(() => vi.advanceTimersByTimeAsync(1_100));

		expect(screen.queryByText('Efímero')).not.toBeInTheDocument();
		vi.useRealTimers();
	});
});
