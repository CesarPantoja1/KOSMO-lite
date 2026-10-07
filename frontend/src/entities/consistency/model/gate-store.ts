'use client';

import { create } from 'zustand';
import { ApiError } from '@/shared/api';
import {
	applyConsistencyEvaluation,
	bulkResolveConsistency,
	discardConsistencyEvaluation,
	getConsistencyActivity,
	getConsistencyReview,
	getConsistencyStatus,
} from '../api/api';
import type {
	BulkResolveResult,
	ConsistencyActivityItem,
	ConsistencyStatusResponse,
	ConsistencyTargetPhase,
	EvaluationActionResult,
	ReviewCard,
} from './types';

interface ConsistencyGateState {
	status: ConsistencyStatusResponse | null;
	statusError: unknown;
	cardsByPhase: Record<string, ReviewCard[]>;
	reviewLoading: boolean;
	reviewError: unknown;
	activity: ConsistencyActivityItem[] | null;
	activityLoading: boolean;
	actionByEvaluation: Record<string, boolean>;

	loadStatus: (projectId: string) => Promise<ConsistencyStatusResponse>;
	loadReview: (projectId: string, targetPhase: string) => Promise<ReviewCard[]>;
	applyEvaluation: (
		projectId: string,
		targetPhase: string,
		evaluationId: string,
	) => Promise<EvaluationActionResult>;
	discardEvaluation: (
		projectId: string,
		targetPhase: string,
		evaluationId: string,
	) => Promise<EvaluationActionResult>;
	bulkResolve: (
		projectId: string,
		action: 'apply' | 'discard',
		targetPhase: string,
	) => Promise<BulkResolveResult>;
	loadActivity: (projectId: string) => Promise<ConsistencyActivityItem[]>;
	reset: () => void;
}

export const useConsistencyGateStore = create<ConsistencyGateState>()((set, get) => ({
	status: null,
	statusError: null,
	cardsByPhase: {},
	reviewLoading: false,
	reviewError: null,
	activity: null,
	activityLoading: false,
	actionByEvaluation: {},

	loadStatus: async (projectId) => {
		try {
			const status = await getConsistencyStatus(projectId);
			set({ status, statusError: null });
			return status;
		} catch (error) {
			set({ statusError: error });
			throw error;
		}
	},

	loadReview: async (projectId, targetPhase) => {
		set({ reviewLoading: true, reviewError: null });
		try {
			const response = await getConsistencyReview(projectId, targetPhase);
			set((state) => ({
				cardsByPhase: { ...state.cardsByPhase, [targetPhase]: response.cards },
				reviewLoading: false,
			}));
			return response.cards;
		} catch (error) {
			set({ reviewLoading: false, reviewError: error });
			throw error;
		}
	},

	applyEvaluation: async (projectId, targetPhase, evaluationId) => {
		set((state) => ({
			actionByEvaluation: { ...state.actionByEvaluation, [evaluationId]: true },
		}));
		try {
			const result = await applyConsistencyEvaluation(projectId, evaluationId);
			set((state) => {
				const currentCards = state.cardsByPhase[targetPhase] ?? [];
				const updatedCards = currentCards.filter((c) => c.evaluation_id !== evaluationId);
				const currentPhaseStatus = state.status?.phases?.[targetPhase as ConsistencyTargetPhase];
				const newPending = Math.max(0, (currentPhaseStatus?.pending ?? 1) - 1);
				return {
					cardsByPhase: {
						...state.cardsByPhase,
						[targetPhase]: updatedCards,
					},
					status:
						state.status && currentPhaseStatus
							? {
									...state.status,
									phases: {
										...state.status.phases,
										[targetPhase as ConsistencyTargetPhase]: {
											...currentPhaseStatus,
											pending: newPending,
										},
									},
							  }
							: state.status,
				};
			});
			return result;
		} catch (error) {
			// 409: la sugerencia quedó obsoleta; el backend la re-evalúa automáticamente
			if (error instanceof ApiError && error.status === 409) {
				void get().loadReview(projectId, targetPhase).catch(() => undefined);
				void get().loadStatus(projectId).catch(() => undefined);
			}
			throw error;
		} finally {
			set((state) => {
				const next = { ...state.actionByEvaluation };
				delete next[evaluationId];
				return { actionByEvaluation: next };
			});
		}
	},

	discardEvaluation: async (projectId, targetPhase, evaluationId) => {
		set((state) => ({
			actionByEvaluation: { ...state.actionByEvaluation, [evaluationId]: true },
		}));
		try {
			const result = await discardConsistencyEvaluation(projectId, evaluationId);
			set((state) => {
				const currentCards = state.cardsByPhase[targetPhase] ?? [];
				const updatedCards = currentCards.filter((c) => c.evaluation_id !== evaluationId);
				const currentPhaseStatus = state.status?.phases?.[targetPhase as ConsistencyTargetPhase];
				const newPending = Math.max(0, (currentPhaseStatus?.pending ?? 1) - 1);
				return {
					cardsByPhase: {
						...state.cardsByPhase,
						[targetPhase]: updatedCards,
					},
					status:
						state.status && currentPhaseStatus
							? {
									...state.status,
									phases: {
										...state.status.phases,
										[targetPhase as ConsistencyTargetPhase]: {
											...currentPhaseStatus,
											pending: newPending,
										},
									},
							  }
							: state.status,
				};
			});
			return result;
		} catch (error) {
			if (error instanceof ApiError && error.status === 409) {
				void get().loadReview(projectId, targetPhase).catch(() => undefined);
				void get().loadStatus(projectId).catch(() => undefined);
			}
			throw error;
		} finally {
			set((state) => {
				const next = { ...state.actionByEvaluation };
				delete next[evaluationId];
				return { actionByEvaluation: next };
			});
		}
	},

	bulkResolve: async (projectId, action, targetPhase) => {
		const result = await bulkResolveConsistency(projectId, action, targetPhase);
		set((state) => {
			const currentPhaseStatus = state.status?.phases?.[targetPhase as ConsistencyTargetPhase];
			return {
				cardsByPhase: {
					...state.cardsByPhase,
					[targetPhase]: [],
				},
				status:
					state.status && currentPhaseStatus
						? {
								...state.status,
								phases: {
									...state.status.phases,
									[targetPhase as ConsistencyTargetPhase]: {
										...currentPhaseStatus,
										pending: 0,
									},
								},
						  }
						: state.status,
			};
		});
		return result;
	},

	loadActivity: async (projectId) => {
		set({ activityLoading: true });
		try {
			const response = await getConsistencyActivity(projectId);
			set({ activity: response.items, activityLoading: false });
			return response.items;
		} catch (error) {
			set({ activityLoading: false });
			throw error;
		}
	},

	reset: () =>
		set({
			status: null,
			statusError: null,
			cardsByPhase: {},
			reviewLoading: false,
			reviewError: null,
			activity: null,
			activityLoading: false,
			actionByEvaluation: {},
		}),
}));
