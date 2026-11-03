import { useConsistencyGateStore } from '@/entities/consistency';
import { clearDiscoveryStore } from '@/entities/discovery';
import { clearCharacteristicStore } from '@/entities/characteristic';
import { clearRequirementsStore } from '@/entities/requirements';
import { clearImplementationStore } from '@/entities/implementation';
import { useChatSessionsStore } from '@/entities/chat';
import { clearProjectStore } from '@/entities/project';
import { create } from 'zustand';
import { clearProjectStoreExceptProjects } from '@/entities/project';
import { initializeProject } from '@/features/initialize';

interface AppState {
	initialized: boolean;
	setInitialized: (v: boolean) => void;
	resetProjectState: () => void;
	resetStateBeforeChangeProject: () => void;
	hasUnsavedChanges: boolean;
	setHasUnsavedChanges: (v: boolean) => void;
	pendingNavigationPath: string | null;
	setPendingNavigationPath: (v: string | null) => void;
	isEditorMaximized: boolean;
	setEditorMaximized: (v: boolean) => void;
	initializeProject: (projectId: string) => Promise<void>;
}

export const useAppStore = create<AppState>()((set) => ({
	initialized: false,
	setInitialized: (v) => set({ initialized: v }),
	resetProjectState: () => {
		clearProjectStore();
		clearDiscoveryStore();
		clearCharacteristicStore();
		clearRequirementsStore();
		clearImplementationStore();
		useChatSessionsStore.getState().reset();
		useConsistencyGateStore.getState().reset();
		set({
			initialized: false,
			hasUnsavedChanges: false,
			pendingNavigationPath: null,
			isEditorMaximized: false,
		});
	},
	resetStateBeforeChangeProject: () => {
		clearProjectStoreExceptProjects();
		clearDiscoveryStore();
		clearCharacteristicStore();
		clearRequirementsStore();
		clearImplementationStore();
		useChatSessionsStore.getState().reset();
		useConsistencyGateStore.getState().reset();
		set({
			initialized: false,
			hasUnsavedChanges: false,
			pendingNavigationPath: null,
			isEditorMaximized: false,
		});
	},
	hasUnsavedChanges: false,
	setHasUnsavedChanges: (v) => set({ hasUnsavedChanges: v }),
	pendingNavigationPath: null,
	setPendingNavigationPath: (v) => set({ pendingNavigationPath: v }),
	isEditorMaximized: false,
	setEditorMaximized: (v) => set({ isEditorMaximized: v }),
	initializeProject: async (projectId) => {
		await initializeProject(projectId);
	},
}));

export const clearAppStore = () => {
	useAppStore.setState({
		initialized: false,
		hasUnsavedChanges: false,
		pendingNavigationPath: null,
		isEditorMaximized: false,
	});
};
