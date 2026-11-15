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

describe('characteristic/api — modo real (USE_MOCKS=false)', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', fetchMock);
	});

	it('getCharacteristics consulta el endpoint del proyecto', async () => {
		// Arrange
		const { getCharacteristics } = await import('./api');
		mockFetchOk([{ id: 'f1', title: 'Login' }]);

		// Act
		const result = await getCharacteristics('prj_01');

		// Assert
		expect(result).toEqual([{ id: 'f1', title: 'Login' }]);
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/projects/prj_01/features'),
			expect.objectContaining({ method: 'GET' }),
		);
	});

	it('generateCharacteristics hace POST al endpoint del proyecto', async () => {
		// Arrange
		const { generateCharacteristics } = await import('./api');
		mockFetchOk([{ id: 'f1', title: 'Login' }]);

		// Act
		await generateCharacteristics('prj_01');

		// Assert
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/projects/prj_01/features'),
			expect.objectContaining({ method: 'POST' }),
		);
	});

	it('getSuggestCharacteristics consulta el endpoint de sugerencias', async () => {
		// Arrange
		const { getSuggestCharacteristics } = await import('./api');
		mockFetchOk([{ number: 1, title: 'Inventario', description: 'desc', origin: '' }]);

		// Act
		const result = await getSuggestCharacteristics('prj_01');

		// Assert
		expect(result).toHaveLength(1);
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/projects/prj_01/features/suggest'),
			expect.objectContaining({ method: 'POST' }),
		);
	});

	it('addCharacteristic envía título, descripción y origen', async () => {
		// Arrange
		const { addCharacteristic } = await import('./api');
		mockFetchOk({ is_saved: true, feature: { id: 'f1' }, origin: '', is_consistent: true });

		// Act
		const result = await addCharacteristic('prj_01', {
			title: 'Nueva',
			description: 'Descripción',
			origin: 'manual',
		});

		// Assert
		expect(result.is_saved).toBe(true);
		const [, options] = fetchMock.mock.calls[0];
		expect(JSON.parse((options as RequestInit).body as string)).toEqual({
			title: 'Nueva',
			description: 'Descripción',
			origin: 'manual',
		});
	});

	it('getChatHistory agrega session_id y before como query params', async () => {
		// Arrange
		const { getChatHistory } = await import('./api');
		mockFetchOk({ phase: 'features', context: 'feat_01', messages: [], has_more: false, next_cursor: null });

		// Act
		await getChatHistory('feat_01', 'sess_1', 'cursor_1');

		// Assert
		const [url] = fetchMock.mock.calls[0];
		expect(url).toContain('session_id=sess_1');
		expect(url).toContain('before=cursor_1');
	});

	it('deleteFeature hace DELETE al endpoint de la característica', async () => {
		// Arrange
		const { deleteFeature } = await import('./api');
		mockFetchOk(null);
		fetchMock.mockResolvedValue({ ok: true, status: 204, json: async () => null });

		// Act
		await deleteFeature('prj_01', 'feat_01');

		// Assert
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/projects/prj_01/features/feat_01'),
			expect.objectContaining({ method: 'DELETE' }),
		);
	});

	it('propaga el error de la API cuando la petición falla', async () => {
		// Arrange
		const { getCharacteristics } = await import('./api');
		mockFetchError(500, { detail: 'Error interno' });

		// Act & Assert
		await expect(getCharacteristics('prj_01')).rejects.toThrow('Error interno');
	});
});

describe('characteristic/api — modo mock (USE_MOCKS=true)', () => {
	beforeEach(() => {
		vi.resetModules();
		vi.doMock('@/shared/api/config', () => ({ USE_MOCKS: true }));
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('getCharacteristics resuelve datos mock sin llamar a fetch', async () => {
		// Arrange
		const { getCharacteristics } = await import('./api');

		// Act
		const promise = getCharacteristics('prj_01');
		await vi.advanceTimersByTimeAsync(3000);
		const result = await promise;

		// Assert
		expect(Array.isArray(result)).toBe(true);
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('generateCharacteristics agrega una característica generada al store mock', async () => {
		// Arrange
		const { generateCharacteristics } = await import('./api');

		// Act
		const promise = generateCharacteristics('prj_01');
		await vi.advanceTimersByTimeAsync(2000);
		const result = await promise;

		// Assert
		expect(result.some((c) => c.title.includes('Perfiles'))).toBe(true);
	});

	it('addCharacteristic agrega al store mock y devuelve is_saved=true', async () => {
		// Arrange
		const { addCharacteristic } = await import('./api');

		// Act
		const promise = addCharacteristic('prj_01', { title: 'X', description: 'Y' });
		await vi.advanceTimersByTimeAsync(600);
		const result = await promise;

		// Assert
		expect(result.is_saved).toBe(true);
		expect(result.feature.title).toBe('X');
	});

	it('deleteFeature no falla en modo mock (no-op)', async () => {
		// Arrange
		const { deleteFeature } = await import('./api');

		// Act & Assert
		await expect(deleteFeature('prj_01', 'feat_01')).resolves.toBeUndefined();
	});
});
