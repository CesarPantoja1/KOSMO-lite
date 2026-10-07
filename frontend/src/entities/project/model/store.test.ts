import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/api', () => ({
	getProjects: vi.fn(),
	getProject: vi.fn(),
	deleteProject: vi.fn(),
}));

import { getProjects, getProject, deleteProject } from '../api/api';
import { useProjectStore, clearProjectStore, clearProjectStoreExceptProjects } from './store';

const api = {
	getProjects: vi.mocked(getProjects),
	getProject: vi.mocked(getProject),
	deleteProject: vi.mocked(deleteProject),
};

describe('useProjectStore', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		clearProjectStore();
	});

	it('inicializa sin proyectos ni proyecto actual', () => {
		const state = useProjectStore.getState();
		expect(state.projects).toEqual([]);
		expect(state.currentProject).toBeNull();
		expect(state.isProyectosOpen).toBe(false);
	});

	it('getProjects guarda la lista en el store', async () => {
		// Arrange
		api.getProjects.mockResolvedValue([{ id: 'p1' } as never]);

		// Act
		const result = await useProjectStore.getState().getProjects();

		// Assert
		expect(result).toHaveLength(1);
		expect(useProjectStore.getState().projects).toHaveLength(1);
	});

	it('getProject guarda el proyecto actual', async () => {
		// Arrange
		api.getProject.mockResolvedValue({ id: 'p1', name: 'Proyecto' } as never);

		// Act
		await useProjectStore.getState().getProject('p1');

		// Assert
		expect(useProjectStore.getState().currentProject?.name).toBe('Proyecto');
	});

	it('deleteProject elimina el proyecto de la lista', async () => {
		// Arrange
		useProjectStore.getState().setProjects([
			{ id: 'p1' } as never,
			{ id: 'p2' } as never,
		]);
		api.deleteProject.mockResolvedValue(undefined);

		// Act
		await useProjectStore.getState().deleteProject('p1');

		// Assert
		expect(useProjectStore.getState().projects).toEqual([{ id: 'p2' }]);
	});

	it('deleteProject limpia currentProject si coincide con el proyecto eliminado', async () => {
		// Arrange
		useProjectStore.getState().setProjects([
			{ id: 'p1' } as never,
			{ id: 'p2' } as never,
		]);
		useProjectStore.getState().setCurrentProject({ id: 'p1' } as never);
		api.deleteProject.mockResolvedValue(undefined);

		// Act
		await useProjectStore.getState().deleteProject('p1');

		// Assert
		expect(useProjectStore.getState().projects).toEqual([{ id: 'p2' }]);
		expect(useProjectStore.getState().currentProject).toBeNull();
	});

	it('deleteProject preserva currentProject si no coincide con el proyecto eliminado', async () => {
		// Arrange
		useProjectStore.getState().setProjects([
			{ id: 'p1' } as never,
			{ id: 'p2' } as never,
		]);
		useProjectStore.getState().setCurrentProject({ id: 'p2' } as never);
		api.deleteProject.mockResolvedValue(undefined);

		// Act
		await useProjectStore.getState().deleteProject('p1');

		// Assert
		expect(useProjectStore.getState().projects).toEqual([{ id: 'p2' }]);
		expect(useProjectStore.getState().currentProject).toEqual({ id: 'p2' });
	});

	it('addProject agrega un proyecto a la lista', () => {
		// Act
		useProjectStore.getState().addProject({ id: 'p1' } as never);

		// Assert
		expect(useProjectStore.getState().projects).toEqual([{ id: 'p1' }]);
	});

	it('setCurrentProject actualiza el proyecto actual', () => {
		// Act
		useProjectStore.getState().setCurrentProject({ id: 'p1' } as never);

		// Assert
		expect(useProjectStore.getState().currentProject).toEqual({ id: 'p1' });
	});

	it('setProjectState actualiza el proyecto actual y abre el panel', () => {
		// Act
		useProjectStore.getState().setProjectState({ id: 'p1' } as never);

		// Assert
		expect(useProjectStore.getState().currentProject).toEqual({ id: 'p1' });
		expect(useProjectStore.getState().isProyectosOpen).toBe(true);
	});

	it('setIsProyectosOpen actualiza el flag del panel', () => {
		useProjectStore.getState().setIsProyectosOpen(true);
		expect(useProjectStore.getState().isProyectosOpen).toBe(true);
	});

	it('clearProjectStore limpia el storage persistido y todo el estado', () => {
		// Arrange
		useProjectStore.getState().setProjects([{ id: 'p1' } as never]);
		useProjectStore.getState().setCurrentProject({ id: 'p1' } as never);

		// Act
		clearProjectStore();

		// Assert
		const state = useProjectStore.getState();
		expect(state.projects).toEqual([]);
		expect(state.currentProject).toBeNull();
		expect(state.isProyectosOpen).toBe(false);
	});

	it('clearProjectStoreExceptProjects limpia todo excepto la lista de proyectos', () => {
		// Arrange
		useProjectStore.getState().setProjects([{ id: 'p1' } as never]);
		useProjectStore.getState().setCurrentProject({ id: 'p1' } as never);
		useProjectStore.getState().setIsProyectosOpen(true);

		// Act
		clearProjectStoreExceptProjects();

		// Assert
		const state = useProjectStore.getState();
		expect(state.projects).toEqual([{ id: 'p1' }]);
		expect(state.currentProject).toBeNull();
		expect(state.isProyectosOpen).toBe(false);
	});
});
