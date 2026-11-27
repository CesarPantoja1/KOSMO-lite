import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const fetchMock = vi.fn();

function mockFetchOk(body: unknown) {
	fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => body });
}

function mockFetchError(status: number, body: unknown) {
	fetchMock.mockResolvedValue({
		ok: false,
		status,
		headers: new Headers(),
		json: async () => body,
	});
}

afterEach(() => {
	fetchMock.mockReset();
	vi.unstubAllGlobals();
	vi.resetModules();
	vi.doUnmock('@/shared/api/config');
});

describe('consistency/api — modo real (USE_MOCKS=false)', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', fetchMock);
	});

	it('getConsistencyStatus consulta el endpoint del proyecto', async () => {
		// Arrange
		const { getConsistencyStatus } = await import('./api');
		mockFetchOk({ phases: {} });

		// Act
		await getConsistencyStatus('prj_01');

		// Assert
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/projects/prj_01/consistency/status'),
			expect.objectContaining({ method: 'GET' }),
		);
	});

	it('getConsistencyReview agrega target_phase como query param', async () => {
		// Arrange
		const { getConsistencyReview } = await import('./api');
		mockFetchOk({ cards: [] });

		// Act
		await getConsistencyReview('prj_01', 'requirements');

		// Assert
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('target_phase=requirements'),
			expect.objectContaining({ method: 'GET' }),
		);
	});

	it('applyConsistencyEvaluation hace POST al endpoint de apply', async () => {
		// Arrange
		const { applyConsistencyEvaluation } = await import('./api');
		mockFetchOk({ evaluation_id: 'ev1', applied: true });

		// Act
		const result = await applyConsistencyEvaluation('prj_01', 'ev1');

		// Assert
		expect(result.applied).toBe(true);
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/consistency/evaluations/ev1/apply'),
			expect.objectContaining({ method: 'POST' }),
		);
	});

	it('discardConsistencyEvaluation hace POST al endpoint de discard', async () => {
		// Arrange
		const { discardConsistencyEvaluation } = await import('./api');
		mockFetchOk({ evaluation_id: 'ev1', discarded: true });

		// Act
		await discardConsistencyEvaluation('prj_01', 'ev1');

		// Assert
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/consistency/evaluations/ev1/discard'),
			expect.objectContaining({ method: 'POST' }),
		);
	});

	it('bulkResolveConsistency envía la acción y la fase objetivo', async () => {
		// Arrange
		const { bulkResolveConsistency } = await import('./api');
		mockFetchOk({ resolved: 3, skipped: 1 });

		// Act
		await bulkResolveConsistency('prj_01', 'apply', 'requirements');

		// Assert
		const [url, options] = fetchMock.mock.calls[0];
		expect(url).toContain('/consistency/review/bulk');
		expect(JSON.parse((options as RequestInit).body as string)).toEqual({
			action: 'apply',
			target_phase: 'requirements',
		});
	});

	it('getConsistencyActivity agrega el límite como query param', async () => {
		// Arrange
		const { getConsistencyActivity } = await import('./api');
		mockFetchOk({ items: [] });

		// Act
		await getConsistencyActivity('prj_01', 20);

		// Assert
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/consistency/activity?limit=20'),
			expect.objectContaining({ method: 'GET' }),
		);
	});

	it('propaga el error de la API cuando la petición falla', async () => {
		// Arrange
		const { getConsistencyStatus } = await import('./api');
		mockFetchError(500, { detail: 'Error interno' });

		// Act & Assert
		await expect(getConsistencyStatus('prj_01')).rejects.toThrow('Error interno');
	});
});

describe('consistency/api — modo mock (USE_MOCKS=true)', () => {
	beforeEach(() => {
		vi.resetModules();
		vi.doMock('@/shared/api/config', () => ({ USE_MOCKS: true }));
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('getConsistencyStatus resuelve un estado vacío en modo mock', async () => {
		// Arrange
		const { getConsistencyStatus } = await import('./api');

		// Act
		const promise = getConsistencyStatus('prj_01');
		await vi.advanceTimersByTimeAsync(200);
		const result = await promise;

		// Assert
		expect(result.phases.features).toEqual({ pending: 0, evaluating: 0, failed: 0 });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('getConsistencyReview resuelve tarjetas vacías en modo mock', async () => {
		// Arrange
		const { getConsistencyReview } = await import('./api');

		// Act
		const promise = getConsistencyReview('prj_01', 'requirements');
		await vi.advanceTimersByTimeAsync(300);
		const result = await promise;

		// Assert
		expect(result.cards).toEqual([]);
	});

	it('applyConsistencyEvaluation resuelve applied=true en modo mock', async () => {
		// Arrange
		const { applyConsistencyEvaluation } = await import('./api');

		// Act
		const promise = applyConsistencyEvaluation('prj_01', 'ev1');
		await vi.advanceTimersByTimeAsync(300);
		const result = await promise;

		// Assert
		expect(result).toEqual({ evaluation_id: 'ev1', applied: true });
	});

	it('bulkResolveConsistency resuelve contadores en cero en modo mock', async () => {
		// Arrange
		const { bulkResolveConsistency } = await import('./api');

		// Act
		const promise = bulkResolveConsistency('prj_01', 'discard', 'features');
		await vi.advanceTimersByTimeAsync(300);
		const result = await promise;

		// Assert
		expect(result).toEqual({ resolved: 0, skipped: 0 });
	});
});
