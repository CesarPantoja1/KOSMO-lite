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

describe('discovery/api — modo real (USE_MOCKS=false)', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', fetchMock);
	});

	it('getDiscovery consulta el endpoint del proyecto', async () => {
		// Arrange
		const { getDiscovery } = await import('./api');
		mockFetchOk({ id: 'd1', project_id: 'prj_01', content: 'texto' });

		// Act
		const result = await getDiscovery('prj_01');

		// Assert
		expect(result.content).toBe('texto');
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/projects/prj_01/discovery'),
			expect.objectContaining({ method: 'GET' }),
		);
	});

	it('saveDiscovery hace PUT con el contenido', async () => {
		// Arrange
		const { saveDiscovery } = await import('./api');
		mockFetchOk({ id: 'd1', project_id: 'prj_01', content: 'nuevo' });

		// Act
		await saveDiscovery('prj_01', 'nuevo');

		// Assert
		const [url, options] = fetchMock.mock.calls[0];
		expect(url).toContain('/api/v1/projects/prj_01/discovery');
		expect((options as RequestInit).method).toBe('PUT');
		expect(JSON.parse((options as RequestInit).body as string)).toEqual({
			content: 'nuevo',
		});
	});

	it('generateDiscovery hace POST al endpoint', async () => {
		// Arrange
		const { generateDiscovery } = await import('./api');
		mockFetchOk({ id: 'd1', project_id: 'prj_01', content: 'generado' });

		// Act
		await generateDiscovery('prj_01');

		// Assert
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/projects/prj_01/discovery'),
			expect.objectContaining({ method: 'POST' }),
		);
	});

	it('sendChatMessage hace POST con el contenido del mensaje', async () => {
		// Arrange
		const { sendChatMessage } = await import('./api');
		mockFetchOk({
			message: { id: 'm1', role: 'assistant', content: 'ok' },
			modification: null,
			redirect: null,
			consistency: null,
		});

		// Act
		await sendChatMessage('prj_01', 'Hola');

		// Assert
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/projects/prj_01/discovery/chat'),
			expect.objectContaining({ method: 'POST' }),
		);
	});

	it('getChatHistory agrega session_id y before como query params', async () => {
		// Arrange
		const { getChatHistory } = await import('./api');
		mockFetchOk({
			phase: 'discovery',
			context: 'prj_01',
			messages: [],
			has_more: false,
			next_cursor: null,
		});

		// Act
		await getChatHistory('prj_01', 'sess_1', 'cursor_1');

		// Assert
		const [url] = fetchMock.mock.calls[0];
		expect(url).toContain('session_id=sess_1');
		expect(url).toContain('before=cursor_1');
	});

	it('propaga el error de la API cuando la petición falla', async () => {
		// Arrange
		const { getDiscovery } = await import('./api');
		mockFetchError(500, { detail: 'Error interno' });

		// Act & Assert
		await expect(getDiscovery('prj_01')).rejects.toThrow('Error interno');
	});
});

describe('discovery/api — modo mock (USE_MOCKS=true)', () => {
	beforeEach(() => {
		vi.resetModules();
		vi.doMock('@/shared/api/config', () => ({ USE_MOCKS: true }));
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('getDiscovery resuelve datos mock sin llamar a fetch', async () => {
		// Arrange
		const { getDiscovery } = await import('./api');

		// Act
		const promise = getDiscovery('prj_01');
		await vi.advanceTimersByTimeAsync(5000);
		const result = await promise;

		// Assert
		expect(result.project_id).toBe('prj_01');
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it('generateDiscovery actualiza el contenido mock', async () => {
		// Arrange
		const { generateDiscovery } = await import('./api');

		// Act
		const promise = generateDiscovery('prj_01');
		await vi.advanceTimersByTimeAsync(2000);
		const result = await promise;

		// Assert
		expect(result.content).toContain('Descubrimiento generado en modo mock');
	});

	it('saveDiscovery devuelve el contenido enviado', async () => {
		// Arrange
		const { saveDiscovery } = await import('./api');

		// Act
		const promise = saveDiscovery('prj_01', 'mi contenido');
		await vi.advanceTimersByTimeAsync(500);
		const result = await promise;

		// Assert
		expect(result.content).toBe('mi contenido');
	});

	it('sendChatMessage resuelve una respuesta mock', async () => {
		// Arrange
		const { sendChatMessage } = await import('./api');

		// Act
		const promise = sendChatMessage('prj_01', 'Hola');
		await vi.advanceTimersByTimeAsync(500);
		const result = await promise;

		// Assert
		expect(result.message).toBeDefined();
	});

	it('getChatHistory resuelve historial vacío en modo mock', async () => {
		// Arrange
		const { getChatHistory } = await import('./api');

		// Act
		const promise = getChatHistory('prj_01');
		await vi.advanceTimersByTimeAsync(300);
		const result = await promise;

		// Assert
		expect(result.messages).toEqual([]);
	});
});
