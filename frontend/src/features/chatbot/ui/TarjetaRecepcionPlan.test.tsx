import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { crearCambioSugerido, renderWithProviders } from '@/test';
import { TarjetaRecepcionPlan } from './TarjetaRecepcionPlan';

const renderizar = (overrides: Parameters<typeof crearCambioSugerido>[0] = {}) =>
	renderWithProviders(<TarjetaRecepcionPlan suggestion={crearCambioSugerido(overrides)} />);

describe('TarjetaRecepcionPlan', () => {
	it('muestra la descripción y la sección del cambio', () => {
		renderizar({ description: 'Añadir requisito de seguridad', section: 'Requisitos no funcionales' });

		expect(screen.getByRole('heading', { name: 'Añadir requisito de seguridad' })).toBeInTheDocument();
		expect(screen.getByText('Requisitos no funcionales')).toBeInTheDocument();
	});

	it.each([
		[true, 'Aplicado', 'No aplicado'],
		[false, 'No aplicado', 'Aplicado'],
	])('applied=%s muestra la etiqueta "%s"', (applied, visible, oculto) => {
		renderizar({ applied });

		expect(screen.getByText(visible)).toBeInTheDocument();
		expect(screen.queryByText(oculto, { exact: true })).not.toBeInTheDocument();
	});

	it('muestra el motivo cuando el cambio no se aplicó', () => {
		renderizar({ applied: false, not_applied_reason: 'La sección fue editada manualmente' });

		expect(screen.getByText('La sección fue editada manualmente')).toBeInTheDocument();
	});

	it('oculta el motivo si el cambio sí se aplicó', () => {
		renderizar({ applied: true, not_applied_reason: 'Motivo obsoleto' });

		expect(screen.queryByText('Motivo obsoleto')).not.toBeInTheDocument();
	});

	describe('diff', () => {
		it('una modificación muestra el texto anterior y el propuesto', () => {
			renderizar({ diff_before: 'Versión vieja', diff_after: 'Versión nueva' });

			expect(screen.getByText('- Anterior')).toBeInTheDocument();
			expect(screen.getByText('Versión vieja')).toBeInTheDocument();
			expect(screen.getByText('+ Propuesto')).toBeInTheDocument();
			expect(screen.getByText('Versión nueva')).toBeInTheDocument();
		});

		it('un texto nuevo (sin anterior) muestra solo lo propuesto, sin etiquetas', () => {
			renderizar({ diff_before: '', diff_after: 'Sección completamente nueva' });

			expect(screen.getByText('Sección completamente nueva')).toBeInTheDocument();
			expect(screen.queryByText('+ Propuesto')).not.toBeInTheDocument();
			expect(screen.queryByText('- Anterior')).not.toBeInTheDocument();
		});

		it.each(['', '   \n  '])('una eliminación (after=%j) muestra solo lo que se elimina', (after) => {
			renderizar({ diff_before: 'Texto a borrar', diff_after: after });

			expect(screen.getByText('- Eliminar')).toBeInTheDocument();
			expect(screen.getByText('Texto a borrar')).toBeInTheDocument();
			expect(screen.queryByText('- Anterior')).not.toBeInTheDocument();
			expect(screen.queryByText('+ Propuesto')).not.toBeInTheDocument();
		});

		it('renderiza el diff como markdown', () => {
			renderizar({ diff_before: '', diff_after: '**importante**' });

			expect(screen.getByText('importante').tagName).toBe('STRONG');
		});
	});

	it('muestra la justificación cuando existe', () => {
		renderizar({ rationale: 'Mejora la trazabilidad con el descubrimiento' });

		expect(screen.getByText('Mejora la trazabilidad con el descubrimiento')).toBeInTheDocument();
	});
});
