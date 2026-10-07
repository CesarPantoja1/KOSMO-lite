import { apiClient } from '@/shared/api';
import { USE_MOCKS } from '@/shared/api/config';
import type {
	BulkResolveResult,
	ConsistencyActivityResponse,
	ConsistencyReviewResponse,
	ConsistencyStatusResponse,
	EvaluationActionResult,
} from '../model/types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// ═══ Consistencia persistente (gate) ═══

const emptyStatus: ConsistencyStatusResponse = {
	phases: {
		features: { pending: 0, evaluating: 0, failed: 0 },
		requirements: { pending: 0, evaluating: 0, failed: 0 },
		model: { pending: 0, evaluating: 0, failed: 0 },
		implementation: { pending: 0, evaluating: 0, failed: 0 },
	},
};

const mockGetConsistencyStatus = async (): Promise<ConsistencyStatusResponse> => {
	await delay(200);
	return emptyStatus;
};

const realGetConsistencyStatus = async (
	projectId: string,
): Promise<ConsistencyStatusResponse> => {
	return apiClient<ConsistencyStatusResponse>(
		`/api/v1/projects/${projectId}/consistency/status`,
		{ method: 'GET' },
	);
};

export const getConsistencyStatus = (
	projectId: string,
): Promise<ConsistencyStatusResponse> =>
	USE_MOCKS ? mockGetConsistencyStatus() : realGetConsistencyStatus(projectId);

const mockGetConsistencyReview = async (): Promise<ConsistencyReviewResponse> => {
	await delay(300);
	return { cards: [] };
};

const realGetConsistencyReview = async (
	projectId: string,
	targetPhase: string,
): Promise<ConsistencyReviewResponse> => {
	return apiClient<ConsistencyReviewResponse>(
		`/api/v1/projects/${projectId}/consistency/review?target_phase=${targetPhase}`,
		{ method: 'GET' },
	);
};

export const getConsistencyReview = (
	projectId: string,
	targetPhase: string,
): Promise<ConsistencyReviewResponse> =>
	USE_MOCKS
		? mockGetConsistencyReview()
		: realGetConsistencyReview(projectId, targetPhase);

const mockApplyEvaluation = async (
	evaluationId: string,
): Promise<EvaluationActionResult> => {
	await delay(300);
	return { evaluation_id: evaluationId, applied: true };
};

const realApplyEvaluation = async (
	projectId: string,
	evaluationId: string,
): Promise<EvaluationActionResult> => {
	return apiClient<EvaluationActionResult>(
		`/api/v1/projects/${projectId}/consistency/evaluations/${evaluationId}/apply`,
		{ method: 'POST' },
	);
};

export const applyConsistencyEvaluation = (
	projectId: string,
	evaluationId: string,
): Promise<EvaluationActionResult> =>
	USE_MOCKS
		? mockApplyEvaluation(evaluationId)
		: realApplyEvaluation(projectId, evaluationId);

const mockDiscardEvaluation = async (
	evaluationId: string,
): Promise<EvaluationActionResult> => {
	await delay(300);
	return { evaluation_id: evaluationId, discarded: true };
};

const realDiscardEvaluation = async (
	projectId: string,
	evaluationId: string,
): Promise<EvaluationActionResult> => {
	return apiClient<EvaluationActionResult>(
		`/api/v1/projects/${projectId}/consistency/evaluations/${evaluationId}/discard`,
		{ method: 'POST' },
	);
};

export const discardConsistencyEvaluation = (
	projectId: string,
	evaluationId: string,
): Promise<EvaluationActionResult> =>
	USE_MOCKS
		? mockDiscardEvaluation(evaluationId)
		: realDiscardEvaluation(projectId, evaluationId);

const mockBulkResolve = async (): Promise<BulkResolveResult> => {
	await delay(300);
	return { resolved: 0, skipped: 0 };
};

const realBulkResolve = async (
	projectId: string,
	action: 'apply' | 'discard',
	targetPhase: string,
): Promise<BulkResolveResult> => {
	return apiClient<BulkResolveResult>(
		`/api/v1/projects/${projectId}/consistency/review/bulk`,
		{
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ action, target_phase: targetPhase }),
		},
	);
};

export const bulkResolveConsistency = (
	projectId: string,
	action: 'apply' | 'discard',
	targetPhase: string,
): Promise<BulkResolveResult> =>
	USE_MOCKS
		? mockBulkResolve()
		: realBulkResolve(projectId, action, targetPhase);

const mockGetConsistencyActivity = async (): Promise<ConsistencyActivityResponse> => {
	await delay(300);
	return { items: [] };
};

const realGetConsistencyActivity = async (
	projectId: string,
	limit: number,
): Promise<ConsistencyActivityResponse> => {
	return apiClient<ConsistencyActivityResponse>(
		`/api/v1/projects/${projectId}/consistency/activity?limit=${limit}`,
		{ method: 'GET' },
	);
};

export const getConsistencyActivity = (
	projectId: string,
	limit = 50,
): Promise<ConsistencyActivityResponse> =>
	USE_MOCKS
		? mockGetConsistencyActivity()
		: realGetConsistencyActivity(projectId, limit);
