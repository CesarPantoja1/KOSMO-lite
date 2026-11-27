import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useCharacteristicStore } from '@/entities/characteristic';
import { useDiscoveryStore } from '@/entities/discovery';
import { useProjectStore } from '@/entities/project';
import {
	HttpResponse,
	apiUrl,
	crearCaracteristica,
	crearProyecto,
	delay,
	http,
	renderWithProviders,
	respuestaSse,
	server,
} from '@/test';
import CharacteristicsPage from './CharacteristicsPage';

const URL_FEATURES = '/api/v1/projects/:projectId/features';

const CARACTERISTICAS = [
	crearCaracteristica({
		id: 'feat_1',
		display_id: 'F-001',
		title: 'Inicio de sesión',
		description: 'Acceso con correo',
	}),
	crearCaracteristica({
		id: 'feat_2',
		display_id: 'F-002',
		title: 'Registro de usuarios',
		description: 'Alta de cuentas',
	}),
	crearCaracteristica({
		id: 'feat_3',
		display_id: 'F-003',
		title: 'Reporte de ventas',
		description: 'Resumen mensual',
	}),
];

function conCaracteristicas(lista = CARACTERISTICAS) {
	server.use(http.get(apiUrl(URL_FEATURES), () => HttpResponse.json(lista)));
}

function renderizar({ conDescubrimiento = true } = {}) {
	useProjectStore.setState({ currentProject: crearProyecto({ id: 'prj_1' }) });
	if (conDescubrimiento)
		useDiscoveryStore.setState({ currentDiscovery: { id: 'disc_1' } as never });
	return renderWithProviders(<CharacteristicsPage />);
}

async function renderizarConLista() {
	conCaracteristicas();
	const utils = renderizar();
	await screen.findByText('Inicio de sesión');
	return utils;
}

const tarjeta = (titulo: string | RegExp) =>
	screen.getByRole('heading', { name: titulo }).closest('div.m-0\\.5') as HTMLElement;

describe('CharacteristicsPage (integración de componentes)', () => {
	it('lista las características del proyecto con su identificador', async () => {
		await renderizarConLista();

		expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(3);
		expect(within(tarjeta('Inicio de sesión')).getByText('F-001')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: /Nueva funcionalidad/ })).toHaveAttribute(
			'href',
			'caracteristicas/nueva',
		);
		expect(screen.getByRole('link', { name: /Continuar/ })).toHaveAttribute(
			'href',
			'requisitos',
		);
	});

	describe('búsqueda', () => {
		it('filtra por título y resalta la coincidencia', async () => {
			const { user } = await renderizarConLista();

			await user.type(screen.getByPlaceholderText('Buscar funcionalidad...'), 'regis');

			expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(1);
			const resaltado = within(tarjeta(/Registro de usuarios/)).getByText('Regis');
			expect(resaltado).toHaveClass('text-primary-600');
		});

		it('descarta números y símbolos en la búsqueda', async () => {
			const { user } = await renderizarConLista();
			const buscador = screen.getByPlaceholderText('Buscar funcionalidad...');

			await user.type(buscador, 'Reporte 2026!');

			expect(buscador).toHaveValue('Reporte ');
		});

		it('indica cuando no hay coincidencias', async () => {
			const { user } = await renderizarConLista();

			await user.type(screen.getByPlaceholderText('Buscar funcionalidad...'), 'xyz');

			expect(
				screen.getByText(
					'No se encontraron funcionalidades que coincidan con la búsqueda',
				),
			).toBeInTheDocument();
		});
	});

	describe('sin características', () => {
		it('sin descubrimiento guía al usuario a completarlo primero', async () => {
			conCaracteristicas([]);
			renderizar({ conDescubrimiento: false });

			expect(
				await screen.findByRole('heading', {
					name: 'No hay descubrimiento del proyecto',
				}),
			).toBeInTheDocument();
			expect(screen.getByRole('link', { name: /Ir a Descubrimiento/ })).toHaveAttribute(
				'href',
				'/proyecto/descubrimiento',
			);
		});

		it('con descubrimiento permite generarlas con IA', async () => {
			conCaracteristicas([]);
			server.use(
				http.post(apiUrl(URL_FEATURES), async () => {
					await delay(50);
					return HttpResponse.json(CARACTERISTICAS);
				}),
			);
			const { user } = renderizar();

			await user.click(
				await screen.findByRole('button', { name: /Generar funcionalidades/ }),
			);

			expect(await screen.findByText('Generando funcionalidades')).toBeInTheDocument();
			expect(await screen.findByText('Reporte de ventas')).toBeInTheDocument();
			expect(screen.queryByText('Generando funcionalidades')).not.toBeInTheDocument();
		});

		it('si la generación falla muestra el error', async () => {
			conCaracteristicas([]);
			server.use(
				http.post(apiUrl(URL_FEATURES), () =>
					HttpResponse.json(
						{ detail: 'El descubrimiento está incompleto' },
						{ status: 422 },
					),
				),
			);
			const { user } = renderizar();

			await user.click(
				await screen.findByRole('button', { name: /Generar funcionalidades/ }),
			);

			expect(
				await screen.findByText('El descubrimiento está incompleto'),
			).toBeInTheDocument();
			expect(
				screen.getByRole('button', { name: /Generar funcionalidades/ }),
			).toBeEnabled();
		});
	});

	describe('eliminar', () => {
		it('elimina la característica tras confirmar e informa del borrado en el código', async () => {
			const eliminadas: string[] = [];
			server.use(
				http.delete(apiUrl(`${URL_FEATURES}/:featureId`), ({ params }) => {
					eliminadas.push(String(params.featureId));
					return new HttpResponse(null, { status: 204 });
				}),
				http.get(apiUrl('/api/v1/implementations/:id/events'), () =>
					respuestaSse([
						{
							event_type: 'done',
							data: { delta: 'Código actualizado sin la funcionalidad' },
						},
					]),
				),
			);
			const { user } = await renderizarConLista();

			await user.click(within(tarjeta('Reporte de ventas')).getByTitle('Eliminar'));
			await user.click(
				within(screen.getByRole('dialog', { name: 'Eliminar funcionalidad' })).getByRole(
					'button',
					{
						name: 'Eliminar',
					},
				),
			);

			expect(await screen.findByText('Característica eliminada')).toBeInTheDocument();
			expect(eliminadas).toEqual(['feat_3']);
			expect(screen.queryByText('Reporte de ventas')).not.toBeInTheDocument();
			expect(
				await screen.findByText('Código actualizado sin la funcionalidad'),
			).toBeInTheDocument();
		});

		it('si el servidor falla mantiene la característica', async () => {
			server.use(
				http.delete(apiUrl(`${URL_FEATURES}/:featureId`), () =>
					HttpResponse.json({ detail: 'Tiene requisitos aprobados' }, { status: 409 }),
				),
			);
			const { user } = await renderizarConLista();

			await user.click(within(tarjeta('Inicio de sesión')).getByTitle('Eliminar'));
			await user.click(
				within(screen.getByRole('dialog')).getByRole('button', { name: 'Eliminar' }),
			);

			expect(await screen.findByText('Tiene requisitos aprobados')).toBeInTheDocument();
			expect(screen.getByText('Inicio de sesión')).toBeInTheDocument();
		});

		it('cancelar no elimina nada', async () => {
			const { user } = await renderizarConLista();

			await user.click(within(tarjeta('Inicio de sesión')).getByTitle('Eliminar'));
			await user.click(screen.getByRole('button', { name: 'Cancelar' }));

			expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
			expect(useCharacteristicStore.getState().currentCharacteristics).toHaveLength(3);
		});
	});

	describe('refinar con IA', () => {
		it('abre el chat de la característica y la marca como activa', async () => {
			const { user } = await renderizarConLista();

			await user.click(
				within(tarjeta('Registro de usuarios')).getByTitle('Mejorar con IA'),
			);

			expect(
				screen.getByRole('textbox', { name: 'Mensaje para el asistente' }),
			).toHaveAttribute('placeholder', 'ej. mejorar característica de búsqueda');
			expect(
				within(tarjeta('Registro de usuarios')).getByTitle('Refinando con IA'),
			).toBeDisabled();
		});

		it('si la IA aplica un cambio, recarga la lista con la versión actualizada', async () => {
			server.use(
				http.post(apiUrl('/api/v1/features/:id/chat/stream'), () =>
					respuestaSse([
						{
							type: 'message',
							content: 'Título actualizado',
							modification: { applied: true },
						},
					]),
				),
			);
			const { user } = await renderizarConLista();
			await user.click(
				within(tarjeta('Registro de usuarios')).getByTitle('Mejorar con IA'),
			);
			conCaracteristicas([
				CARACTERISTICAS[0],
				{ ...CARACTERISTICAS[1], title: 'Registro con verificación' },
				CARACTERISTICAS[2],
			]);

			await user.type(
				screen.getByRole('textbox', { name: 'Mensaje para el asistente' }),
				'Agrega verificación por correo{Enter}',
			);

			expect(await screen.findByText('Registro con verificación')).toBeInTheDocument();
			expect(screen.getByText('Título actualizado')).toBeInTheDocument();
		});

		it('cerrar el chat quita la marca de característica activa', async () => {
			const { user } = await renderizarConLista();
			await user.click(within(tarjeta('Inicio de sesión')).getByTitle('Mejorar con IA'));

			await user.click(screen.getByRole('button', { name: 'Cerrar chat' }));

			expect(
				screen.queryByRole('textbox', { name: 'Mensaje para el asistente' }),
			).not.toBeInTheDocument();
			await waitFor(() =>
				expect(
					within(tarjeta('Inicio de sesión')).getByTitle('Mejorar con IA'),
				).toBeEnabled(),
			);
		});
	});
});
