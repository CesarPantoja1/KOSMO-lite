/**
 * Integración: DiscoveryPage + store de descubrimiento + API (MSW) + chat real.
 * El editor MDXEditor no funciona en jsdom, así que se sustituye por un doble
 * (textarea) que respeta el mismo contrato de props.
 */
import { screen, waitFor, within } from '@testing-library/react';
import { forwardRef } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { useAppStore } from '@/features/app-state';
import { useDiscoveryStore } from '@/entities/discovery';
import { useProjectStore } from '@/entities/project';
import {
	HttpResponse,
	apiUrl,
	crearProyecto,
	delay,
	http,
	mockRouter,
	renderWithProviders,
	respuestaSse,
	server,
} from '@/test';
import { DiscoveryPage } from './DiscoveryPage';

vi.mock('@/features/markdown-editor', () => ({
	MarkdownEditor: forwardRef<
		unknown,
		{
			markdown: string;
			onChange: (value: string) => void;
			isMaximized: boolean;
			onMaximize: () => void;
			onMinimize: () => void;
			saveStatus: string;
		}
	>(function EditorDoble(props, _ref) {
		return (
			<div>
				<textarea
					aria-label='Editor de descubrimiento'
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
		);
	}),
}));

const URL_DISCOVERY = '/api/v1/projects/:projectId/discovery';
const URL_HISTORIAL = '/api/v1/projects/:projectId/discovery/chat';
const URL_STREAM = '/api/v1/projects/:projectId/discovery/chat/stream';

const documento = (content: string) => ({ id: 'disc_1', project_id: 'prj_1', content });

function renderizar({ contenido }: { contenido?: string } = {}) {
	useProjectStore.setState({ currentProject: crearProyecto({ id: 'prj_1' }) });
	if (contenido) useDiscoveryStore.setState({ currentDiscovery: documento(contenido) });
	server.use(
		http.get(apiUrl(URL_HISTORIAL), () =>
			HttpResponse.json({ messages: [], has_more: false, next_cursor: null }),
		),
	);
	return renderWithProviders(<DiscoveryPage />);
}

const editor = () => screen.getByRole('textbox', { name: 'Editor de descubrimiento' });

describe('DiscoveryPage (integración)', () => {
	describe('sin documento', () => {
		it('invita a analizar el proyecto y oculta las acciones del documento', () => {
			renderizar();

			expect(
				screen.getByRole('heading', { name: 'Aún no hay análisis del problema' }),
			).toBeInTheDocument();
			expect(
				screen.queryByRole('button', { name: /Mejorar con IA/ }),
			).not.toBeInTheDocument();
			expect(screen.queryByRole('button', { name: /Continuar/ })).not.toBeInTheDocument();
		});

		it('genera el documento con IA mostrando el progreso y luego lo carga en el editor', async () => {
			server.use(
				http.post(apiUrl(URL_DISCOVERY), async () => {
					await delay(50);
					return HttpResponse.json(documento('# Problema de negocio'));
				}),
			);
			const { user } = renderizar();

			await user.click(screen.getByRole('button', { name: /Analizar mi proyecto/ }));

			expect(await screen.findByText('Analizando tu proyecto')).toBeInTheDocument();
			await waitFor(() => expect(editor()).toHaveValue('# Problema de negocio'));
			expect(screen.queryByText('Analizando tu proyecto')).not.toBeInTheDocument();
			expect(useDiscoveryStore.getState().currentDiscovery?.content).toBe(
				'# Problema de negocio',
			);
		});

		it('si la generación falla muestra el error y mantiene el estado vacío', async () => {
			server.use(
				http.post(apiUrl(URL_DISCOVERY), () =>
					HttpResponse.json({ detail: 'Servicio de IA no disponible' }, { status: 503 }),
				),
			);
			const { user } = renderizar();

			await user.click(screen.getByRole('button', { name: /Analizar mi proyecto/ }));

			expect(await screen.findByText('Servicio de IA no disponible')).toBeInTheDocument();
			expect(
				screen.getByRole('heading', { name: 'Aún no hay análisis del problema' }),
			).toBeInTheDocument();
		});
	});

	describe('con documento', () => {
		it('muestra el contenido guardado en el editor', () => {
			renderizar({ contenido: '# Contexto' });

			expect(editor()).toHaveValue('# Contexto');
			expect(
				screen.queryByRole('heading', { name: 'Aún no hay análisis del problema' }),
			).not.toBeInTheDocument();
		});

		it('sin cambios, "Continuar" navega directamente a características', async () => {
			const { user } = renderizar({ contenido: '# Contexto' });

			await user.click(screen.getByRole('button', { name: /Continuar/ }));

			expect(mockRouter.push).toHaveBeenCalledWith('caracteristicas');
			expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
		});

		it('con cambios sin guardar pide confirmación, guarda y luego navega', async () => {
			const guardados: unknown[] = [];
			server.use(
				http.put(apiUrl(URL_DISCOVERY), async ({ request }) => {
					const body = (await request.json()) as { content: string };
					guardados.push(body);
					return HttpResponse.json(documento(body.content));
				}),
			);
			const { user } = renderizar({ contenido: '# Contexto' });
			await user.type(editor(), ' ampliado');

			await user.click(screen.getByRole('button', { name: /Continuar/ }));
			const dialogo = screen.getByRole('dialog', { name: 'Cambios sin guardar' });
			expect(mockRouter.push).not.toHaveBeenCalled();

			await user.click(within(dialogo).getByRole('button', { name: 'Aceptar' }));

			await waitFor(() =>
				expect(mockRouter.push).toHaveBeenCalledWith('caracteristicas'),
			);
			expect(guardados).toEqual([{ content: '# Contexto ampliado' }]);
			expect(useAppStore.getState().hasUnsavedChanges).toBe(false);
		});

		it('si el guardado falla al salir, no navega y marca el error', async () => {
			server.use(
				http.put(apiUrl(URL_DISCOVERY), () =>
					HttpResponse.json({ detail: 'caído' }, { status: 500 }),
				),
			);
			const { user } = renderizar({ contenido: '# Contexto' });
			await user.type(editor(), '!');

			await user.click(screen.getByRole('button', { name: /Continuar/ }));
			await user.click(screen.getByRole('button', { name: 'Aceptar' }));

			await waitFor(() =>
				expect(screen.getByTestId('estado-guardado')).toHaveTextContent('error'),
			);
			expect(mockRouter.push).not.toHaveBeenCalled();
		});

		it('cancelar la confirmación permanece en la página con los cambios', async () => {
			const { user } = renderizar({ contenido: '# Contexto' });
			await user.type(editor(), '!');

			await user.click(screen.getByRole('button', { name: /Continuar/ }));
			await user.click(screen.getByRole('button', { name: 'Cancelar' }));

			expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
			expect(editor()).toHaveValue('# Contexto!');
			expect(mockRouter.push).not.toHaveBeenCalled();
		});

		it('una navegación pendiente a otra ruta se confirma sin guardar', async () => {
			const { user } = renderizar({ contenido: '# Contexto' });
			await user.type(editor(), '!');
			useAppStore.getState().setPendingNavigationPath('/proyecto/requisitos');

			await user.click(await screen.findByRole('button', { name: 'Aceptar' }));

			expect(mockRouter.push).toHaveBeenCalledWith('/proyecto/requisitos');
			expect(useAppStore.getState().hasUnsavedChanges).toBe(false);
		});

		it('maximizar el editor oculta las acciones de la cabecera', async () => {
			const { user } = renderizar({ contenido: '# Contexto' });

			await user.click(screen.getByRole('button', { name: 'Maximizar' }));

			expect(useAppStore.getState().isEditorMaximized).toBe(true);
			expect(screen.queryByRole('button', { name: /Continuar/ })).not.toBeInTheDocument();

			await user.click(screen.getByRole('button', { name: 'Minimizar' }));
			expect(screen.getByRole('button', { name: /Continuar/ })).toBeInTheDocument();
		});
	});

	describe('mejorar con IA', () => {
		it('abre el chat del descubrimiento', async () => {
			const { user } = renderizar({ contenido: '# Contexto' });

			await user.click(screen.getByRole('button', { name: /Mejorar con IA/ }));

			expect(
				screen.getByRole('textbox', { name: 'Mensaje para el asistente' }),
			).toHaveAttribute('placeholder', 'ej., ¿Qué alcance tiene el módulo de pagos?');
		});

		it('si la IA modifica el documento, recarga el editor con la nueva versión', async () => {
			server.use(
				http.post(apiUrl(URL_STREAM), () =>
					respuestaSse([
						{
							type: 'message',
							content: 'Alcance actualizado',
							modification: { applied: true },
						},
					]),
				),
				http.get(apiUrl(URL_DISCOVERY), () =>
					HttpResponse.json(documento('# Contexto\n\n## Alcance: pagos')),
				),
			);
			const { user } = renderizar({ contenido: '# Contexto' });
			await user.click(screen.getByRole('button', { name: /Mejorar con IA/ }));

			await user.type(
				screen.getByRole('textbox', { name: 'Mensaje para el asistente' }),
				'Agrega el alcance de pagos{Enter}',
			);

			expect(await screen.findByText('Alcance actualizado')).toBeInTheDocument();
			await waitFor(() =>
				expect(editor()).toHaveValue('# Contexto\n\n## Alcance: pagos'),
			);
			expect(screen.getByText('Agrega el alcance de pagos')).toBeInTheDocument();
		});

		it('cerrar el chat lo oculta', async () => {
			const { user } = renderizar({ contenido: '# Contexto' });
			await user.click(screen.getByRole('button', { name: /Mejorar con IA/ }));

			await user.click(screen.getByRole('button', { name: 'Cerrar chat' }));

			expect(
				screen.queryByRole('textbox', { name: 'Mensaje para el asistente' }),
			).not.toBeInTheDocument();
		});
	});
});
