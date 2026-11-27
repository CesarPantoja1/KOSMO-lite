import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useAppStore } from '@/features/app-state';
import { crearEstadoConsistencia, mockRouter, renderWithProviders } from '@/test';
import { ConsistencyGateButton } from './ConsistencyGateButton';

const fase = (pending = 0, evaluating = 0, failed = 0) => ({
	pending,
	evaluating,
	failed,
});

describe('ConsistencyGateButton', () => {
	it.each([
		['sin estado', null],
		['con todas las fases consistentes', crearEstadoConsistencia()],
	])('no se muestra %s', (_caso, status) => {
		const { container } = renderWithProviders(<ConsistencyGateButton status={status} />);

		expect(container).toBeEmptyDOMElement();
	});

	it('indica cuántos cambios pendientes hay en total (singular y plural)', () => {
		const { rerender } = renderWithProviders(
			<ConsistencyGateButton status={crearEstadoConsistencia({ features: fase(1) })} />,
		);
		expect(
			screen.getByRole('button', { name: 'Revisar consistencia (1 pendiente)' }),
		).toBeInTheDocument();

		rerender(
			<ConsistencyGateButton
				status={crearEstadoConsistencia({ features: fase(1), requirements: fase(2) })}
			/>,
		);
		expect(
			screen.getByRole('button', { name: 'Revisar consistencia (3 pendientes)' }),
		).toBeInTheDocument();
	});

	it('mientras solo se evalúa muestra un estado informativo sin acción', () => {
		renderWithProviders(
			<ConsistencyGateButton
				status={crearEstadoConsistencia({ features: fase(0, 1) })}
			/>,
		);

		expect(screen.getByText('Analizando consistencia…')).toBeInTheDocument();
		expect(screen.queryByRole('button')).not.toBeInTheDocument();
	});

	it.each([
		['características', { features: fase(1) }, '/proyecto/caracteristicas/consistencia'],
		['requisitos', { requirements: fase(1) }, '/proyecto/requisitos/consistencia'],
		['código', { implementation: fase(0, 0, 1) }, '/proyecto/codigo/consistencia'],
	])('lleva a la revisión de %s', async (_caso, phases, ruta) => {
		const { user } = renderWithProviders(
			<ConsistencyGateButton status={crearEstadoConsistencia(phases)} />,
		);

		await user.click(screen.getByRole('button'));

		expect(mockRouter.push).toHaveBeenCalledWith(ruta);
	});

	it('con cambios sin guardar no navega: deja la ruta pendiente de confirmación', async () => {
		useAppStore.setState({ hasUnsavedChanges: true });
		const { user } = renderWithProviders(
			<ConsistencyGateButton status={crearEstadoConsistencia({ features: fase(1) })} />,
		);

		await user.click(screen.getByRole('button'));

		expect(mockRouter.push).not.toHaveBeenCalled();
		expect(useAppStore.getState().pendingNavigationPath).toBe(
			'/proyecto/caracteristicas/consistencia',
		);
	});
});
