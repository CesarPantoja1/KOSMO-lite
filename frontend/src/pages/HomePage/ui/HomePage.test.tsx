import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useProjectStore } from '@/entities/project';
import { useDiscoveryStore } from '@/entities/discovery';
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
import { HomePage } from './HomePage';

const PROYECTOS = [
	crearProyecto({
		id: 'prj_a',
		name: 'tienda online',
		description: 'Ventas por internet',
		current_phase: 'requisitos',
	}),
	crearProyecto({
		id: 'prj_b',
		name: 'gestor de tareas',
		description: '',
		status: 'Pausado',
		current_phase: undefined,
	}),
];

function conProyectos(proyectos = PROYECTOS) {
	server.use(http.get(apiUrl('/api/v1/projects'), () => HttpResponse.json(proyectos)));
}

async function renderizarCargado() {
	const utils = renderWithProviders(<HomePage />);
	await screen.findByText('tienda online');
	return utils;
}

const vistaLista = () => screen.getByTitle('Vista de lista');
const vistaTarjetas = () => screen.getByTitle('Vista de tarjetas');

describe('HomePage (integración de componentes)', () => {
	it('muestra un esqueleto mientras carga los proyectos', async () => {
		server.use(
			http.get(apiUrl('/api/v1/projects'), async () => {
				await delay('infinite');
				return HttpResponse.json([]);
			}),
		);
		const { container } = renderWithProviders(<HomePage />);

		expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
		expect(screen.queryByRole('article')).not.toBeInTheDocument();
	});

	it('limpia el estado del proyecto anterior al entrar', async () => {
		conProyectos();
		useProjectStore.setState({ currentProject: crearProyecto({ id: 'prj_viejo' }) });
		useDiscoveryStore.setState({ currentDiscovery: { id: 'd1' } as never });

		await renderizarCargado();

		expect(useProjectStore.getState().currentProject).toBeNull();
		expect(useDiscoveryStore.getState().currentDiscovery).toBeNull();
	});

	describe('vista de tarjetas (por defecto)', () => {
		it('muestra una tarjeta por proyecto con sus datos', async () => {
			conProyectos();
			await renderizarCargado();

			const tarjetas = screen.getAllByRole('article');
			expect(tarjetas).toHaveLength(2);
			expect(within(tarjetas[0]).getByText('Ventas por internet')).toBeInTheDocument();
			expect(within(tarjetas[0]).getByText('requisitos')).toBeInTheDocument();
			expect(within(tarjetas[1]).getByText('Sin descripción')).toBeInTheDocument();
			expect(within(tarjetas[1]).getByText('Pausado')).toBeInTheDocument();
		});

		it('ofrece crear un nuevo proyecto', async () => {
			conProyectos();
			await renderizarCargado();

			const enlaces = screen.getAllByRole('link', { name: /nuevo proyecto/i });
			enlaces.forEach((e) => expect(e).toHaveAttribute('href', '/crear-proyecto'));
		});
	});

	describe('vista de lista', () => {
		it('alterna entre tarjetas y tabla', async () => {
			conProyectos();
			const { user } = await renderizarCargado();

			await user.click(vistaLista());
			expect(screen.getByRole('table')).toBeInTheDocument();
			expect(screen.queryByRole('article')).not.toBeInTheDocument();
			expect(vistaLista()).toHaveClass('bg-primary-500');

			await user.click(vistaTarjetas());
			expect(screen.queryByRole('table')).not.toBeInTheDocument();
			expect(screen.getAllByRole('article')).toHaveLength(2);
		});

		it('muestra una fila por proyecto con fase "Descubrimiento" por defecto', async () => {
			conProyectos();
			const { user } = await renderizarCargado();

			await user.click(vistaLista());

			const filas = within(screen.getByRole('table')).getAllByRole('row');
			// encabezado + 2 proyectos + pie
			expect(filas).toHaveLength(4);
			expect(within(filas[2]).getByText('Descubrimiento')).toBeInTheDocument();
		});

		it('indica cuando no hay proyectos', async () => {
			conProyectos([]);
			const { user } = renderWithProviders(<HomePage />);
			await waitFor(() => expect(screen.queryByRole('article')).not.toBeInTheDocument());

			await user.click(vistaLista());

			expect(screen.getByText(/No tienes proyectos creados/)).toBeInTheDocument();
		});
	});

	it.each(['tarjetas', 'lista'])(
		'abrir un proyecto (vista %s) lo selecciona y navega a Descubrimiento',
		async (vista) => {
			conProyectos();
			const { user } = await renderizarCargado();
			if (vista === 'lista') await user.click(vistaLista());

			await user.click(screen.getByText('gestor de tareas'));

			expect(useProjectStore.getState().currentProject?.id).toBe('prj_b');
			expect(mockRouter.push).toHaveBeenCalledWith('/proyecto/descubrimiento');
		},
	);

	describe.each(['tarjetas', 'lista'])('eliminar un proyecto (vista %s)', (vista) => {
		async function pedirEliminar() {
			conProyectos();
			const utils = await renderizarCargado();
			if (vista === 'lista') await utils.user.click(vistaLista());
			await utils.user.click(screen.getAllByTitle('Eliminar proyecto')[0]);
			return utils;
		}

		it('pide confirmación sin abrir el proyecto', async () => {
			await pedirEliminar();

			expect(
				screen.getByRole('dialog', { name: 'Eliminar proyecto' }),
			).toBeInTheDocument();
			expect(mockRouter.push).not.toHaveBeenCalled();
		});

		it('al confirmar lo elimina en el servidor y de la lista', async () => {
			const eliminados: string[] = [];
			server.use(
				http.delete(apiUrl('/api/v1/projects/:id'), ({ params }) => {
					eliminados.push(String(params.id));
					return new HttpResponse(null, { status: 204 });
				}),
			);
			const { user } = await pedirEliminar();

			await user.click(screen.getByRole('button', { name: 'Eliminar' }));

			expect(await screen.findByText('Proyecto eliminado')).toBeInTheDocument();
			expect(eliminados).toEqual(['prj_a']);
			expect(screen.queryByText('tienda online')).not.toBeInTheDocument();
		});

		it('si el servidor falla mantiene el proyecto y muestra el error', async () => {
			server.use(
				http.delete(apiUrl('/api/v1/projects/:id'), () =>
					HttpResponse.json(
						{ detail: 'El proyecto tiene un despliegue activo' },
						{ status: 409 },
					),
				),
			);
			const { user } = await pedirEliminar();

			await user.click(screen.getByRole('button', { name: 'Eliminar' }));

			expect(
				await screen.findByText('El proyecto tiene un despliegue activo'),
			).toBeInTheDocument();
			expect(screen.getByText('tienda online')).toBeInTheDocument();
		});

		it('cancelar no elimina nada', async () => {
			const { user } = await pedirEliminar();

			await user.click(screen.getByRole('button', { name: 'Cancelar' }));

			expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
			expect(screen.getByText('tienda online')).toBeInTheDocument();
		});
	});

	it('si falla la carga muestra la página vacía sin romperse', async () => {
		server.use(
			http.get(apiUrl('/api/v1/projects'), () => HttpResponse.json({}, { status: 500 })),
		);
		const consola = await import('vitest').then(({ vi }) =>
			vi.spyOn(console, 'error').mockImplementation(() => {}),
		);

		renderWithProviders(<HomePage />);

		await waitFor(() => expect(consola).toHaveBeenCalled());
		expect(screen.getByRole('heading', { name: 'Proyectos' })).toBeInTheDocument();
		expect(screen.getByText('Crear nuevo proyecto')).toBeInTheDocument();
	});
});
