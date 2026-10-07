import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildSummary, fetchImplementation, fetchImplementationFile } from './api';

const fetchMock = vi.fn();

function mockFetchOk(body: unknown) {
	fetchMock.mockResolvedValue({ ok: true, json: async () => body });
}

function mockFetchError(status: number, body: unknown) {
	fetchMock.mockResolvedValue({ ok: false, status, headers: new Headers(), json: async () => body });
}

afterEach(() => {
	fetchMock.mockReset();
	vi.stubGlobal('fetch', undefined);
});

describe('buildSummary', () => {
	it('construye el resumen con métricas reales desde el evento done', () => {
		// Arrange
		const data: Record<string, unknown> = {
			status: 'implemented',
			generated_files: ['src/app/page.tsx', 'tests/app.test.tsx'],
			screens_count: 1,
			requirements_count: 2,
			traceability_edges: 4,
			validations_passed: 4,
			validations_total: 4,
		};

		// Act
		const summary = buildSummary(
			'feat_01',
			'Registrar gastos',
			'F-01',
			data,
			'2026-08-19T10:00:00Z',
		);

		// Assert
		expect(summary.featureId).toBe('feat_01');
		expect(summary.featureTitle).toBe('Registrar gastos');
		expect(summary.featureDisplayId).toBe('F-01');
		expect(summary.status).toBe('completed');
		expect(summary.metrics).toHaveLength(4);
		expect(summary.metrics[0]).toMatchObject({ value: '1', label: 'Funcionalidades implementadas' });
		expect(summary.metrics[1]).toMatchObject({ value: '2', label: 'Requisitos de negocio' });
		expect(summary.metrics[2]).toMatchObject({
			value: '4',
			label: 'Enlaces de trazabilidad',
		});
		expect(summary.metrics[3]).toMatchObject({ value: '100%', label: 'Calidad verificada' });
		expect(summary.generatedAt).toBe('2026-08-19T10:00:00Z');
		expect(summary.technologies).toContain('Next.js');
		expect(summary.generatedFiles).toEqual([
			'src/app/page.tsx',
			'tests/app.test.tsx',
		]);
	});

	it('usa valores por defecto coherentes cuando el evento no trae métricas', () => {
		// Arrange
		const data: Record<string, unknown> = { status: 'implemented' };

		// Act
		const summary = buildSummary('feat_02', 'Título', 'F-02', data, '2026-08-19T10:00:00Z');

		// Assert
		expect(summary.metrics).toHaveLength(4);
		expect(summary.metrics[0].label).toBe('Funcionalidades implementadas');
		expect(summary.metrics[1].label).toBe('Requisitos de negocio');
		expect(summary.metrics[2].label).toBe('Enlaces de trazabilidad');
		expect(summary.metrics[3].label).toBe('Calidad verificada');
	});
});

describe('fetchImplementationFile', () => {
	it('devuelve el contenido del archivo desde el endpoint', async () => {
		// Arrange
		vi.stubGlobal('fetch', fetchMock);
		mockFetchOk({ path: 'src/a.ts', content: 'export const a = 1;' });

		// Act
		const content = await fetchImplementationFile('impl_feat_01', 'src/a.ts');

		// Assert
		expect(content).toBe('export const a = 1;');
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/implementations/impl_feat_01/files/content?path=src%2Fa.ts'),
			expect.objectContaining({ cache: 'no-store' }),
		);
	});

	it('lanza error si la respuesta no es exitosa', async () => {
		// Arrange
		vi.stubGlobal('fetch', fetchMock);
		mockFetchError(404, { detail: 'No se encontró el archivo' });

		// Act & Assert
		await expect(fetchImplementationFile('impl_feat_01', 'src/a.ts')).rejects.toThrow(
			'No se encontró el archivo',
		);
	});
});

describe('fetchImplementation', () => {
	it('devuelve el registro persistido de la implementación', async () => {
		// Arrange
		vi.stubGlobal('fetch', fetchMock);
		mockFetchOk({
			implementation_id: 'impl_feat_01',
			feature_id: 'feat_01',
			project_id: 'prj_01',
			status: 'implemented',
			generated_files: ['src/app/page.tsx'],
			updated_at: '2026-08-19T10:00:00Z',
		});

		// Act
		const record = await fetchImplementation('feat_01');

		// Assert
		expect(record).toMatchObject({
			implementationId: 'impl_feat_01',
			featureId: 'feat_01',
			projectId: 'prj_01',
			status: 'implemented',
			generatedFiles: ['src/app/page.tsx'],
		});
		expect(fetchMock).toHaveBeenCalledWith(
			expect.stringContaining('/api/v1/implementations?feature_id=feat_01'),
			expect.anything(),
		);
	});

	it('devuelve null cuando la implementación no existe (404)', async () => {
		// Arrange
		vi.stubGlobal('fetch', fetchMock);
		mockFetchError(404, { detail: 'No se encontró una implementación' });

		// Act
		const record = await fetchImplementation('feat_none');

		// Assert
		expect(record).toBeNull();
	});
});


describe('generateImplementation', () => {
	function sseResponse(payload: string): Response {
		const encoder = new TextEncoder();
		const stream = new ReadableStream<Uint8Array>({
			start(controller) {
				controller.enqueue(encoder.encode(payload));
				controller.close();
			},
		});
		return new Response(stream, {
			headers: { 'Content-Type': 'text/event-stream' },
			status: 200,
		});
	}

	it('inicia la implementación y procesa eventos SSE de OpenCode hasta done', async () => {
		// Arrange
		const progressMessages: string[] = [];
		const onProgress = (msg: string) => progressMessages.push(msg);

		const events = [
			{ event_type: 'session_created', data: { feature_id: 'feat_01' } },
			{ event_type: 'plan_progress', data: { delta: 'Planificando...' } },
			{ event_type: 'plan_complete', data: { files: ['src/logic.ts'] } },
			{ event_type: 'build_progress', data: {} },
			{ event_type: 'file_edit', data: { path: 'src/features/gastos/logic.ts' } },
			{ event_type: 'build_complete', data: { files: ['src/features/gastos/logic.ts'] } },
			{
				event_type: 'done',
				data: {
					status: 'implemented',
					generated_files: ['src/features/gastos/logic.ts'],
					traceability_edges: 3,
				},
			},
		];
		const ssePayload = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');

		vi.stubGlobal(
			'fetch',
			vi.fn((url: string, init?: RequestInit) => {
				if (url.includes('/api/v1/implementations') && init?.method === 'POST') {
					return Promise.resolve(
						new Response(JSON.stringify({ implementation_id: 'impl_feat_01' }), {
							status: 202,
							headers: { 'Content-Type': 'application/json' },
						}),
					);
				}
				if (url.includes('/api/v1/implementations/impl_feat_01/events')) {
					return Promise.resolve(sseResponse(ssePayload));
				}
				return Promise.reject(new Error(`URL inesperada: ${url}`));
			}),
		);

		// Act
		const { generateImplementation } = await import('./api');
		const result = await generateImplementation('feat_01', 'Gastos', 'F-01', onProgress);

		// Assert
		expect(result.status).toBe('completed');
		expect(result.generatedFiles).toEqual(['src/features/gastos/logic.ts']);
		expect(progressMessages).toContain('Implementación iniciada');
		expect(progressMessages).toContain('Sesión iniciada');
		expect(progressMessages).toContain('Planificando...');
		expect(progressMessages).toContain('Plan aprobado, preparando generación...');
		expect(progressMessages).toContain('Se generó `src/features/gastos/logic.ts`');
		expect(progressMessages).toContain('Código generado, ejecutando validaciones...');
	});

	it('notifica reintentos de validación con el número de intento', async () => {
		// Arrange
		const progressMessages: string[] = [];
		const onProgress = (msg: string) => progressMessages.push(msg);

		const events = [
			{ event_type: 'retry', data: { attempt: 1, max_retries: 3 } },
			{
				event_type: 'done',
				data: { status: 'implemented', generated_files: [] },
			},
		];
		const ssePayload = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');

		vi.stubGlobal(
			'fetch',
			vi.fn((url: string, init?: RequestInit) => {
				if (url.includes('/api/v1/implementations') && init?.method === 'POST') {
					return Promise.resolve(
						new Response(JSON.stringify({ implementation_id: 'impl_feat_02' }), {
							status: 202,
							headers: { 'Content-Type': 'application/json' },
						}),
					);
				}
				return Promise.resolve(sseResponse(ssePayload));
			}),
		);

		// Act
		const { generateImplementation } = await import('./api');
		await generateImplementation('feat_02', 'Login', 'F-02', onProgress);

		// Assert
		expect(progressMessages).toContain('Corrigiendo errores de validación (intento 1/3)');
	});

	it('lanza el error específico cuando el backend emite evento error', async () => {
		// Arrange
		const events = [
			{
				event_type: 'error',
				data: { error: 'El servidor OpenCode no está disponible. Verifica que esté en ejecución.' },
			},
		];
		const ssePayload = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');

		vi.stubGlobal(
			'fetch',
			vi.fn((url: string, init?: RequestInit) => {
				if (url.includes('/api/v1/implementations') && init?.method === 'POST') {
					return Promise.resolve(
						new Response(JSON.stringify({ implementation_id: 'impl_feat_03' }), {
							status: 202,
							headers: { 'Content-Type': 'application/json' },
						}),
					);
				}
				return Promise.resolve(sseResponse(ssePayload));
			}),
		);

		// Act & Assert
		const { generateImplementation } = await import('./api');
		await expect(
			generateImplementation('feat_03', 'Error Feature', 'F-03'),
		).rejects.toThrow('El servidor OpenCode no está disponible. Verifica que esté en ejecución.');
	});

	it('transmite pensamientos de OpenCode y deltas en tiempo real hacia onProgress', async () => {
		// Arrange
		const logs: Array<{ message: string; type?: string }> = [];
		const onProgress = (msg: string, log?: { type: string; message: string }) => {
			logs.push({ message: msg, type: log?.type });
		};

		const events = [
			{ event_type: 'plan_progress', data: { thought: 'Pensando cómo estructurar la feature...' } },
			{ event_type: 'build_progress', data: { delta: 'Generando schema de datos...', stage: 'writing' } },
			{ event_type: 'build_progress', data: { delta: 'Validando tipados...', stage: 'validating' } },
			{
				event_type: 'done',
				data: { status: 'implemented', generated_files: ['src/db/schema.ts'] },
			},
		];
		const ssePayload = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');

		vi.stubGlobal(
			'fetch',
			vi.fn((url: string, init?: RequestInit) => {
				if (url.includes('/api/v1/implementations') && init?.method === 'POST') {
					return Promise.resolve(
						new Response(JSON.stringify({ implementation_id: 'impl_feat_thought' }), {
							status: 202,
							headers: { 'Content-Type': 'application/json' },
						}),
					);
				}
				return Promise.resolve(sseResponse(ssePayload));
			}),
		);

		// Act
		const { generateImplementation } = await import('./api');
		await generateImplementation('feat_th', 'Thought Feature', 'F-TH', onProgress);

		// Assert
		expect(logs.some((l) => l.type === 'thought' && l.message.includes('Pensando'))).toBe(true);
		expect(logs.some((l) => l.type === 'code' && l.message.includes('Generando schema'))).toBe(true);
		expect(logs.some((l) => l.type === 'validation' && l.message.includes('Validando tipados'))).toBe(true);
	});
});

describe('subscribeImplementationEvents', () => {
	function sseResponse(payload: string): Response {
		const encoder = new TextEncoder();
		const stream = new ReadableStream<Uint8Array>({
			start(controller) {
				controller.enqueue(encoder.encode(payload));
				controller.close();
			},
		});
		return new Response(stream, {
			headers: { 'Content-Type': 'text/event-stream' },
			status: 200,
		});
	}

	it('notifica deltas, done y el mensaje ciudadano de éxito', async () => {
		// Arrange
		const deltas: string[] = [];
		let doneDelta = '';
		const events = [
			{ event_type: 'plan_progress', data: { delta: 'Eliminando la funcionalidad del código...' } },
			{
				event_type: 'build_progress',
				data: { delta: 'Validando la aplicación después de la eliminación...' },
			},
			{
				event_type: 'done',
				data: { status: 'deleted', delta: 'La funcionalidad se eliminó y la aplicación sigue funcionando correctamente.' },
			},
		];
		const ssePayload = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');
		vi.stubGlobal(
			'fetch',
			vi.fn(() => Promise.resolve(sseResponse(ssePayload))),
		);

		// Act
		const { subscribeImplementationEvents } = await import('./api');
		await subscribeImplementationEvents('impl_feat_del', {
			onDelta: (delta) => deltas.push(delta),
			onDone: (delta) => {
				doneDelta = delta;
			},
		});

		// Assert
		expect(deltas).toHaveLength(2);
		expect(doneDelta).toContain('sigue funcionando correctamente');
	});

	it('notifica el error ciudadano cuando la eliminación falla', async () => {
		// Arrange
		let errorMsg = '';
		const events = [
			{
				event_type: 'error',
				data: { error: 'No se pudo eliminar la funcionalidad. La aplicación volvió a su estado anterior.' },
			},
		];
		const ssePayload = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('');
		vi.stubGlobal(
			'fetch',
			vi.fn(() => Promise.resolve(sseResponse(ssePayload))),
		);

		// Act
		const { subscribeImplementationEvents } = await import('./api');
		await subscribeImplementationEvents('impl_feat_del_fail', {
			onError: (error) => {
				errorMsg = error;
			},
		});

		// Assert
		expect(errorMsg).toContain('No se pudo eliminar la funcionalidad');
		expect(errorMsg).toContain('volvió a su estado anterior');
	});
});

