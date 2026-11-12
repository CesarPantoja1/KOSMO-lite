import { act, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test';
import { SaveIndicator } from './save-indicator';

describe('SaveIndicator', () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('no muestra nada en reposo', () => {
		const { container } = renderWithProviders(<SaveIndicator status='idle' />);

		expect(container).toBeEmptyDOMElement();
	});

	it.each([
		['saving', 'Guardando...'],
		['saved', 'Guardado'],
		['error', 'No se pudo guardar'],
	] as const)('en estado %s muestra "%s"', (status, texto) => {
		renderWithProviders(<SaveIndicator status={status} />);

		expect(screen.getByText(texto)).toBeInTheDocument();
	});

	it('acepta mensajes personalizados', () => {
		const { rerender } = renderWithProviders(
			<SaveIndicator status='saving' saveMessage='Sincronizando…' />,
		);
		expect(screen.getByText('Sincronizando…')).toBeInTheDocument();

		rerender(<SaveIndicator status='saved' savedMessage='Cambios guardados' />);
		expect(screen.getByText('Cambios guardados')).toBeInTheDocument();

		rerender(<SaveIndicator status='error' errorMessage='Sin conexión' />);
		expect(screen.getByText('Sin conexión')).toBeInTheDocument();
	});

	it('el indicador de guardando es visible de inmediato', () => {
		renderWithProviders(<SaveIndicator status='saving' />);

		expect(screen.getByText('Guardando...').closest('[style]')).toHaveStyle({
			opacity: '1',
		});
	});

	it('"Guardado" aparece y se desvanece a los 2,5 s', () => {
		renderWithProviders(<SaveIndicator status='saved' />);
		const indicador = screen.getByText('Guardado').closest('[style]');
		expect(indicador).toHaveStyle({ opacity: '1' });

		act(() => vi.advanceTimersByTime(2_500));

		expect(indicador).toHaveStyle({ opacity: '0' });
	});

	it('el error permanece visible más tiempo (4 s) antes de desvanecerse', () => {
		renderWithProviders(<SaveIndicator status='error' />);
		const indicador = screen.getByText('No se pudo guardar').closest('[style]');

		act(() => vi.advanceTimersByTime(2_500));
		expect(indicador).toHaveStyle({ opacity: '1' });

		act(() => vi.advanceTimersByTime(1_500));
		expect(indicador).toHaveStyle({ opacity: '0' });
	});

	it('un nuevo guardado cancela el desvanecimiento pendiente', () => {
		const { rerender } = renderWithProviders(<SaveIndicator status='saved' />);
		act(() => vi.advanceTimersByTime(2_000));

		rerender(<SaveIndicator status='saving' />);
		act(() => vi.advanceTimersByTime(5_000));

		expect(screen.getByText('Guardando...').closest('[style]')).toHaveStyle({
			opacity: '1',
		});
	});

	it('limpia el temporizador al desmontarse', () => {
		const { unmount } = renderWithProviders(<SaveIndicator status='saved' />);

		unmount();

		expect(vi.getTimerCount()).toBe(0);
	});
});
