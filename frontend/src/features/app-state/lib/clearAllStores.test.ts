import { describe, expect, it } from 'vitest';
import { useCharacteristicStore } from '@/entities/characteristic';
import { useChatSessionsStore } from '@/entities/chat';
import { useConsistencyGateStore } from '@/entities/consistency';
import { useDiscoveryStore } from '@/entities/discovery';
import { useImplementationStore } from '@/entities/implementation';
import { useProjectStore } from '@/entities/project';
import { useRequirementsStore } from '@/entities/requirements';
import { useAuthStore } from '@/shared/model/auth-store';
import { crearCaracteristica, crearProyecto, crearUsuario } from '@/test';
import { useAppStore } from '../model/app.store';
import { clearAllStores } from './clearAllStores';

const CLAVES_PERSISTIDAS = [
	'kosmo-auth-store',
	'kosmo-project-store',
	'kosmo-discovery-store',
	'kosmo-characteristic-store',
	'kosmo-requirements-store',
	'kosmo-implementation-store',
];

/** Simula una sesión de trabajo con datos en todos los stores. */
function poblarStores() {
	useAuthStore.getState().setTokens('access', 'refresh');
	useAuthStore.getState().setUser(crearUsuario());

	const proyecto = crearProyecto();
	useProjectStore.setState({
		projects: [proyecto],
		currentProject: proyecto,
		isProyectosOpen: true,
	});
	useCharacteristicStore.setState({
		currentCharacteristics: [crearCaracteristica()],
		selectedId: 'feat_1',
	});
	useRequirementsStore.setState({ hasRequirements: { feat_1: true } });
	useDiscoveryStore.setState({
		chatHistory: [{ role: 'user', content: 'hola' }] as never,
	});
	useImplementationStore.setState({ status: 'running' as never, logs: ['log'] as never });
	useChatSessionsStore.setState({ loading: true, error: 'fallo' as never });
	useConsistencyGateStore.setState({
		reviewLoading: true,
		actionByEvaluation: { ev1: true },
	});
	useAppStore.setState({
		initialized: true,
		hasUnsavedChanges: true,
		pendingNavigationPath: '/x',
	});
}

describe('clearAllStores', () => {
	it('reinicia el estado de sesión y de todas las entidades', () => {
		poblarStores();

		clearAllStores();

		expect(useAuthStore.getState()).toMatchObject({
			accessToken: null,
			refreshToken: null,
			user: null,
		});
		expect(useProjectStore.getState()).toMatchObject({
			projects: [],
			currentProject: null,
			isProyectosOpen: false,
		});
		expect(useCharacteristicStore.getState()).toMatchObject({
			currentCharacteristics: [],
			selectedId: null,
		});
		expect(useRequirementsStore.getState().hasRequirements).toEqual({});
		expect(useDiscoveryStore.getState().chatHistory).toEqual([]);
		expect(useImplementationStore.getState()).toMatchObject({ status: 'idle', logs: [] });
		expect(useChatSessionsStore.getState()).toMatchObject({
			loading: false,
			error: null,
		});
		expect(useConsistencyGateStore.getState()).toMatchObject({
			reviewLoading: false,
			actionByEvaluation: {},
		});
		expect(useAppStore.getState()).toMatchObject({
			initialized: false,
			hasUnsavedChanges: false,
			pendingNavigationPath: null,
		});
	});

	it('elimina los datos sensibles persistidos en localStorage', () => {
		poblarStores();

		clearAllStores();

		CLAVES_PERSISTIDAS.forEach((clave) => {
			const persistido = localStorage.getItem(clave);
			// Persist puede reescribir el estado vacío; lo importante es que no queden los valores de la sesión.
			expect(persistido ?? '').not.toContain('"access"');
			expect(persistido ?? '').not.toContain('"refresh"');
			expect(persistido ?? '').not.toContain('"prj_1"');
		});
	});

	it('es seguro llamarlo sin datos previos', () => {
		expect(() => clearAllStores()).not.toThrow();
	});
});
