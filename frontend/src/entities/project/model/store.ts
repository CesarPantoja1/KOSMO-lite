import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Project } from './types';
import { getProjects, getProject, deleteProject } from '../api/api';

interface ProjectStore {
	projects: Project[];
	setProjects: (projects: Project[]) => void;
	addProject: (project: Project) => void;
	deleteProject: (id: string) => Promise<void>;
	currentProject: Project | null;
	setCurrentProject: (project: Project) => void;
	setProjectState: (project: Project) => void;
	isProyectosOpen: boolean;
	setIsProyectosOpen: (v: boolean) => void;
	githubSyncingProjectId: string | null;
	setGithubSyncing: (id: string | null, isSyncing: boolean) => void;
	getProjects: () => Promise<Project[]>;
	getProject: (id: string) => Promise<Project>;
}

export const useProjectStore = create<ProjectStore>()(
	persist(
		(set) => ({
			projects: [],
			setProjects: (projects) => set({ projects }),
			addProject: (project) =>
				set((state) => ({ projects: [...state.projects, project] })),
			deleteProject: async (id) => {
				await deleteProject(id);
				set((state) => ({
					projects: state.projects.filter((p) => p.id !== id),
					currentProject: state.currentProject?.id === id ? null : state.currentProject,
				}));
			},
			currentProject: null,
			setCurrentProject: (project) => set({ currentProject: project }),
			setProjectState: (project) =>
				set({ currentProject: project, isProyectosOpen: true }),
			isProyectosOpen: false,
			setIsProyectosOpen: (v) => set({ isProyectosOpen: v }),
			githubSyncingProjectId: null,
			setGithubSyncing: (id, isSyncing) =>
				set({ githubSyncingProjectId: isSyncing ? id : null }),

			getProjects: async () => {
				const data = await getProjects();
				set({ projects: data });
				return data;
			},

			getProject: async (id) => {
				const data = await getProject(id);
				set({ currentProject: data });
				return data;
			},
		}),
		{
			name: 'kosmo-project-store',
			partialize: (state) => ({
				currentProject: state.currentProject,
				isProyectosOpen: state.isProyectosOpen,
				githubSyncingProjectId: state.githubSyncingProjectId,
			}),
		},
	),
);

export const clearProjectStore = () => {
	useProjectStore.persist.clearStorage();
	useProjectStore.setState({
		projects: [],
		currentProject: null,
		isProyectosOpen: false,
		githubSyncingProjectId: null,
	});
};

export const clearProjectStoreExceptProjects = () => {
	useProjectStore.setState({
		currentProject: null,
		isProyectosOpen: false,
	});
};
