/**
 * Integración: RequirementsPage + stores de características y requisitos + API (MSW)
 * + panel lateral y asistente de requisitos reales.
 * El editor MDXEditor no funciona en jsdom, así que se sustituye por un doble
 * (textarea) que respeta el mismo contrato de props.
 */
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useAppStore } from '@/features/app-state';
import { useCharacteristicStore } from '@/entities/characteristic';
import { useProjectStore } from '@/entities/project';
import { useRequirementsStore } from '@/entities/requirements';
import {
	HttpResponse,
	apiUrl,
	crearCaracteristica,
	crearProyecto,
	delay,
	http,
	mockRouter,
	renderWithProviders,
	respuestaSse,
	server,
} from '@/test';
import { RequirementsPage } from './RequirementsPage';

vi.mock('@/features/markdown-editor', () => ({
	MarkdownEditor: (props: {
		markdown: string;
		onChange: (value: string) => void;
		isMaximized: boolean;
		onMaximize: () => void;
		onMinimize: () => void;
		saveStatus: string;
	}) => (
		<div>
			<textarea
				aria-label='Editor de requisitos'
				value={props.markdown}
				onChange={(e) => props.onChange(e.target.value)}
			/>
			<span data-testid='estado-guardado'>{props.saveStatus}</span>
			<button
				type='button'
				onClick={props.isMaximized ? props.onMinimize : props.onMaximize}
			>
				{props.isMaximized ? 'Minimizar' : 'Maximizar'}
			</button>
		</div>
	),
}));

const URL_FEATURES = '/api/v1/projects/:projectId/features';
const URL_REQUISITOS = '/api/v1/features/:featureId/requirements';
const URL_GENERAR = '/api/v1/features/:featureId/requirements/generate';
const URL_HISTORIAL = '/api/v1/features/:featureId/requirements/chat/history';
const URL_STREAM = '/api/v1/features/:featureId/requirements/chat/stream';

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
		title: 'Pagos',
		description: 'Cobro con tarjeta',
	}),
];

/** Documentos de requisitos que devuelve el backend, por característica. */
type Documentos = Record<string, string | null>;

function renderizar({
	caracteristicas = CARACTERISTICAS,
	documentos = {},
}: { caracteristicas?: typeof CARACTERISTICAS; documentos?: Documentos } = {}) {
	useProjectStore.setState({ currentProject: crearProyecto({ id: 'prj_1' }) });
	useRequirementsStore.setState({
		hasRequirements: Object.fromEntries(
			Object.entries(documentos).map(([id, doc]) => [id, !!doc]),
		),
		currentRequirements: Object.fromEntries(
			Object.entries(documentos).filter(([, doc]) => !!doc),
		) as Record<string, string>,
	});
	server.use(
		http.get(apiUrl(URL_FEATURES), () => HttpResponse.json(caracteristicas)),
		http.get(apiUrl(URL_REQUISITOS), ({ params }) =>
			HttpResponse.json({
				document_markdown: documentos[String(params.featureId)] ?? null,
			}),
		),
		http.get(apiUrl(URL_HISTORIAL), () =>
			HttpResponse.json({ messages: [], has_more: false, next_cursor: null }),
		),
	);
	return renderWithProviders(<RequirementsPage />);
}

const editor = () => screen.getByRole('textbox', { name: 'Editor de requisitos' });
const itemLateral = (nombre: RegExp) => screen.getByRole('button', { name: nombre });

describe('RequirementsPage (integración)', () => {
	describe('carga inicial', () => {
		it('sin características guía al usuario a definirlas primero', async () => {
			renderizar({ caracteristicas: [] });

			expect(
				await screen.findByRole('heading', { name: 'No hay funcionalidades definidas' }),
			).toBeInTheDocument();
			expect(screen.getByRole('link', { name: /Ir a Funcionalidades/ })).toHaveAttribute(
				'href',
				'/proyecto/caracteristicas',
			);
			expect(screen.queryByRole('link', { name: /Continuar/ })).not.toBeInTheDocument();
		});

		it('selecciona la primera característica y muestra sus requisitos', async () => {
			renderizar({ documentos: { feat_1: '# Requisitos de inicio de sesión' } });

			await waitFor(() =>
				expect(editor()).toHaveValue('# Requisitos de inicio de sesión'),
			);
			expect(useCharacteristicStore.getState().selectedId).toBe('feat_1');
			expect(screen.getByText('Acceso con correo')).toBeInTheDocument();
			expect(screen.getByRole('button', { name: /Mejorar con IA/ })).toBeInTheDocument();
		});

		// Defecto conocido: al terminar la carga, el store actualiza `currentRequirements`,
		// lo que vuelve a ejecutar el efecto y cancela la carga en curso antes de apagar
		// `isLoadingRequirements`; la segunda ejecución sale por la caché sin apagarlo.
		// Ocurre cuando la caché local está vacía (otro dispositivo, tras cerrar sesión).
		it.fails(
			'carga los requisitos desde el servidor cuando no están en caché',
			async () => {
				useProjectStore.setState({ currentProject: crearProyecto({ id: 'prj_1' }) });
				useRequirementsStore.setState({ hasRequirements: { feat_1: true } });
				server.use(
					http.get(apiUrl(URL_FEATURES), () => HttpResponse.json(CARACTERISTICAS)),
					http.get(apiUrl(URL_REQUISITOS), () =>
						HttpResponse.json({ document_markdown: '# Desde el servidor' }),
					),
				);
				renderWithProviders(<RequirementsPage />);

				await waitFor(() => expect(editor()).toHaveValue('# Desde el servidor'));
			},
		);

		it('si falla la carga de características muestra el error', async () => {
			server.use(
				http.get(apiUrl(URL_FEATURES), () =>
					HttpResponse.json({ detail: 'Proyecto no disponible' }, { status: 500 }),
				),
			);
			useProjectStore.setState({ currentProject: crearProyecto({ id: 'prj_1' }) });
			renderWithProviders(<RequirementsPage />);

			expect(await screen.findByText('Proyecto no disponible')).toBeInTheDocument();
		});

		it('si falla la carga de requisitos muestra el error', async () => {
			renderizar();
			server.use(
				http.get(apiUrl(URL_REQUISITOS), () =>
					HttpResponse.json({ detail: 'Requisitos corruptos' }, { status: 500 }),
				),
			);

			expect(await screen.findByText('Requisitos corruptos')).toBeInTheDocument();
		});
	});

	describe('generación', () => {
		it('una característica sin requisitos ofrece generarlos y oculta "Mejorar con IA"', async () => {
			renderizar();

			expect(
				await screen.findByRole('heading', { name: 'Aún no hay criterios generados' }),
			).toBeInTheDocument();
			expect(
				screen.queryByRole('button', { name: /Mejorar con IA/ }),
			).not.toBeInTheDocument();
		});

		it('genera los criterios EARS mostrando el progreso', async () => {
			server.use(
				http.post(apiUrl(URL_GENERAR), async () => {
					await delay(50);
					return HttpResponse.json({ document_markdown: '# EARS: inicio de sesión' });
				}),
			);
			const { user } = renderizar();

			await user.click(await screen.findByRole('button', { name: /Generar criterios/ }));

			expect(
				await screen.findByText('Generando criterios de aceptación'),
			).toBeInTheDocument();
			await waitFor(() => expect(editor()).toHaveValue('# EARS: inicio de sesión'));
			expect(useRequirementsStore.getState().hasRequirements.feat_1).toBe(true);
		});

		it('si la generación falla muestra el error', async () => {
			server.use(
				http.post(apiUrl(URL_GENERAR), () =>
					HttpResponse.json({ detail: 'Servicio de IA no disponible' }, { status: 503 }),
				),
			);
			const { user } = renderizar();

			await user.click(await screen.findByRole('button', { name: /Generar criterios/ }));

			expect(await screen.findByText('Servicio de IA no disponible')).toBeInTheDocument();
			expect(screen.getByRole('button', { name: /Generar criterios/ })).toBeEnabled();
		});
	});

	describe('cambio de característica', () => {
		it('sin cambios pendientes cambia directamente', async () => {
			const { user } = renderizar({
				documentos: { feat_1: '# Inicio', feat_2: '# Pagos' },
			});
			await waitFor(() => expect(editor()).toHaveValue('# Inicio'));

			await user.click(itemLateral(/F-002.*Pagos/));

			await waitFor(() => expect(editor()).toHaveValue('# Pagos'));
			expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
		});

		it('con cambios sin guardar pide confirmación antes de descartarlos', async () => {
			const { user } = renderizar({
				documentos: { feat_1: '# Inicio', feat_2: '# Pagos' },
			});
			await waitFor(() => expect(editor()).toHaveValue('# Inicio'));
			await user.type(editor(), ' editado');

			await user.click(itemLateral(/F-002.*Pagos/));
			const dialogo = screen.getByRole('dialog', { name: 'Cambios sin guardar' });
			expect(useCharacteristicStore.getState().selectedId).toBe('feat_1');

			await user.click(within(dialogo).getByRole('button', { name: 'Aceptar' }));

			await waitFor(() => expect(editor()).toHaveValue('# Pagos'));
			expect(useCharacteristicStore.getState().selectedId).toBe('feat_2');
		});

		it('cancelar la confirmación conserva la edición en curso', async () => {
			const { user } = renderizar({
				documentos: { feat_1: '# Inicio', feat_2: '# Pagos' },
			});
			await waitFor(() => expect(editor()).toHaveValue('# Inicio'));
			await user.type(editor(), '!');

			await user.click(itemLateral(/F-002.*Pagos/));
			await user.click(screen.getByRole('button', { name: 'Cancelar' }));

			expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
			expect(editor()).toHaveValue('# Inicio!');
		});
	});

	describe('eliminar requisitos', () => {
		it('tras confirmar elimina los requisitos y vuelve al estado sin criterios', async () => {
			const eliminados: string[] = [];
			const documentos: Documentos = { feat_1: '# Inicio' };
			server.use(
				http.delete(apiUrl(URL_REQUISITOS), ({ params }) => {
					eliminados.push(String(params.featureId));
					documentos[String(params.featureId)] = null;
					return new HttpResponse(null, { status: 204 });
				}),
			);
			const { user } = renderizar({ documentos });
			await waitFor(() => expect(editor()).toHaveValue('# Inicio'));

			await user.click(screen.getByTitle('Eliminar'));
			const dialogo = screen.getByRole('dialog', { name: 'Eliminar requisitos' });
			await user.click(within(dialogo).getByRole('button', { name: 'Eliminar' }));

			expect(await screen.findByText('Requisitos eliminados')).toBeInTheDocument();
			expect(eliminados).toEqual(['feat_1']);
			expect(
				await screen.findByRole('heading', { name: 'Aún no hay criterios generados' }),
			).toBeInTheDocument();
		});

		it('si el servidor falla conserva los requisitos', async () => {
			server.use(
				http.delete(apiUrl(URL_REQUISITOS), () =>
					HttpResponse.json({ detail: 'No se pudo eliminar' }, { status: 500 }),
				),
			);
			const { user } = renderizar({ documentos: { feat_1: '# Inicio' } });
			await waitFor(() => expect(editor()).toHaveValue('# Inicio'));

			await user.click(screen.getByTitle('Eliminar'));
			await user.click(
				within(screen.getByRole('dialog')).getByRole('button', { name: 'Eliminar' }),
			);

			expect(await screen.findByText('No se pudo eliminar')).toBeInTheDocument();
			expect(editor()).toHaveValue('# Inicio');
		});

		it('cancelar no elimina nada', async () => {
			const { user } = renderizar({ documentos: { feat_1: '# Inicio' } });
			await waitFor(() => expect(editor()).toHaveValue('# Inicio'));

			await user.click(screen.getByTitle('Eliminar'));
			await user.click(screen.getByRole('button', { name: 'Cancelar' }));

			expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
			expect(useRequirementsStore.getState().hasRequirements.feat_1).toBe(true);
		});
	});

	describe('navegación', () => {
		it('"Continuar" sin cambios deja navegar al código', async () => {
			const { user } = renderizar({ documentos: { feat_1: '# Inicio' } });
			await waitFor(() => expect(editor()).toHaveValue('# Inicio'));

			const continuar = screen.getByRole('link', { name: /Continuar/ });
			expect(continuar).toHaveAttribute('href', 'codigo');
			await user.click(continuar);

			expect(useAppStore.getState().pendingNavigationPath).toBeNull();
			expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
		});

		it('"Continuar" con cambios sin guardar pide confirmación y luego navega', async () => {
			const { user } = renderizar({ documentos: { feat_1: '# Inicio' } });
			await waitFor(() => expect(editor()).toHaveValue('# Inicio'));
			await user.type(editor(), '!');

			await user.click(screen.getByRole('link', { name: /Continuar/ }));
			const dialogo = screen.getByRole('dialog', { name: 'Cambios sin guardar' });
			await user.click(within(dialogo).getByRole('button', { name: 'Aceptar' }));

			expect(mockRouter.push).toHaveBeenCalledWith('codigo');
			expect(useAppStore.getState().hasUnsavedChanges).toBe(false);
		});

		it('maximizar el editor oculta las acciones de la cabecera', async () => {
			const { user } = renderizar({ documentos: { feat_1: '# Inicio' } });
			await waitFor(() => expect(editor()).toHaveValue('# Inicio'));

			await user.click(screen.getByRole('button', { name: 'Maximizar' }));

			expect(screen.queryByRole('link', { name: /Continuar/ })).not.toBeInTheDocument();

			await user.click(screen.getByRole('button', { name: 'Minimizar' }));
			expect(screen.getByRole('link', { name: /Continuar/ })).toBeInTheDocument();
		});
	});

	describe('guardado automático', () => {
		it('guarda la edición tras la pausa de escritura', async () => {
			const guardados: unknown[] = [];
			server.use(
				http.put(apiUrl(URL_REQUISITOS), async ({ request }) => {
					guardados.push(await request.json());
					return HttpResponse.json({ feature_id: 'feat_1', message: 'ok' });
				}),
			);
			renderizar({ documentos: { feat_1: '# Inicio' } });
			await waitFor(() => expect(editor()).toHaveValue('# Inicio'));
			vi.useFakeTimers({ shouldAdvanceTime: true });

			fireEvent.change(editor(), { target: { value: '# Inicio editado' } });
			act(() => vi.advanceTimersByTime(3_000));

			await waitFor(() =>
				expect(screen.getByTestId('estado-guardado')).toHaveTextContent('saved'),
			);
			vi.useRealTimers();
			expect(guardados).toHaveLength(1);
			expect(useRequirementsStore.getState().currentRequirements.feat_1).toBe(
				'# Inicio editado',
			);
		});
	});

	describe('mejorar con IA', () => {
		it('abre el asistente EARS y contrae el panel lateral', async () => {
			const { user } = renderizar({ documentos: { feat_1: '# Inicio' } });
			await waitFor(() => expect(editor()).toHaveValue('# Inicio'));

			await user.click(screen.getByRole('button', { name: /Mejorar con IA/ }));

			expect(screen.getByText('Asistente de Requisitos EARS')).toBeInTheDocument();
			expect(
				screen.queryByRole('heading', { name: 'Funcionalidades' }),
			).not.toBeInTheDocument();
		});

		it('si la IA modifica los requisitos, recarga el editor con la nueva versión', async () => {
			const documentos: Documentos = { feat_1: '# Inicio' };
			server.use(
				http.post(apiUrl(URL_STREAM), () => {
					documentos.feat_1 = '# Inicio\n\n- Escenario alternativo';
					return respuestaSse([
						{
							type: 'message',
							content: 'Agregué un escenario alternativo',
							modification: { applied: true },
						},
					]);
				}),
			);
			const { user } = renderizar({ documentos });
			await waitFor(() => expect(editor()).toHaveValue('# Inicio'));
			await user.click(screen.getByRole('button', { name: /Mejorar con IA/ }));

			await user.type(
				screen.getByRole('textbox', { name: 'Mensaje para el asistente' }),
				'Agrega un escenario alternativo{Enter}',
			);

			expect(
				await screen.findByText('Agregué un escenario alternativo'),
			).toBeInTheDocument();
			await waitFor(() =>
				expect(editor()).toHaveValue('# Inicio\n\n- Escenario alternativo'),
			);
		});

		it('cerrar el asistente vuelve a expandir el panel lateral', async () => {
			const { user } = renderizar({ documentos: { feat_1: '# Inicio' } });
			await waitFor(() => expect(editor()).toHaveValue('# Inicio'));
			await user.click(screen.getByRole('button', { name: /Mejorar con IA/ }));

			await user.click(screen.getByRole('button', { name: 'Cerrar chat' }));

			expect(screen.queryByText('Asistente de Requisitos EARS')).not.toBeInTheDocument();
			expect(
				screen.getByRole('heading', { name: 'Funcionalidades' }),
			).toBeInTheDocument();
		});
	});
});
