import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useProjectStore } from '@/entities/project';
import {
	HttpResponse,
	apiUrl,
	crearProyecto,
	delay,
	http,
	mockRouter,
	renderWithProviders,
	server,
} from '@/test';
import { CreateProjectForm } from './CreateProjectForm';

const DESCRIPCION =
	'Aplicación para gestionar el inventario y las ventas diarias de una ferretería de barrio.';

const campos = () => ({
	nombre: screen.getByLabelText('Nombre del proyecto'),
	descripcion: screen.getByLabelText('Descripción'),
	repo: screen.getByLabelText('Nombre del repositorio'),
});
const botonCrear = () => screen.getByRole('button', { name: /Crear proyecto/ });

/** Registra las peticiones de creación de proyecto y de push a GitHub. */
function espiarBackend() {
	const creaciones: unknown[] = [];
	const pushes: unknown[] = [];
	server.use(
		http.post(apiUrl('/api/v1/projects'), async ({ request }) => {
			const body = (await request.json()) as { name: string; description: string };
			creaciones.push(body);
			return HttpResponse.json(crearProyecto({ id: 'prj_nuevo', ...body }), {
				status: 201,
			});
		}),
		http.post(apiUrl('/api/v1/projects/:id/github/push'), async ({ request, params }) => {
			pushes.push({ id: params.id, ...((await request.json()) as object) });
			return HttpResponse.json({ has_repository: true, sync_status: 'synced' });
		}),
	);
	return { creaciones, pushes };
}

async function renderizar({
	proyectosExistentes = [crearProyecto({ name: 'Proyecto Previo' })],
} = {}) {
	useProjectStore.setState({ projects: proyectosExistentes });
	const utils = renderWithProviders(<CreateProjectForm />);
	return utils;
}

async function completar(
	user: Awaited<ReturnType<typeof renderizar>>['user'],
	{ nombre = 'Ferreteria Central', descripcion = DESCRIPCION } = {},
) {
	if (nombre) await user.type(campos().nombre, nombre);
	if (descripcion) {
		await user.click(campos().descripcion);
		await user.paste(descripcion);
	}
}

describe('CreateProjectForm', () => {
	describe('valores iniciales', () => {
		it('arranca vacío con el repositorio por defecto bloqueado', async () => {
			await renderizar();

			expect(campos().nombre).toHaveValue('');
			expect(campos().descripcion).toHaveValue('');
			expect(campos().repo).toHaveValue('kosmo-repositorio');
			expect(campos().repo).toBeDisabled();
			expect(screen.getByText('0/25')).toBeInTheDocument();
			expect(screen.getByText('0/1000')).toBeInTheDocument();
		});

		it('carga los proyectos existentes si el store está vacío', async () => {
			await renderizar({ proyectosExistentes: [] });

			await waitFor(() => expect(useProjectStore.getState().projects).toHaveLength(2));
		});
	});

	describe('campo nombre', () => {
		it('deriva el nombre del repositorio en formato kebab-case', async () => {
			const { user } = await renderizar();

			await user.type(campos().nombre, 'Gestor De Tareas');

			expect(campos().repo).toHaveValue('kosmo-gestor-de-tareas');
		});

		it('descarta números, símbolos y tildes mientras se escribe', async () => {
			const { user } = await renderizar();

			await user.type(campos().nombre, 'App 2.0 Gestión!');

			expect(campos().nombre).toHaveValue('App  Gestin');
		});

		it('limita el nombre a 25 caracteres', async () => {
			const { user } = await renderizar();

			await user.type(campos().nombre, 'A'.repeat(30));

			expect(campos().nombre).toHaveValue('A'.repeat(25));
			expect(screen.getByText('25/25')).toBeInTheDocument();
		});

		it('vuelve al repositorio por defecto si se borra el nombre', async () => {
			const { user } = await renderizar();
			await user.type(campos().nombre, 'Tienda');

			await user.clear(campos().nombre);

			expect(campos().repo).toHaveValue('kosmo-repositorio');
		});
	});

	it('limita la descripción a 1000 caracteres', async () => {
		const { user } = await renderizar();

		await user.click(campos().descripcion);
		await user.paste('x'.repeat(1200));

		expect(campos().descripcion).toHaveValue('x'.repeat(1000));
		expect(screen.getByText('1000/1000')).toBeInTheDocument();
	});

	describe('validación al enviar', () => {
		it('muestra los errores de ambos campos y no crea nada', async () => {
			const { creaciones } = espiarBackend();
			const { user } = await renderizar();

			await user.click(botonCrear());

			const alertas = await screen.findAllByRole('alert');
			expect(alertas.map((a) => a.textContent)).toEqual([
				'Mínimo 3 caracteres',
				'Mínimo 50 caracteres',
			]);
			expect(creaciones).toHaveLength(0);
		});

		it('rechaza un nombre que ya usa otro proyecto (sin distinguir mayúsculas)', async () => {
			const { creaciones } = espiarBackend();
			const { user } = await renderizar({
				proyectosExistentes: [crearProyecto({ name: 'Ferreteria Central' })],
			});

			await completar(user, { nombre: 'ferreteria central' });
			await user.click(botonCrear());

			expect(await screen.findByRole('alert')).toHaveTextContent(
				'Ya existe un proyecto con ese nombre',
			);
			expect(creaciones).toHaveLength(0);
		});

		it('detecta duplicados contra los proyectos cargados desde el servidor', async () => {
			server.use(
				http.get(apiUrl('/api/v1/projects'), () =>
					HttpResponse.json([crearProyecto({ name: 'Tienda Online' })]),
				),
			);
			const { user } = await renderizar({ proyectosExistentes: [] });
			await waitFor(() => expect(useProjectStore.getState().projects).toHaveLength(1));

			await completar(user, { nombre: 'Tienda Online' });
			await user.click(botonCrear());

			expect(await screen.findByRole('alert')).toHaveTextContent(
				'Ya existe un proyecto con ese nombre',
			);
		});
	});

	describe('creación exitosa', () => {
		it('crea el proyecto, lo selecciona y navega a Descubrimiento', async () => {
			const { creaciones } = espiarBackend();
			const { user } = await renderizar();

			await completar(user);
			await user.click(botonCrear());

			await waitFor(() =>
				expect(mockRouter.replace).toHaveBeenCalledWith('/proyecto/descubrimiento'),
			);
			expect(creaciones).toEqual([
				{ name: 'Ferreteria Central', description: DESCRIPCION },
			]);
			const { currentProject, projects } = useProjectStore.getState();
			expect(currentProject?.id).toBe('prj_nuevo');
			expect(projects.map((p) => p.id)).toContain('prj_nuevo');
			expect(
				await screen.findByText('Proyecto creado correctamente'),
			).toBeInTheDocument();
		});

		it('crea el repositorio público en GitHub en segundo plano', async () => {
			const { pushes } = espiarBackend();
			const { user } = await renderizar();

			await completar(user);
			await user.click(botonCrear());

			await waitFor(() => expect(pushes).toHaveLength(1));
			expect(pushes[0]).toEqual({
				id: 'prj_nuevo',
				repo_name: 'kosmo-ferreteria-central',
				is_public: true,
			});
			await waitFor(() =>
				expect(useProjectStore.getState().githubSyncingProjectId).toBeNull(),
			);
		});

		it('si falla GitHub avisa sin bloquear la navegación', async () => {
			espiarBackend();
			server.use(
				http.post(apiUrl('/api/v1/projects/:id/github/push'), () =>
					HttpResponse.json({ detail: 'GitHub no disponible' }, { status: 502 }),
				),
			);
			vi.spyOn(console, 'error').mockImplementation(() => {});
			const { user } = await renderizar();

			await completar(user);
			await user.click(botonCrear());

			expect(
				await screen.findByText(/No se pudo inicializar el repositorio en GitHub/),
			).toBeInTheDocument();
			expect(mockRouter.replace).toHaveBeenCalledWith('/proyecto/descubrimiento');
			expect(useProjectStore.getState().githubSyncingProjectId).toBeNull();
		});

		it('bloquea el botón mientras se crea el proyecto', async () => {
			server.use(
				http.post(apiUrl('/api/v1/projects'), async () => {
					await delay('infinite');
					return HttpResponse.json({});
				}),
			);
			const { user } = await renderizar();

			await completar(user);
			await user.click(botonCrear());

			expect(
				await screen.findByRole('button', { name: /Creando proyecto/ }),
			).toBeDisabled();
		});
	});

	it('si el servidor rechaza la creación muestra el error y permite reintentar', async () => {
		server.use(
			http.post(apiUrl('/api/v1/projects'), () =>
				HttpResponse.json({ detail: 'Límite de proyectos alcanzado' }, { status: 403 }),
			),
		);
		const { user } = await renderizar();

		await completar(user);
		await user.click(botonCrear());

		expect(await screen.findByText('Límite de proyectos alcanzado')).toBeInTheDocument();
		expect(botonCrear()).toBeEnabled();
		expect(mockRouter.replace).not.toHaveBeenCalled();
	});

	it('Cancelar vuelve al listado de proyectos', async () => {
		const { user } = await renderizar();

		await user.click(screen.getByRole('button', { name: 'Cancelar' }));

		expect(mockRouter.push).toHaveBeenCalledWith('/proyecto');
	});
});
