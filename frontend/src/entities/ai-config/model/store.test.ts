import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AIConfigView, AIProviderInfo, TestAIConnectionResult } from './types';

const apiMocks = vi.hoisted(() => ({
	getProviders: vi.fn(),
	getConfig: vi.fn(),
	saveConfig: vi.fn(),
	deleteConfig: vi.fn(),
	testConnection: vi.fn(),
}));

vi.mock('../api/api', () => ({
	aiConfigApi: apiMocks,
}));

import { useAiConfigStore } from './store';

const mockConfig: AIConfigView = {
	provider: 'openai',
	model: 'gpt-4o',
	is_custom: true,
	has_api_key: true,
	masked_key: '••••••••1234',
	updated_at: '2026-08-26T12:00:00Z',
};

const mockProviders: AIProviderInfo[] = [
	{
		value: 'openai',
		label: 'OpenAI',
		models: [{ id: 'gpt-4o', display_name: 'GPT-4o', tier: 'flagship' }],
	},
];

describe('useAiConfigStore', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		useAiConfigStore.setState({
			config: null,
			providers: [],
			loading: false,
			error: null,
			testResult: null,
			testLoading: false,
			testError: null,
		});
	});

	it('fetchConfig carga la configuración y actualiza el estado', async () => {
		apiMocks.getConfig.mockResolvedValue(mockConfig);

		await useAiConfigStore.getState().fetchConfig();

		expect(apiMocks.getConfig).toHaveBeenCalledTimes(1);
		expect(useAiConfigStore.getState().config).toEqual(mockConfig);
		expect(useAiConfigStore.getState().loading).toBe(false);
		expect(useAiConfigStore.getState().error).toBeNull();
	});

	it('fetchConfig maneja errores correctamente', async () => {
		apiMocks.getConfig.mockRejectedValue(new Error('Network error'));

		await useAiConfigStore.getState().fetchConfig();

		expect(useAiConfigStore.getState().config).toBeNull();
		expect(useAiConfigStore.getState().loading).toBe(false);
		expect(useAiConfigStore.getState().error).toBe('Network error');
	});

	it('fetchProviders carga el catálogo de proveedores', async () => {
		apiMocks.getProviders.mockResolvedValue(mockProviders);

		await useAiConfigStore.getState().fetchProviders();

		expect(apiMocks.getProviders).toHaveBeenCalledTimes(1);
		expect(useAiConfigStore.getState().providers).toEqual(mockProviders);
	});

	it('saveConfig guarda la configuración y actualiza el estado', async () => {
		apiMocks.saveConfig.mockResolvedValue(mockConfig);

		await useAiConfigStore.getState().saveConfig({
			provider: 'openai',
			model: 'gpt-4o',
			api_key: 'sk-test1234',
		});

		expect(apiMocks.saveConfig).toHaveBeenCalledWith({
			provider: 'openai',
			model: 'gpt-4o',
			api_key: 'sk-test1234',
		});
		expect(useAiConfigStore.getState().config).toEqual(mockConfig);
		expect(useAiConfigStore.getState().loading).toBe(false);
	});

	it('deleteConfig llama a la API y elimina la configuración activa', async () => {
		useAiConfigStore.setState({ config: mockConfig });
		apiMocks.deleteConfig.mockResolvedValue(undefined);

		await useAiConfigStore.getState().deleteConfig();

		expect(apiMocks.deleteConfig).toHaveBeenCalledTimes(1);
		expect(useAiConfigStore.getState().config).toEqual({
			provider: null,
			model: null,
			is_custom: false,
			has_api_key: false,
			masked_key: null,
			updated_at: null,
		});
		expect(useAiConfigStore.getState().loading).toBe(false);
		expect(useAiConfigStore.getState().error).toBeNull();
	});

	it('deleteConfig maneja errores y propaga la excepción', async () => {
		useAiConfigStore.setState({ config: mockConfig });
		apiMocks.deleteConfig.mockRejectedValue(new Error('Delete error'));

		await expect(useAiConfigStore.getState().deleteConfig()).rejects.toThrow('Delete error');
		expect(useAiConfigStore.getState().error).toBe('Delete error');
		expect(useAiConfigStore.getState().loading).toBe(false);
	});

	it('testConnection ejecuta la prueba de conectividad y actualiza testResult', async () => {
		const testResult: TestAIConnectionResult = {
			is_connected: true,
			detected_model: 'gpt-4o',
			message: 'Conexión exitosa',
		};
		apiMocks.testConnection.mockResolvedValue(testResult);

		await useAiConfigStore.getState().testConnection({
			provider: 'openai',
			model: 'gpt-4o',
			api_key: 'sk-test1234',
		});

		expect(apiMocks.testConnection).toHaveBeenCalledWith({
			provider: 'openai',
			model: 'gpt-4o',
			api_key: 'sk-test1234',
		});
		expect(useAiConfigStore.getState().testResult).toEqual(testResult);
		expect(useAiConfigStore.getState().testLoading).toBe(false);
	});

	it('clearTestResult limpia los resultados y errores de prueba', () => {
		useAiConfigStore.setState({
			testResult: { is_connected: true, detected_model: 'gpt-4o', message: 'OK' },
			testError: 'Error',
		});

		useAiConfigStore.getState().clearTestResult();

		expect(useAiConfigStore.getState().testResult).toBeNull();
		expect(useAiConfigStore.getState().testError).toBeNull();
	});
});
