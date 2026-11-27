/**
 * Integración: layout principal (barra lateral + wizard + contenido) con los proyectos
 * cargados desde la API simulada.
 */
import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useProjectStore } from '@/entities/project';
import { useAppStore } from '@/features/app-state';
import { useAuthStore } from '@/shared/model/auth-store';
import {
	HttpResponse,
	apiUrl,
	crearProyecto,
	crearUsuario,
	http,
	mockRouter,
	renderWithProviders,
	server,
} from '@/test';
import { MainNavbar } from './MainNavbar';

function renderizar() {
	server.use(
		http.get(apiUrl('/api/v1/projects'), () =>
			HttpResponse.json([
				crearProyecto({ id: 'prj_a', name: 'tienda online' }),
				crearProyecto({ id: 'prj_b', name: 'gestor de tareas' }),
			]),
		),
	);
	useAuthStore.getState().setUser(crearUsuario({ name: 'Ada' }));
	return renderWithProviders(
		<MainNavbar>
			<p>Contenido de la página</p>
		</MainNavbar>,
		{ route: { pathname: '/proyecto' } },
	);
}

describe('MainNavbar (integración)', () => {
	it('carga los proyectos en la barra lateral y muestra el contenido', async () => {
		renderizar();

		expect(screen.getByText('Contenido de la página')).toBeInTheDocument();
		expect(await screen.findByTitle('tienda online')).toBeInTheDocument();
		expect(screen.getByTitle('gestor de tareas')).toBeInTheDocument();
	});

	it('arranca contraída y se expande mostrando nombres y usuario', async () => {
		const { user } = renderizar();
		await screen.findByTitle('tienda online');
		expect(screen.queryByText('Proyectos')).not.toBeInTheDocument();

		// El botón de expandir es el primero de la barra (solo contiene un ícono).
		const [expandir] = screen.getAllByRole('button');
		await user.click(expandir);

		expect(screen.getByText('Proyectos')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'KOSMO' })).toBeInTheDocument();
		expect(screen.getByRole('heading', { name: 'Ada' })).toBeInTheDocument();
	});

	it('abrir un proyecto lo selecciona y navega a Descubrimiento', async () => {
		const { user } = renderizar();

		await user.click(await screen.findByTitle('gestor de tareas'));

		expect(useProjectStore.getState().currentProject?.id).toBe('prj_b');
		expect(mockRouter.push).toHaveBeenCalledWith('/proyecto/descubrimiento');
	});

	it('Inicio lleva al listado de proyectos', async () => {
		const { user } = renderizar();

		await user.click(screen.getByTitle('Inicio'));

		expect(mockRouter.push).toHaveBeenCalledWith('/proyecto');
	});

	it('con cambios sin guardar, Inicio deja la navegación pendiente de confirmación', async () => {
		useAppStore.setState({ hasUnsavedChanges: true });
		const { user } = renderizar();

		await user.click(screen.getByTitle('Inicio'));

		expect(mockRouter.push).not.toHaveBeenCalled();
		expect(useAppStore.getState().pendingNavigationPath).toBe('/proyecto');
	});

	it('con el editor maximizado oculta la barra lateral y el wizard', async () => {
		useAppStore.setState({ isEditorMaximized: true });
		renderizar();

		await waitFor(() => expect(useProjectStore.getState().projects).toHaveLength(2));
		expect(screen.queryByTitle('Inicio')).not.toBeInTheDocument();
		expect(screen.getByText('Contenido de la página')).toBeInTheDocument();
	});
});
