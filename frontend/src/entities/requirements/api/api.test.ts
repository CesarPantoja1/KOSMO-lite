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

describe('requirements/api — modo real (USE_MOCKS=false)', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', fetchMock);
	});

	it('getRequirements consulta el endpoint con project_id como query', async () => {
		// Arrange
		const { getRequirements } = await import('./api');
		mockFetchOk({
			feature_id: 'f1',
			feature_number: 1,
			document_markdown: 'md',
			total: 1,
		});

		// Act
		const result = await getRequirements('prj_01', 'f1');

		// Assert
		expect(result.document_markdown).toBe('md');
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/features/f1/requirements?project_id=prj_01'),
			expect.objectContaining({ method: 'GET' }),
		);
	});

	it('saveRequirements hace PUT con project_id y markdown', async () => {
		// Arrange
		const { saveRequirements } = await import('./api');
		mockFetchOk({ feature_id: 'f1', message: 'ok' });

		// Act
		await saveRequirements('prj_01', 'f1', 'contenido');

		// Assert
		const [url, options] = fetchMock.mock.calls[0];
		expect(url).toContain('/api/v1/features/f1/requirements');
		expect((options as RequestInit).method).toBe('PUT');
		expect(JSON.parse((options as RequestInit).body as string)).toEqual({
			project_id: 'prj_01',
			markdown: 'contenido',
		});
	});

	it('generateRequirements hace POST con project_id', async () => {
		// Arrange
		const { generateRequirements } = await import('./api');
		mockFetchOk({
			feature_id: 'f1',
			feature_number: 1,
			document_markdown: 'generado',
			total: 4,
		});

		// Act
		const result = await generateRequirements('prj_01', 'f1');

		// Assert
		expect(result.document_markdown).toBe('generado');
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/features/f1/requirements/generate'),
			expect.objectContaining({ method: 'POST' }),
		);
	});

	it('deleteRequirements hace DELETE con project_id como query', async () => {
		// Arrange
		const { deleteRequirements } = await import('./api');
		mockFetchOk(null);

		// Act
		await deleteRequirements('prj_01', 'f1');

		// Assert
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/features/f1/requirements?project_id=prj_01'),
			expect.objectContaining({ method: 'DELETE' }),
		);
	});

	it('getRequirementChatHistory agrega session_id y before como query params', async () => {
		// Arrange
		const { getRequirementChatHistory } = await import('./api');
		mockFetchOk({
			phase: 'requirements',
			context: 'f1',
			messages: [],
			has_more: false,
			next_cursor: null,
		});

		// Act
		await getRequirementChatHistory('f1', 'sess_1', 'cursor_1');

		// Assert
		const [url] = fetchMock.mock.calls[0];
		expect(url).toContain('session_id=sess_1');
		expect(url).toContain('before=cursor_1');
	});

	it('sendRequirementChatMessage hace POST con el contenido', async () => {
		// Arrange
		const { sendRequirementChatMessage } = await import('./api');
		mockFetchOk({
			message: { id: 'm1', role: 'assistant', content: 'ok' },
			modification: null,
			redirect: null,
			consistency: null,
		});

		// Act
		await sendRequirementChatMessage('f1', 'Hola');

		// Assert
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/features/f1/requirements/chat'),
			expect.objectContaining({ method: 'POST' }),
		);
	});

	it('propaga el error de la API cuando la petición falla', async () => {
		// Arrange
		const { getRequirements } = await import('./api');
		mockFetchError(500, { detail: 'Error interno' });

		// Act & Assert
		await expect(getRequirements('prj_01', 'f1')).rejects.toThrow('Error interno');
	});
});

describe('requirements/api — modo mock (USE_MOCKS=true)', () => {
	beforeEach(() => {
		vi.resetModules();
		vi.doMock('@/shared/api/config', () => ({ USE_MOCKS: true }));
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('getRequirements resuelve desde el store mock', async () => {
		// Arrange
		const { getRequirements } = await import('./api');

		// Act
		const promise = getRequirements('prj_01', '1');
		await vi.advanceTimersByTimeAsync(400);
		const result = await promise;

		// Assert
		expect(result.feature_id).toBe('1');
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('generateRequirements devuelve un documento EARS generado', async () => {
		// Arrange
		const { generateRequirements } = await import('./api');

		// Act
		const promise = generateRequirements('prj_01', '1');
		await vi.advanceTimersByTimeAsync(2000);
		const result = await promise;

		// Assert
		expect(result.document_markdown).toContain('EARS Requirements');
	});

	it('saveRequirements no lanza error en modo mock', async () => {
		// Arrange
		const { saveRequirements } = await import('./api');

		// Act
		const promise = saveRequirements('prj_01', '1', 'nuevo contenido');
		await vi.advanceTimersByTimeAsync(500);

		// Assert
		await expect(promise).resolves.toBeUndefined();
	});

	it('deleteRequirements no lanza error en modo mock', async () => {
		// Arrange
		const { deleteRequirements } = await import('./api');

		// Act
		const promise = deleteRequirements('prj_01', '1');
		await vi.advanceTimersByTimeAsync(400);

		// Assert
		await expect(promise).resolves.toBeUndefined();
	});

	it('getRequirementChatHistory resuelve historial vacío por defecto', async () => {
		// Arrange
		const { getRequirementChatHistory } = await import('./api');

		// Act
		const promise = getRequirementChatHistory('f1');
		await vi.advanceTimersByTimeAsync(300);
		const result = await promise;

		// Assert
		expect(result.messages).toEqual([]);
	});

	it('sendRequirementChatMessage devuelve una sugerencia de cambio simulada', async () => {
		// Arrange
		const { sendRequirementChatMessage } = await import('./api');

		// Act
		const promise = sendRequirementChatMessage('f1', 'Agrega validación');
		await vi.advanceTimersByTimeAsync(600);
		const result = await promise;

		// Assert
		expect(result.message.change_suggestions).toHaveLength(1);
	});

	it('sendRequirementChatMessage lanza error cuando el contenido simula formato inválido', async () => {
		// Arrange
		const { sendRequirementChatMessage } = await import('./api');

		// Act
		const promise = sendRequirementChatMessage('f1', 'contenido con ERROR_FORMATO');
		const assertion = expect(promise).rejects.toThrow('formato inválido');
		await vi.advanceTimersByTimeAsync(600);

		// Assert
		await assertion;
	});
});
