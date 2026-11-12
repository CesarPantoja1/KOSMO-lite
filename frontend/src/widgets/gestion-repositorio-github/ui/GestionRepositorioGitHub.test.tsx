/**
 * Integración: widget GestionRepositorioGitHub + hook useProjectGithubRepo (features/github-sync)
 * + entidades project/integration, contra la API simulada con MSW.
 */
import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ProjectGitHubStatus } from '@/entities/project';
import { useProjectGithubRepo } from '@/features/github-sync';
import {
	HttpResponse,
	apiUrl,
	crearIntegracion,
	delay,
	http,
	renderWithProviders,
	server,
} from '@/test';
import { GestionRepositorioGitHub } from './GestionRepositorioGitHub';

const URL_GITHUB = '/api/v1/projects/:projectId/github';
const URL_PUSH = '/api/v1/projects/:projectId/github/push';

/** Composición tal como la usa la página de implementación. */
function RepositorioDelProyecto() {
	const repo = useProjectGithubRepo('prj_1');
	return (
		<GestionRepositorioGitHub
			viewState={repo.viewState}
			status={repo.status}
			loading={repo.loading}
			error={repo.error}
			onCreate={repo.createRepo}
			onSync={repo.sync}
		/>
	);
}

const estado = (overrides: Partial<ProjectGitHubStatus> = {}): ProjectGitHubStatus => ({
	has_repository: true,
	repo_name: 'kosmo-tienda',
	repo_url: 'https://github.com/ada/kosmo-tienda',
	is_public: false,
	last_push_at: '2026-01-15T10:30:00.000Z',
	last_commit_hash: 'a1b2c3d4e5f6',
	sync_status: 'synced',
	suggested_repo_name: 'kosmo-tienda',
	error_message: null,
	...overrides,
});

function backend({ conectado = true, repo = estado() }: { conectado?: boolean; repo?: ProjectGitHubStatus } = {}) {
	server.use(
		http.get(apiUrl('/api/v1/integrations/:provider/status'), () =>
			HttpResponse.json(crearIntegracion({ is_connected: conectado })),
		),
		http.get(apiUrl(URL_GITHUB), () => HttpResponse.json(repo)),
	);
}

const renderizar = () => renderWithProviders(<RepositorioDelProyecto />);

describe('GestionRepositorioGitHub (integración con useProjectGithubRepo)', () => {
	it('verifica el estado del repositorio al cargar', () => {
		backend();
		renderizar();

		expect(screen.getByText('Verificando estado del repositorio...')).toBeInTheDocument();
	});

	it('sin cuenta de GitHub vinculada invita a conectarla', async () => {
		backend({ conectado: false });
		renderizar();

		expect(await screen.findByText('Vincula tu cuenta de GitHub')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Conectar cuenta de GitHub' })).toHaveAttribute('href', '/perfil');
	});

	describe('repositorio sincronizado', () => {
		it('muestra el enlace, la última sincronización y el commit abreviado', async () => {
			backend();
			renderizar();

			const enlace = await screen.findByRole('link', { name: /kosmo-tienda/ });
			expect(enlace).toHaveAttribute('href', 'https://github.com/ada/kosmo-tienda');
			expect(enlace).toHaveAttribute('target', '_blank');
			expect(enlace).toHaveAttribute('rel', 'noopener noreferrer');
			expect(screen.getByText('a1b2c3d')).toBeInTheDocument();
			expect(screen.getByText('Privado')).toBeInTheDocument();
			expect(screen.getByText('Al día')).toBeInTheDocument();
		});

		it('indica si el repositorio es público', async () => {
			backend({ repo: estado({ is_public: true }) });
			renderizar();

			expect(await screen.findByText('Público')).toBeInTheDocument();
		});

		it('muestra guiones si aún no hay push ni commit', async () => {
			backend({ repo: estado({ last_push_at: null, last_commit_hash: null }) });
			renderizar();

			await screen.findByText('Al día');
			expect(screen.getAllByText('—')).toHaveLength(2);
		});

		it('sincronizar ahora sube el código y confirma', async () => {
			const pushes: unknown[] = [];
			backend();
			server.use(
				http.post(apiUrl(URL_PUSH), async ({ request }) => {
					pushes.push(await request.json());
					await delay(30);
					return HttpResponse.json(estado({ last_commit_hash: 'ffff0000aaaa' }));
				}),
			);
			const { user } = renderizar();

			await user.click(await screen.findByRole('button', { name: 'Sincronizar ahora' }));

			expect(await screen.findByText('Código sincronizado con GitHub.')).toBeInTheDocument();
			expect(pushes).toEqual([{}]);
			expect(screen.getByText('ffff000')).toBeInTheDocument();
		});
	});

	describe('crear el repositorio', () => {
		it('crea un repositorio privado con el nombre sugerido', async () => {
			const pushes: unknown[] = [];
			backend({ repo: estado({ has_repository: false, sync_status: 'not_created', suggested_repo_name: 'kosmo-ferreteria' }) });
			server.use(
				http.post(apiUrl(URL_PUSH), async ({ request }) => {
					pushes.push(await request.json());
					return HttpResponse.json(estado({ repo_name: 'kosmo-ferreteria' }));
				}),
			);
			const { user } = renderizar();

			expect(await screen.findByText('Crea el repositorio de tu proyecto')).toBeInTheDocument();
			expect(screen.getByLabelText('Nombre del repositorio')).toHaveValue('kosmo-ferreteria');
			await user.click(screen.getByRole('button', { name: /Crear repositorio/ }));

			expect(await screen.findByText('Repositorio creado y sincronizado con GitHub.')).toBeInTheDocument();
			expect(pushes).toEqual([{ repo_name: 'kosmo-ferreteria', is_public: false }]);
			expect(screen.getByRole('link', { name: /kosmo-ferreteria/ })).toBeInTheDocument();
		});

		it('si aún no hay código generado lo indica en lugar de fallar', async () => {
			backend({ repo: estado({ has_repository: false, sync_status: 'not_created' }) });
			server.use(
				http.post(apiUrl(URL_PUSH), () =>
					HttpResponse.json({ detail: 'El proyecto no tiene funcionalidades implementadas' }, { status: 409 }),
				),
			);
			const { user } = renderizar();

			await user.click(await screen.findByRole('button', { name: /Crear repositorio/ }));

			expect(await screen.findByText('Aún no hay código generado')).toBeInTheDocument();
		});
	});

	describe('sincronización fallida', () => {
		it('muestra el motivo y permite reintentar', async () => {
			backend({ repo: estado({ sync_status: 'failed', error_message: 'Token de GitHub revocado' }) });
			server.use(http.post(apiUrl(URL_PUSH), () => HttpResponse.json(estado())));
			const { user } = renderizar();

			expect(await screen.findByText('La sincronización falló')).toBeInTheDocument();
			expect(screen.getByText('Token de GitHub revocado')).toBeInTheDocument();
			await user.click(screen.getByRole('button', { name: 'Reintentar' }));

			expect(await screen.findByText('Al día')).toBeInTheDocument();
		});

		it('si el reintento falla muestra el error del servidor', async () => {
			backend({ repo: estado({ sync_status: 'failed' }) });
			server.use(
				http.post(apiUrl(URL_PUSH), () =>
					HttpResponse.json({ detail: 'GitHub no responde' }, { status: 502 }),
				),
			);
			const { user } = renderizar();

			await user.click(await screen.findByRole('button', { name: 'Reintentar' }));

			const avisos = await screen.findAllByText('GitHub no responde');
			expect(avisos.length).toBeGreaterThan(0);
		});
	});

	it('si no puede consultar el estado muestra el error', async () => {
		server.use(
			http.get(apiUrl(URL_GITHUB), () => HttpResponse.json({ detail: 'Proyecto no encontrado' }, { status: 404 })),
		);
		renderizar();

		const card = await screen.findByText('Proyecto no encontrado');
		expect(card).toBeInTheDocument();
	});

	it('mientras GitHub sincroniza consulta el estado periódicamente hasta terminar', async () => {
		let consultas = 0;
		server.use(
			http.get(apiUrl('/api/v1/integrations/:provider/status'), () => HttpResponse.json(crearIntegracion())),
			http.get(apiUrl(URL_GITHUB), () => {
				consultas++;
				return HttpResponse.json(estado({ sync_status: consultas < 2 ? 'syncing' : 'synced' }));
			}),
		);
		renderizar();

		expect(await screen.findByText('Sincronizando el código con GitHub...')).toBeInTheDocument();
		await waitFor(() => expect(screen.getByText('Al día')).toBeInTheDocument(), { timeout: 4_000 });
		expect(consultas).toBeGreaterThanOrEqual(2);
	});
});
