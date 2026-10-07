import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { fetchImplementation, generateImplementation } from '../api/api';
import { buildSummary } from '../api/api';
import type { ImplementationLog, ImplementationStatus, ImplementationSummary } from './types';

interface ImplementationStore {
	status: ImplementationStatus;
	summary: ImplementationSummary | null;
	progress: string | null;
	currentThought: string | null;
	logs: ImplementationLog[];
	errorMessage: string | null;
	implementations: Record<string, boolean>;
	requiresReviewByFeature: Record<string, boolean>;
	startGeneration: (
		featureId: string,
		featureTitle: string,
		featureDisplayId: string,
	) => Promise<void>;
	loadImplementation: (
		featureId: string,
		featureTitle: string,
		featureDisplayId: string,
	) => Promise<void>;
	reset: () => void;
}

export const useImplementationStore = create<ImplementationStore>()(
	persist(
		(set) => ({
	status: 'idle',
	summary: null,
	progress: null,
	currentThought: null,
	logs: [],
	errorMessage: null,
	implementations: {},
	requiresReviewByFeature: {},

	startGeneration: async (featureId, featureTitle, featureDisplayId) => {
		set({
			status: 'generating',
			summary: null,
			progress: 'Preparando generación...',
			currentThought: null,
			logs: [],
			errorMessage: null,
		});
		try {
			const summary = await generateImplementation(
				featureId,
				featureTitle,
				featureDisplayId,
				(message, log) => {
					set((state) => ({
						progress: message,
						currentThought: log?.type === 'thought' ? log.message : state.currentThought,
						logs: log ? [...state.logs, log] : state.logs,
					}));
				},
			);
			set((state) => ({
				status: 'completed',
				summary,
				progress: null,
				currentThought: null,
				implementations: {
					...state.implementations,
					[featureId]: true,
				},
				requiresReviewByFeature: {
					...state.requiresReviewByFeature,
					[featureId]: false,
				},
			}));
		} catch (error) {
			set({
				status: 'failed',
				progress: null,
				errorMessage:
					error instanceof Error ? error.message : 'Error desconocido durante la generación.',
			});
		}
	},

	loadImplementation: async (featureId, featureTitle, featureDisplayId) => {
		try {
			const record = await fetchImplementation(featureId);
			if (!record) {
				set((state) => {
					const nextRequires = { ...state.requiresReviewByFeature };
					delete nextRequires[featureId];
					return {
						status: 'idle',
						summary: null,
						requiresReviewByFeature: nextRequires,
					};
				});
				return;
			}
			if (record.status === 'failed') {
				set((state) => ({
					status: 'idle',
					summary: null,
					implementations: { ...state.implementations, [featureId]: false },
				}));
				return;
			}
			if (record.status !== 'implemented' && record.status !== 'requires_review') {
				return;
			}
			const summary = buildSummary(
				featureId,
				featureTitle,
				featureDisplayId,
				{
					generated_files: record.generatedFiles,
					features_count: record.featuresCount,
					screens_count: record.screensCount,
					requirements_count: record.requirementsCount,
					validations_passed: record.validationsPassed,
					validations_total: record.validationsTotal,
					traceability_edges: record.traceabilityEdgesCount,
					technologies: record.technologies,
				},
				record.updatedAt,
			);
			const isRequiresReview = record.status === 'requires_review';
			set((state) => ({
				status: isRequiresReview ? 'requires_review' : 'completed',
				summary,
				progress: null,
				currentThought: null,
				implementations: {
					...state.implementations,
					[featureId]: true,
				},
				requiresReviewByFeature: {
					...state.requiresReviewByFeature,
					[featureId]: isRequiresReview,
				},
			}));
		} catch {
			// Sin registro o error de red: se deja sin marcar para permitir regenerar
		}
	},

	reset: () =>
		set({
			status: 'idle',
			summary: null,
			progress: null,
			currentThought: null,
			logs: [],
			errorMessage: null,
			requiresReviewByFeature: {},
		}),
		}),
		{
			name: 'kosmo-implementation-store',
			partialize: (state) => ({
				summary: state.summary,
				implementations: state.implementations,
				requiresReviewByFeature: state.requiresReviewByFeature,
			}),
		},
	),
);

export const clearImplementationStore = () => {
	useImplementationStore.persist?.clearStorage?.();
	useImplementationStore.setState({
		status: 'idle',
		summary: null,
		progress: null,
		currentThought: null,
		logs: [],
		errorMessage: null,
		implementations: {},
		requiresReviewByFeature: {},
	});
};

