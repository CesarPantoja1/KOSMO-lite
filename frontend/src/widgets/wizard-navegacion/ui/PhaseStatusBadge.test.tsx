import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { PhaseConsistencyStatus } from '@/entities/consistency';
import { renderWithProviders } from '@/test';
import { PhaseStatusBadge } from './PhaseStatusBadge';

const estado = (
	overrides: Partial<PhaseConsistencyStatus> = {},
): PhaseConsistencyStatus => ({
	pending: 0,
	evaluating: 0,
	failed: 0,
	...overrides,
});

describe('PhaseStatusBadge', () => {
	it('no muestra nada cuando la fase es consistente', () => {
		const { container } = renderWithProviders(<PhaseStatusBadge status={estado()} />);

		expect(container).toBeEmptyDOMElement();
	});

	it.each([
		['evaluando', estado({ evaluating: 2 }), 'Evaluando consistencia (2)'],
		[
			'con cambios pendientes',
			estado({ pending: 3 }),
			'3 cambio(s) pendiente(s) de revisión',
		],
		['con fallos', estado({ failed: 1 }), 'Fallos en la evaluación (1)'],
	])('describe el estado de una fase %s', (_caso, status, titulo) => {
		renderWithProviders(<PhaseStatusBadge status={status} />);

		expect(screen.getByTitle(titulo)).toBeInTheDocument();
	});

	it('muestra el número de cambios pendientes', () => {
		renderWithProviders(<PhaseStatusBadge status={estado({ pending: 4 })} />);

		expect(screen.getByTitle(/pendiente/)).toHaveTextContent('4');
	});
});
