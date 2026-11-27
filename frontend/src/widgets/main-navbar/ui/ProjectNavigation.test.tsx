import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Project } from '@/entities/project';
import { crearProyecto, renderWithProviders } from '@/test';
import { ProjectNavigation } from './ProjectNavigation';

function renderizar(isSidebarExpanded: boolean, currentProject: Project | null = null) {
	const projects = [
		crearProyecto({ id: 'prj_1', name: 'tienda online' }),
		crearProyecto({ id: 'prj_2', name: 'gestor de tareas' }),
	];
	const onHomeClick = vi.fn();
	const onProjectClick = vi.fn();
	const utils = renderWithProviders(
		<ProjectNavigation
			projects={projects}
			currentProject={currentProject ?? null}
			isSidebarExpanded={isSidebarExpanded}
			onHomeClick={onHomeClick}
			onProjectClick={onProjectClick}
		/>,
	);
	return { ...utils, projects, onHomeClick, onProjectClick };
}

describe('ProjectNavigation', () => {
	describe.each([
		['expandida', true],
		['contraída', false],
	])('barra %s', (_caso, expandida) => {
		it('lista un botón por proyecto además de Inicio', () => {
			renderizar(expandida);

			expect(screen.getByRole('button', { name: /Inicio/ })).toBeInTheDocument();
			expect(screen.getByTitle('tienda online')).toBeInTheDocument();
			expect(screen.getByTitle('gestor de tareas')).toBeInTheDocument();
		});

		it('notifica el proyecto elegido', async () => {
			const { user, projects, onProjectClick } = renderizar(expandida);

			await user.click(screen.getByTitle('gestor de tareas'));

			expect(onProjectClick).toHaveBeenCalledWith(projects[1]);
		});

		it('notifica el clic en Inicio', async () => {
			const { user, onHomeClick } = renderizar(expandida);

			await user.click(screen.getByTitle('Inicio'));

			expect(onHomeClick).toHaveBeenCalledOnce();
		});

		it('resalta el proyecto activo', () => {
			renderizar(expandida, crearProyecto({ id: 'prj_2' }));

			expect(screen.getByTitle('gestor de tareas')).toHaveClass('bg-neutral-700');
			expect(screen.getByTitle('tienda online')).not.toHaveClass('bg-neutral-700');
		});
	});

	it('expandida muestra el nombre completo y la sección Proyectos', () => {
		renderizar(true);

		expect(screen.getByText('Proyectos')).toBeInTheDocument();
		expect(screen.getByText('tienda online')).toBeInTheDocument();
	});

	it('contraída muestra solo las iniciales del proyecto', () => {
		renderizar(false);

		expect(screen.getByTitle('tienda online')).toHaveTextContent(/^TI$/);
		expect(screen.queryByText('Proyectos')).not.toBeInTheDocument();
	});
});
