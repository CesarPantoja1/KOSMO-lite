import { create } from 'zustand';
import { aiConfigApi } from '../api/api';
import type {
	AIConfigView,
	AIProviderInfo,
	SaveAIConfigRequest,
	TestAIConnectionRequest,
	TestAIConnectionResult,
} from './types';

export interface AiConfigState {
	config: AIConfigView | null;
	providers: AIProviderInfo[];
	loading: boolean;
	error: string | null;
	testResult: TestAIConnectionResult | null;
	testLoading: boolean;
	testError: string | null;
	fetchConfig: () => Promise<void>;
	fetchProviders: () => Promise<void>;
	saveConfig: (data: SaveAIConfigRequest) => Promise<void>;
	deleteConfig: () => Promise<void>;
	testConnection: (data: TestAIConnectionRequest) => Promise<void>;
	clearTestResult: () => void;
	getDefaultConfig: () => AIConfigView;
}

export const useAiConfigStore = create<AiConfigState>()((set) => ({
	config: null,
	providers: [],
	loading: false,
	error: null,
	testResult: null,
	testLoading: false,
	testError: null,

	fetchConfig: async () => {
		set({ loading: true, error: null });
		try {
			const config = await aiConfigApi.getConfig();
			set({ config, loading: false });
		} catch (err) {
			const message =
				err instanceof Error ? err.message : 'Error al cargar configuración de IA';
			set({ error: message, loading: false });
		}
	},

	fetchProviders: async () => {
		try {
			const providers = await aiConfigApi.getProviders();
			set({ providers });
		} catch {
			// El catálogo es best-effort; el form queda vacío si falla
		}
	},

	saveConfig: async (data: SaveAIConfigRequest) => {
		set({ loading: true, error: null });
		try {
			const config = await aiConfigApi.saveConfig(data);
			set({ config, loading: false });
		} catch (err) {
			const message =
				err instanceof Error ? err.message : 'Error al guardar configuración de IA';
			set({ error: message, loading: false });
			throw err;
		}
	},

	deleteConfig: async () => {
		set({ loading: true, error: null });
		try {
			await aiConfigApi.deleteConfig();
			set({
				config: {
					provider: null,
					model: null,
					is_custom: false,
					has_api_key: false,
					masked_key: null,
					updated_at: null,
				},
				loading: false,
			});
		} catch (err) {
			const message =
				err instanceof Error ? err.message : 'Error al eliminar configuración de IA';
			set({ error: message, loading: false });
			throw err;
		}
	},

	testConnection: async (data: TestAIConnectionRequest) => {
		set({ testLoading: true, testError: null, testResult: null });
		try {
			const result = await aiConfigApi.testConnection(data);
			set({ testResult: result, testLoading: false });
		} catch (err) {
			const message = err instanceof Error ? err.message : 'Error al probar conexión';
			set({ testError: message, testLoading: false });
			throw err;
		}
	},

	clearTestResult: () => {
		set({ testResult: null, testError: null });
	},

	getDefaultConfig: (): AIConfigView => ({
		provider: null,
		model: null,
		is_custom: false,
		has_api_key: false,
		masked_key: null,
		updated_at: null,
	}),
}));
