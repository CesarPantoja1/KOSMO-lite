import { act, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useProjectStore } from '@/entities/project';
import { useAppStore } from '@/features/app-state';
import {
	HttpResponse,
	apiUrl,
	crearEstadoConsistencia,
	crearProyecto,
	http,
	mockRouter,
	renderWithProviders,
	server,
} from '@/test';
import { WizardNavegacion } from './WizardNavegacion';

const URL_STATUS = '/api/v1/projects/:projectId/consistency/status';
const FASES = ['DESCUBRIMIENTO', 'FUNCIONALIDADES', 'CRITERIOS', 'IMPLEMENTACIÓN'];

function abrirProyecto() {
	useProjectStore.setState({
		currentProject: crearProyecto({ id: 'prj_1' }),
		isProyectosOpen: true,
	});
}

const enlaceFase = (label: string) =>
	screen.getByRole('link', { name: new RegExp(label) });
const etiqueta = (label: string) => screen.getByText(label);

describe('WizardNavegacion (integración de componentes)', () => {
	afterEach(() => {
		vi.useRealTimers();
	});

	it('no se muestra si no hay un proyecto abierto', () => {
		const { container } = renderWithProviders(<WizardNavegacion />, {
			route: { pathname: '/proyecto/descubrimiento' },
		});

		expect(container).toBeEmptyDOMElement();
	});

	it('muestra las cuatro fases enlazadas a su ruta', () => {
		abrirProyecto();
		renderWithProviders(<WizardNavegacion />, {
			route: { pathname: '/proyecto/descubrimiento' },
		});

		expect(enlaceFase('DESCUBRIMIENTO')).toHaveAttribute(
			'href',
			'/proyecto/descubrimiento',
		);
		expect(enlaceFase('FUNCIONALIDADES')).toHaveAttribute(
			'href',
			'/proyecto/caracteristicas',
		);
		expect(enlaceFase('CRITERIOS')).toHaveAttribute('href', '/proyecto/requisitos');
		expect(enlaceFase('IMPLEMENTACIÓN')).toHaveAttribute('href', '/proyecto/codigo');
	});

	it.each([
		['/proyecto/descubrimiento', ['active', 'disable', 'disable', 'disable']],
		['/proyecto/caracteristicas/nueva', ['completed', 'active', 'disable', 'disable']],
		['/proyecto/requisitos', ['completed', 'completed', 'active', 'disable']],
		['/proyecto/codigo/resumen', ['completed', 'completed', 'completed', 'active']],
	])(
		'en %s marca las fases completadas, la activa y las pendientes',
		(pathname, estados) => {
			abrirProyecto();
			renderWithProviders(<WizardNavegacion />, { route: { pathname } });

			const clase = {
				active: 'text-wizard-label-active',
				completed: 'text-wizard-label-completed',
				disable: 'text-wizard-label-pending',
			};
			FASES.forEach((fase, i) => {
				expect(etiqueta(fase)).toHaveClass(clase[estados[i] as keyof typeof clase]);
			});
		},
	);

	it('con cambios sin guardar intercepta la navegación entre fases', async () => {
		abrirProyecto();
		useAppStore.setState({ hasUnsavedChanges: true });
		const { user } = renderWithProviders(<WizardNavegacion />, {
			route: { pathname: '/proyecto/descubrimiento' },
		});

		await user.click(enlaceFase('CRITERIOS'));

		expect(useAppStore.getState().pendingNavigationPath).toBe('/proyecto/requisitos');
	});

	it('muestra en cada fase los cambios de consistencia pendientes', async () => {
		abrirProyecto();
		server.use(
			http.get(apiUrl(URL_STATUS), () =>
				HttpResponse.json(
					crearEstadoConsistencia({
						features: { pending: 2, evaluating: 0, failed: 0 },
						implementation: { pending: 0, evaluating: 0, failed: 1 },
					}),
				),
			),
		);
		renderWithProviders(<WizardNavegacion />, {
			route: { pathname: '/proyecto/requisitos' },
		});

		expect(
			await screen.findByTitle('2 cambio(s) pendiente(s) de revisión'),
		).toBeInTheDocument();
		expect(screen.getByTitle('Fallos en la evaluación (1)')).toBeInTheDocument();
		expect(
			screen.getByRole('button', { name: 'Revisar consistencia (2 pendientes)' }),
		).toBeInTheDocument();
	});

	it('avisa con un toast cuando termina una evaluación con sugerencias pendientes', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		abrirProyecto();
		let respuesta = crearEstadoConsistencia({
			requirements: { pending: 0, evaluating: 1, failed: 0 },
		});
		server.use(http.get(apiUrl(URL_STATUS), () => HttpResponse.json(respuesta)));
		const { user } = renderWithProviders(<WizardNavegacion />, {
			route: { pathname: '/proyecto/descubrimiento' },
			userEventOptions: { advanceTimers: vi.advanceTimersByTime },
		});
		expect(await screen.findByText('Analizando consistencia…')).toBeInTheDocument();

		respuesta = crearEstadoConsistencia({
			requirements: { pending: 3, evaluating: 0, failed: 0 },
		});
		await act(() => vi.advanceTimersByTimeAsync(10_000));

		const aviso = await screen.findByRole('alertdialog');
		expect(within(aviso).getByText('Consistencia evaluada')).toBeInTheDocument();
		expect(
			within(aviso).getByText('3 sugerencia(s) pendiente(s) de revisión'),
		).toBeInTheDocument();

		await user.click(within(aviso).getByRole('button', { name: 'Revisar' }));
		expect(mockRouter.push).toHaveBeenCalledWith('/proyecto/requisitos/consistencia');
	});

	it('avisa si falta configurar la API key de IA', async () => {
		abrirProyecto();
		server.use(
			http.get(apiUrl('/api/v1/ai-config'), () =>
				HttpResponse.json({ has_api_key: false, is_custom: false }),
			),
		);

		renderWithProviders(<WizardNavegacion />, {
			route: { pathname: '/proyecto/descubrimiento' },
		});

		expect(await screen.findByText(/API Key de IA no configurada/)).toBeInTheDocument();
	});
});
