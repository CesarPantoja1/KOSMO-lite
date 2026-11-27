import { ApiError } from '@/shared/api/errors';
import { HttpResponse, apiUrl, http, server } from '@/test';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ProjectDeployStatusResponse } from '../model/types';
import { deleteDeployment, getDeployStatus, startDeployRailway } from './api';

const estado = (
	overrides: Partial<ProjectDeployStatusResponse> = {},
): ProjectDeployStatusResponse => ({
	service_id: 'srv_1',
	service_name: 'kosmo-app',
	deploy_url: 'https://kosmo-app.up.railway.app',
	status: 'ready',
	last_deploy_at: '2026-01-15T10:00:00.000Z',
	error_message: null,
	error_log_url: null,
	...overrides,
});

describe('deploy/api — modo real', () => {
	describe('getDeployStatus', () => {
		it('consulta el estado del despliegue del proyecto', async () => {
			server.use(
				http.get(apiUrl('/api/v1/projects/:id/deploy'), ({ params }) =>
					HttpResponse.json(estado({ service_name: `svc-${params.id}` })),
				),
			);

			const res = await getDeployStatus('prj_7');

			expect(res).toMatchObject({ status: 'ready', service_name: 'svc-prj_7' });
		});

		it('propaga el error del servidor como ApiError', async () => {
			server.use(
				http.get(apiUrl('/api/v1/projects/:id/deploy'), () =>
					HttpResponse.json(
						{ title: 'Error', detail: 'Railway no responde' },
						{ status: 502 },
					),
				),
			);

			await expect(getDeployStatus('prj_7')).rejects.toMatchObject({
				status: 502,
				detail: 'Railway no responde',
			});
		});
	});

	describe('startDeployRailway', () => {
		it('envía la configuración del despliegue en el cuerpo', async () => {
			let cuerpo: unknown;
			server.use(
				http.post(apiUrl('/api/v1/projects/:id/deploy/railway'), async ({ request }) => {
					cuerpo = await request.json();
					return HttpResponse.json(estado({ status: 'building', deploy_url: null }));
				}),
			);

			const res = await startDeployRailway('prj_7', {
				service_name: 'mi-app',
				environment_variables: { NODE_ENV: 'production' },
			});

			expect(res.status).toBe('building');
			expect(cuerpo).toEqual({
				service_name: 'mi-app',
				environment_variables: { NODE_ENV: 'production' },
			});
		});

		it('no envía cuerpo cuando no hay configuración', async () => {
			let texto: string | null = null;
			server.use(
				http.post(apiUrl('/api/v1/projects/:id/deploy/railway'), async ({ request }) => {
					texto = await request.text();
					return HttpResponse.json(estado({ status: 'pending' }));
				}),
			);

			await startDeployRailway('prj_7');

			expect(texto).toBe('');
		});
	});

	describe('deleteDeployment', () => {
		it('elimina el despliegue con DELETE y resuelve sin valor (204)', async () => {
			const metodos: string[] = [];
			server.use(
				http.delete(apiUrl('/api/v1/projects/:id/deploy'), ({ request }) => {
					metodos.push(request.method);
					return new HttpResponse(null, { status: 204 });
				}),
			);

			await expect(deleteDeployment('prj_7')).resolves.toBeUndefined();
			expect(metodos).toEqual(['DELETE']);
		});

		it('rechaza si el despliegue no existe (404)', async () => {
			server.use(
				http.delete(apiUrl('/api/v1/projects/:id/deploy'), () =>
					HttpResponse.json({ detail: 'No encontrado' }, { status: 404 }),
				),
			);

			await expect(deleteDeployment('prj_x')).rejects.toBeInstanceOf(ApiError);
		});
	});
});

describe('deploy/api — modo mock (USE_MOCKS=true)', () => {
	async function importarEnModoMock() {
		vi.resetModules();
		vi.doMock('@/shared/api/config', async (importOriginal) => ({
			...(await importOriginal<typeof import('@/shared/api/config')>()),
			USE_MOCKS: true,
		}));
		return import('./api');
	}

	afterEach(() => {
		vi.useRealTimers();
		vi.doUnmock('@/shared/api/config');
		vi.resetModules();
	});

	it('inicia en estado idle sin hacer peticiones de red', async () => {
		vi.useFakeTimers();
		const api = await importarEnModoMock();

		const promesa = api.getDeployStatus('prj_1');
		await vi.advanceTimersByTimeAsync(300);

		await expect(promesa).resolves.toMatchObject({ status: 'idle', deploy_url: null });
	});

	it('simula el ciclo building → ready del despliegue', async () => {
		vi.useFakeTimers();
		const api = await importarEnModoMock();

		const inicio = api.startDeployRailway('prj_1');
		await vi.advanceTimersByTimeAsync(800);
		await expect(inicio).resolves.toMatchObject({ status: 'building', deploy_url: null });

		await vi.advanceTimersByTimeAsync(6_000);
		const final = api.getDeployStatus('prj_1');
		await vi.advanceTimersByTimeAsync(300);

		await expect(final).resolves.toMatchObject({
			status: 'ready',
			deploy_url: 'https://kosmo-app.up.railway.app',
		});
	});
});
