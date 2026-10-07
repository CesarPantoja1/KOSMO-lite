import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/shared/api';

const apiMocks = vi.hoisted(() => ({
	getConsistencyStatus: vi.fn(),
	getConsistencyReview: vi.fn(),
	applyConsistencyEvaluation: vi.fn(),
	discardConsistencyEvaluation: vi.fn(),
	bulkResolveConsistency: vi.fn(),
	getConsistencyActivity: vi.fn(),
}));

vi.mock('../api/api', () => apiMocks);

import { useConsistencyGateStore } from './gate-store';

const emptyStatus = {
	phases: {
		features: { pending: 0, evaluating: 0, failed: 0 },
		requirements: { pending: 0, evaluating: 0, failed: 0 },
		model: { pending: 0, evaluating: 0, failed: 0 },
		implementation: { pending: 0, evaluating: 0, failed: 0 },
	},
};

describe('useConsistencyGateStore', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		useConsistencyGateStore.getState().reset();
	});

	it('loadStatus guarda el estado por fase', async () => {
		apiMocks.getConsistencyStatus.mockResolvedValue({
			phases: {
				features: { pending: 2, evaluating: 1, failed: 0 },
				requirements: { pending: 0, evaluating: 0, failed: 1 },
				model: { pending: 0, evaluating: 0, failed: 0 },
				implementation: { pending: 0, evaluating: 0, failed: 0 },
			},
		});

		const status = await useConsistencyGateStore.getState().loadStatus('prj_01');

		expect(status.phases.features.pending).toBe(2);
		expect(useConsistencyGateStore.getState().status?.phases.requirements.failed).toBe(1);
	});

	it('loadReview guarda cards por fase destino', async () => {
		apiMocks.getConsistencyReview.mockResolvedValue({
			cards: [
				{
					evaluation_id: 'ev_01',
					source_phase: 'caracteristicas',
					target_phase: 'requisitos',
					target_artifact_id: 'req_01',
					artifact_type: 'EARSRequirement',
					target_display_id: 'REQ-1',
					target_title: 'Registrar gastos',
					section: 'criteria',
					rationale: 'El título de la característica cambió.',
					action: 'update',
					diff: { field: 'criteria', before: 'antes', after: 'después' },
					status: 'completed',
					failure_reason: null,
				},
			],
		});

		const cards = await useConsistencyGateStore
			.getState()
			.loadReview('prj_01', 'requirements');

		expect(cards).toHaveLength(1);
		expect(useConsistencyGateStore.getState().cardsByPhase.requirements[0].evaluation_id).toBe(
			'ev_01',
		);
	});

	it('applyEvaluation maneja el 409 stale: refetch review/status y relanza', async () => {
		apiMocks.applyConsistencyEvaluation.mockRejectedValue(
			new ApiError({
				status: 409,
				title: 'Sugerencia obsoleta',
				detail: 'La lógica de origen cambió. La sugerencia se re-evaluará automáticamente.',
			}),
		);
		apiMocks.getConsistencyReview.mockResolvedValue({ cards: [] });
		apiMocks.getConsistencyStatus.mockResolvedValue(emptyStatus);

		await expect(
			useConsistencyGateStore.getState().applyEvaluation('prj_01', 'requirements', 'ev_01'),
		).rejects.toBeInstanceOf(ApiError);

		// El refetch dispara ambas llamadas en background
		await vi.waitFor(() => {
			expect(apiMocks.getConsistencyReview).toHaveBeenCalledWith('prj_01', 'requirements');
			expect(apiMocks.getConsistencyStatus).toHaveBeenCalledWith('prj_01');
		});

		expect(useConsistencyGateStore.getState().actionByEvaluation.ev_01).toBeUndefined();
	});

	it('applyEvaluation exitosa no dispara refetch y limpia el flag de acción', async () => {
		apiMocks.applyConsistencyEvaluation.mockResolvedValue({
			evaluation_id: 'ev_01',
			applied: true,
		});

		await useConsistencyGateStore.getState().applyEvaluation('prj_01', 'requirements', 'ev_01');

		expect(apiMocks.getConsistencyReview).not.toHaveBeenCalled();
		expect(useConsistencyGateStore.getState().actionByEvaluation.ev_01).toBeUndefined();
	});

	it('applyEvaluation y discardEvaluation reducen optimistamente el conteo de pending y remueven la card', async () => {
		useConsistencyGateStore.setState({
			status: {
				phases: {
					features: { pending: 2, evaluating: 0, failed: 0 },
					requirements: { pending: 3, evaluating: 0, failed: 0 },
					model: { pending: 1, evaluating: 0, failed: 0 },
					implementation: { pending: 1, evaluating: 0, failed: 0 },
				},
			},
			cardsByPhase: {
				requirements: [
					{
						evaluation_id: 'ev_01',
						source_phase: 'features',
						target_phase: 'requirements',
						target_artifact_id: 'req_01',
						artifact_type: 'EARSRequirement',
						target_display_id: 'REQ-1.1',
						target_title: 'Req 1',
						section: 'content',
						rationale: 'Diff',
						action: 'update',
						diff: null,
						status: 'completed',
						failure_reason: null,
					},
					{
						evaluation_id: 'ev_02',
						source_phase: 'features',
						target_phase: 'requirements',
						target_artifact_id: 'req_02',
						artifact_type: 'EARSRequirement',
						target_display_id: 'REQ-1.2',
						target_title: 'Req 2',
						section: 'content',
						rationale: 'Diff',
						action: 'update',
						diff: null,
						status: 'completed',
						failure_reason: null,
					},
				],
			},
		});

		apiMocks.applyConsistencyEvaluation.mockResolvedValue({
			evaluation_id: 'ev_01',
			applied: true,
		});

		await useConsistencyGateStore.getState().applyEvaluation('prj_01', 'requirements', 'ev_01');

		let state = useConsistencyGateStore.getState();
		expect(state.status?.phases.requirements.pending).toBe(2);
		expect(state.cardsByPhase.requirements).toHaveLength(1);
		expect(state.cardsByPhase.requirements[0].evaluation_id).toBe('ev_02');

		apiMocks.discardConsistencyEvaluation.mockResolvedValue({
			evaluation_id: 'ev_02',
			discarded: true,
		});

		await useConsistencyGateStore.getState().discardEvaluation('prj_01', 'requirements', 'ev_02');

		state = useConsistencyGateStore.getState();
		expect(state.status?.phases.requirements.pending).toBe(1);
		expect(state.cardsByPhase.requirements).toHaveLength(0);
	});

	it('bulkResolve devuelve el resultado del backend', async () => {
		apiMocks.bulkResolveConsistency.mockResolvedValue({ resolved: 3, skipped: 1 });

		const result = await useConsistencyGateStore
			.getState()
			.bulkResolve('prj_01', 'apply', 'requirements');

		expect(result).toEqual({ resolved: 3, skipped: 1 });
	});

	it('loadActivity guarda el feed', async () => {
		apiMocks.getConsistencyActivity.mockResolvedValue({
			items: [
				{
					evaluation_id: 'ev_02',
					status: 'applied',
					source_phase: 'caracteristicas',
					target_phase: 'requisitos',
					target_artifact_id: 'req_01',
					target_title: 'Registrar gastos',
					failure_reason: null,
					updated_at: '2026-08-14T12:00:00Z',
				},
			],
		});

		const items = await useConsistencyGateStore.getState().loadActivity('prj_01');

		expect(items).toHaveLength(1);
		expect(useConsistencyGateStore.getState().activity?.[0].status).toBe('applied');
	});
});
