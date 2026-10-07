import type { ConsistencyStatusResponse, ConsistencyTargetPhase } from './types';

export const CONSISTENCY_PHASE_ORDER: ConsistencyTargetPhase[] = [
	'features',
	'requirements',
	'model',
	'implementation',
];

export const CONSISTENCY_REVIEW_ROUTES: Record<ConsistencyTargetPhase, string> = {
	features: '/proyecto/caracteristicas/consistencia',
	requirements: '/proyecto/requisitos/consistencia',
	model: '/proyecto/modelo/consistencia',
	implementation: '/proyecto/codigo/consistencia',
};

export function sumPhaseStatus(
	status: ConsistencyStatusResponse | null,
	key: 'pending' | 'evaluating' | 'failed',
): number {
	if (!status) return 0;
	return CONSISTENCY_PHASE_ORDER.reduce(
		(total, phase) => total + status.phases[phase][key],
		0,
	);
}

export function firstPhaseToReview(
	status: ConsistencyStatusResponse | null,
): ConsistencyTargetPhase {
	return (
		CONSISTENCY_PHASE_ORDER.find(
			(phase) => (status?.phases[phase].pending ?? 0) > 0,
		) ??
		CONSISTENCY_PHASE_ORDER.find(
			(phase) => (status?.phases[phase].failed ?? 0) > 0,
		) ??
		'features'
	);
}
