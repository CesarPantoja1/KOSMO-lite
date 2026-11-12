import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useCharacteristicStore } from '@/entities/characteristic';
import type { CreateCharacteristicResponse } from '@/entities/characteristic/model/types';
import { useProjectStore } from '@/entities/project';
import {
	HttpResponse,
	apiUrl,
	crearCaracteristica,
	crearProyecto,
	crearSugerencia,
	delay,
	http,
	mockRouter,
	renderWithProviders,
	server,
} from '@/test';
import CreateCharacteristic from './CreateCharacteristicPage';

const URL_MANUAL = '/api/v1/projects/:projectId/features/manual';

const campoTitulo = () => screen.getByPlaceholderText(/Categorización inteligente/);
const campoDescripcion = () => screen.getByPlaceholderText(/Asigna automáticamente/);
const botonCrear = () => screen.getByRole('button', { name: /Crear funcionalidad/ });

function responderGuardado(respuesta: Partial<CreateCharacteristicResponse>, demora = 0) {
	server.use(
		http.post(apiUrl(URL_MANUAL), async () => {
			if (demora) await delay(demora);
			return HttpResponse.json<CreateCharacteristicResponse>({
				is_saved: true,
				feature: crearCaracteristica(),
				origin: 'manual',
				is_consistent: true,
				...respuesta,
			});
		}),
	);
}

function renderizar() {
	useProjectStore.setState({ currentProject: crearProyecto({ id: 'prj_1' }) });
	return renderWithProviders(<CreateCharacteristic />);
}

async function completar(user: ReturnType<typeof renderizar>['user']) {
	await user.type(campoTitulo(), 'Inicio de sesion');
	await user.type(campoDescripcion(), 'El usuario se autentica con su correo.');
}

describe('CreateCharacteristicPage', () => {
	it('muestra el formulario vacío con sus contadores', () => {
		renderizar();

		expect(
			screen.getByRole('heading', { name: 'Nueva funcionalidad' }),
		).toBeInTheDocument();
		expect(screen.getByText('0/50')).toBeInTheDocument();
		expect(screen.getByText('0/500')).toBeInTheDocument();
	});

	it('actualiza los contadores al escribir', async () => {
		const { user } = renderizar();

		await completar(user);

		expect(screen.getByText('16/50')).toBeInTheDocument();
		expect(screen.getByText('38/500')).toBeInTheDocument();
	});

	it('marca los campos obligatorios al enviar vacío', async () => {
		const { user } = renderizar();

		await user.click(botonCrear());

		const alertas = await screen.findAllByRole('alert');
		expect(alertas).toHaveLength(2);
		alertas.forEach((a) => expect(a).toHaveTextContent('Este campo es obligatorio'));
		expect(campoTitulo()).toHaveClass('border-error-500');
	});

	it('muestra el análisis de coherencia mientras valida y luego vuelve al listado', async () => {
		responderGuardado({}, 100);
		const { user } = renderizar();
		await completar(user);

		await user.click(botonCrear());

		expect(await screen.findByText('Verificando funcionalidad')).toBeInTheDocument();
		await waitFor(() =>
			expect(mockRouter.push).toHaveBeenCalledWith('/proyecto/caracteristicas'),
		);
		expect(screen.queryByText('Verificando funcionalidad')).not.toBeInTheDocument();
		expect(useCharacteristicStore.getState().currentCharacteristics).toHaveLength(1);
	});

	it('explica por qué la IA rechazó la funcionalidad y permite cerrar el aviso', async () => {
		responderGuardado({
			is_saved: false,
			feature: undefined,
			is_consistent: false,
			inconsistency_reason: 'El descubrimiento excluye los pagos en línea',
		});
		const { user } = renderizar();
		await completar(user);

		await user.click(botonCrear());

		expect(
			await screen.findByRole('heading', { name: 'Revisión de coherencia' }),
		).toBeInTheDocument();
		expect(
			screen.getByText('El descubrimiento excluye los pagos en línea'),
		).toBeInTheDocument();
		expect(mockRouter.push).not.toHaveBeenCalled();

		await user.click(screen.getByRole('button', { name: 'Entendido' }));
		expect(screen.queryByText('Revisión de coherencia')).not.toBeInTheDocument();
		expect(campoTitulo()).toHaveValue('Inicio de sesion');
	});

	describe('sugerencias de la IA', () => {
		it('aplica la sugerencia elegida al formulario', async () => {
			const sugerencias = [
				crearSugerencia({
					title: 'Registro de gastos',
					description: 'Anota cada gasto.',
				}),
				crearSugerencia({
					title: 'Reporte mensual',
					description: 'Resume los gastos del mes.',
				}),
			];
			server.use(
				http.post(apiUrl('/api/v1/projects/:projectId/features/suggest'), async () => {
					await delay(50);
					return HttpResponse.json(sugerencias);
				}),
			);
			const { user } = renderizar();

			await user.click(screen.getByRole('button', { name: /Sugerir ideas/ }));
			expect(await screen.findByText('Buscando ideas')).toBeInTheDocument();

			expect(
				await screen.findByRole('heading', { name: 'Ideas de funcionalidades' }),
			).toBeInTheDocument();
			const aplicar = screen.getByRole('button', { name: /Aplicar sugerencia/ });
			expect(aplicar).toBeDisabled();

			await user.click(screen.getByRole('button', { name: /Reporte mensual/ }));
			await user.click(aplicar);

			expect(screen.queryByText('Ideas de funcionalidades')).not.toBeInTheDocument();
			expect(campoTitulo()).toHaveValue('Reporte mensual');
			expect(campoDescripcion()).toHaveValue('Resume los gastos del mes.');
		});

		it('informa si no se pudieron cargar las sugerencias', async () => {
			server.use(
				http.post(apiUrl('/api/v1/projects/:projectId/features/suggest'), () =>
					HttpResponse.json({}, { status: 500 }),
				),
			);
			const { user } = renderizar();

			await user.click(screen.getByRole('button', { name: /Sugerir ideas/ }));

			expect(
				await screen.findByRole('heading', {
					name: 'No se pudieron cargar las sugerencias',
				}),
			).toBeInTheDocument();
		});
	});

	it('Cancelar vuelve al listado sin guardar', async () => {
		const { user } = renderizar();

		await user.click(screen.getByRole('button', { name: 'Cancelar' }));

		expect(mockRouter.push).toHaveBeenCalledWith('/proyecto/caracteristicas');
	});
});
