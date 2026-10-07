import { describe, expect, it } from 'vitest';
import type { ConsistencyStatusResponse } from './types';
import {
	CONSISTENCY_REVIEW_ROUTES,
	firstPhaseToReview,
	sumPhaseStatus,
} from './selectors';

const emptyStatus: ConsistencyStatusResponse = {
	phases: {
		features: { pending: 0, evaluating: 0, failed: 0 },
		requirements: { pending: 0, evaluating: 0, failed: 0 },
		model: { pending: 0, evaluating: 0, failed: 0 },
		implementation: { pending: 0, evaluating: 0, failed: 0 },
	},
};

describe('selectors de consistencia', () => {
	it('sumPhaseStatus suma el indicador pedido entre todas las fases', () => {
		const status: ConsistencyStatusResponse = {
			phases: {
				features: { pending: 2, evaluating: 1, failed: 0 },
				requirements: { pending: 1, evaluating: 0, failed: 1 },
				model: { pending: 0, evaluating: 2, failed: 0 },
				implementation: { pending: 1, evaluating: 0, failed: 0 },
			},
		};

		expect(sumPhaseStatus(status, 'pending')).toBe(4);
		expect(sumPhaseStatus(status, 'evaluating')).toBe(3);
		expect(sumPhaseStatus(status, 'failed')).toBe(1);
	});

	it('sumPhaseStatus devuelve 0 con estado nulo', () => {
		expect(sumPhaseStatus(null, 'pending')).toBe(0);
	});

	it('firstPhaseToReview elige la primera fase con pendientes en orden de flujo', () => {
		const status: ConsistencyStatusResponse = {
			phases: {
				features: { pending: 0, evaluating: 0, failed: 0 },
				requirements: { pending: 0, evaluating: 0, failed: 0 },
				model: { pending: 4, evaluating: 0, failed: 0 },
				implementation: { pending: 0, evaluating: 0, failed: 0 },
			},
		};

		expect(firstPhaseToReview(status)).toBe('model');
	});

	it('firstPhaseToReview cae a la primera fase con fallos si no hay pendientes', () => {
		const status: ConsistencyStatusResponse = {
			phases: {
				features: { pending: 0, evaluating: 0, failed: 0 },
				requirements: { pending: 0, evaluating: 0, failed: 1 },
				model: { pending: 0, evaluating: 0, failed: 1 },
				implementation: { pending: 0, evaluating: 0, failed: 0 },
			},
		};

		expect(firstPhaseToReview(status)).toBe('requirements');
	});

	it('firstPhaseToReview devuelve features como respaldo total', () => {
		expect(firstPhaseToReview(emptyStatus)).toBe('features');
		expect(firstPhaseToReview(null)).toBe('features');
	});

	it('CONSISTENCY_REVIEW_ROUTES cubre las cuatro fases', () => {
		expect(CONSISTENCY_REVIEW_ROUTES).toEqual({
			features: '/proyecto/caracteristicas/consistencia',
			requirements: '/proyecto/requisitos/consistencia',
			model: '/proyecto/modelo/consistencia',
			implementation: '/proyecto/codigo/consistencia',
		});
	});
});
