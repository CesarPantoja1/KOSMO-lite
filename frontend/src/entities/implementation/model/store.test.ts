import { beforeEach, describe, expect, it, vi } from 'vitest';
import { buildSummary, fetchImplementation, generateImplementation } from '../api/api';
import { clearImplementationStore, useImplementationStore } from './store';
import type { ImplementationSummary } from './types';

vi.mock('../api/api', () => ({
	fetchImplementation: vi.fn(),
	generateImplementation: vi.fn(),
	buildSummary: vi.fn(),
}));

const mockedGenerate = vi.mocked(generateImplementation);
const mockedFetchImplementation = vi.mocked(fetchImplementation);
const mockedBuildSummary = vi.mocked(buildSummary);

const aSummary: ImplementationSummary = {
	featureId: 'feat_01',
	featureTitle: 'Registrar gastos',
	featureDisplayId: 'F-01',
	status: 'completed',
	metrics: [],
	technologies: [],
	nextSteps: [],
	generatedAt: '2026-08-19T10:00:00Z',
};

describe('useImplementationStore', () => {
	beforeEach(() => {
		clearImplementationStore();
		mockedGenerate.mockReset();
		mockedFetchImplementation.mockReset();
		mockedBuildSummary.mockReset();
	});

	it('marca completed y registra la implementación al terminar', async () => {
		// Arrange
		mockedGenerate.mockResolvedValue(aSummary);

		// Act
		await useImplementationStore
			.getState()
			.startGeneration('feat_01', 'Registrar gastos', 'F-01');

		// Assert
		expect(useImplementationStore.getState().status).toBe('completed');
		expect(useImplementationStore.getState().summary).toEqual(aSummary);
		expect(useImplementationStore.getState().implementations['feat_01']).toBe(true);
	});

	it('actualiza el progreso con los mensajes emitidos por el flujo', async () => {
		// Arrange
		mockedGenerate.mockImplementation(
			async (_id, _title, _displayId, onProgress) => {
				onProgress?.('Generando código...');
				return aSummary;
			},
		);

		// Act
		await useImplementationStore
			.getState()
			.startGeneration('feat_01', 'Registrar gastos', 'F-01');

		// Assert
		expect(useImplementationStore.getState().progress).toBeNull();
	});

	it('marca failed y guarda el mensaje si la generación lanza error', async () => {
		// Arrange
		mockedGenerate.mockRejectedValue(new Error('fallo de validación'));

		// Act
		await useImplementationStore
			.getState()
			.startGeneration('feat_01', 'Registrar gastos', 'F-01');

		// Assert
		expect(useImplementationStore.getState().status).toBe('failed');
		expect(useImplementationStore.getState().errorMessage).toBe('fallo de validación');
		expect(useImplementationStore.getState().implementations['feat_01']).toBeUndefined();
	});

	it('hidrata la implementación desde el servidor al recargar', async () => {
		// Arrange
		mockedFetchImplementation.mockResolvedValue({
			implementationId: 'impl_feat_01',
			featureId: 'feat_01',
			projectId: 'prj_01',
			status: 'implemented',
			generatedFiles: ['src/app/page.tsx'],
			updatedAt: '2026-08-19T10:00:00Z',
		});
		mockedBuildSummary.mockReturnValue({
			...aSummary,
			generatedFiles: ['src/app/page.tsx'],
		});

		// Act
		await useImplementationStore.getState().loadImplementation('feat_01', 'Registrar gastos', 'F-01');

		// Assert
		const state = useImplementationStore.getState();
		expect(state.implementations['feat_01']).toBe(true);
		expect(state.summary?.featureId).toBe('feat_01');
		expect(state.summary?.generatedFiles).toEqual(['src/app/page.tsx']);
		expect(state.summary?.status).toBe('completed');
	});

	it('no marca implementado si el servidor no tiene registro (404)', async () => {
		// Arrange
		mockedFetchImplementation.mockResolvedValue(null);

		// Act
		await useImplementationStore.getState().loadImplementation('feat_new', 'Nueva', 'F-09');

		// Assert
		const state = useImplementationStore.getState();
		expect(state.implementations['feat_new']).toBeUndefined();
		expect(state.summary).toBeNull();
	});

	it('acumula los logs y actualiza currentThought durante la generación', async () => {
		// Arrange
		mockedGenerate.mockImplementation(
			async (_id, _title, _displayId, onProgress) => {
				onProgress?.('Pensando lógica...', {
					id: 'log_1',
					type: 'thought',
					message: 'Pensando lógica...',
					timestamp: '2026-08-19T10:00:00Z',
				});
				onProgress?.('Generando archivo...', {
					id: 'log_2',
					type: 'file',
					message: 'Generando archivo...',
					timestamp: '2026-08-19T10:00:01Z',
				});
				return aSummary;
			},
		);

		// Act
		await useImplementationStore
			.getState()
			.startGeneration('feat_01', 'Registrar gastos', 'F-01');

		// Assert
		const state = useImplementationStore.getState();
		expect(state.status).toBe('completed');
		expect(state.currentThought).toBeNull();
	});

	it('hidrata status requires_review y activa requiresReviewByFeature', async () => {
		// Arrange
		mockedFetchImplementation.mockResolvedValue({
			implementationId: 'impl_feat_01',
			featureId: 'feat_01',
			projectId: 'prj_01',
			status: 'requires_review',
			generatedFiles: ['src/app/page.tsx'],
			updatedAt: '2026-08-19T10:00:00Z',
		});
		mockedBuildSummary.mockReturnValue({
			...aSummary,
			status: 'requires_review',
			generatedFiles: ['src/app/page.tsx'],
		});

		// Act
		await useImplementationStore.getState().loadImplementation('feat_01', 'Registrar gastos', 'F-01');

		// Assert
		const state = useImplementationStore.getState();
		expect(state.implementations['feat_01']).toBe(true);
		expect(state.requiresReviewByFeature['feat_01']).toBe(true);
		expect(state.status).toBe('requires_review');
	});

	it('restablece estado idle y permite reintento cuando el status es failed', async () => {
		// Arrange
		mockedFetchImplementation.mockResolvedValue({
			implementationId: 'impl_feat_failed',
			featureId: 'feat_failed',
			projectId: 'prj_01',
			status: 'failed',
			generatedFiles: [],
			updatedAt: '2026-08-19T10:00:00Z',
		});

		// Act
		await useImplementationStore.getState().loadImplementation('feat_failed', 'Fallida', 'F-08');

		// Assert
		const state = useImplementationStore.getState();
		expect(state.implementations['feat_failed']).toBe(false);
		expect(state.status).toBe('idle');
		expect(state.summary).toBeNull();
	});

	it('clearImplementationStore limpia el almacenamiento persistido y el estado', () => {
		// Arrange
		useImplementationStore.setState({
			status: 'completed',
			summary: aSummary,
			implementations: { feat_01: true },
			requiresReviewByFeature: { feat_01: true },
		});

		// Act
		clearImplementationStore();

		// Assert
		const state = useImplementationStore.getState();
		expect(state.status).toBe('idle');
		expect(state.summary).toBeNull();
		expect(state.implementations).toEqual({});
		expect(state.requiresReviewByFeature).toEqual({});
	});
});

