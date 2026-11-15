import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/api', () => ({
	getCharacteristics: vi.fn(),
	generateCharacteristics: vi.fn(),
	getSuggestCharacteristics: vi.fn(),
	addCharacteristic: vi.fn(),
	getChatHistory: vi.fn(),
}));

import {
	getCharacteristics,
	generateCharacteristics,
	getSuggestCharacteristics,
	addCharacteristic,
	getChatHistory,
} from '../api/api';
import { useCharacteristicStore, clearCharacteristicStore } from './store';

const api = {
	getCharacteristics: vi.mocked(getCharacteristics),
	generateCharacteristics: vi.mocked(generateCharacteristics),
	getSuggestCharacteristics: vi.mocked(getSuggestCharacteristics),
	addCharacteristic: vi.mocked(addCharacteristic),
	getChatHistory: vi.mocked(getChatHistory),
};

describe('useCharacteristicStore', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		clearCharacteristicStore();
		useCharacteristicStore.setState({ historyHasMore: false, historyCursor: null });
	});

	it('inicializa con listas vacías y sin selección', () => {
		const state = useCharacteristicStore.getState();
		expect(state.currentCharacteristics).toEqual([]);
		expect(state.currentSuggestions).toEqual([]);
		expect(state.selectedId).toBeNull();
	});

	it('getCharacteristics guarda el resultado en el store', async () => {
		// Arrange
		api.getCharacteristics.mockResolvedValue([
			{ id: 'f1', title: 'Login' } as never,
		]);

		// Act
		const result = await useCharacteristicStore.getState().getCharacteristics('prj_01');

		// Assert
		expect(result).toHaveLength(1);
		expect(useCharacteristicStore.getState().currentCharacteristics).toHaveLength(1);
	});

	it('generateCharacteristics reemplaza las características actuales', async () => {
		// Arrange
		api.generateCharacteristics.mockResolvedValue([
			{ id: 'f1', title: 'Generada' } as never,
		]);

		// Act
		await useCharacteristicStore.getState().generateCharacteristics('prj_01');

		// Assert
		expect(useCharacteristicStore.getState().currentCharacteristics).toEqual([
			{ id: 'f1', title: 'Generada' },
		]);
	});

	it('getSuggestCharacteristics guarda las sugerencias', async () => {
		// Arrange
		api.getSuggestCharacteristics.mockResolvedValue([
			{ number: 1, title: 'Sugerida', description: 'd', origin: '' },
		]);

		// Act
		await useCharacteristicStore.getState().getSuggestCharacteristics('prj_01');

		// Assert
		expect(useCharacteristicStore.getState().currentSuggestions).toHaveLength(1);
	});

	it('addCharacteristic agrega la nueva característica cuando is_saved=true', async () => {
		// Arrange
		api.addCharacteristic.mockResolvedValue({
			is_saved: true,
			feature: { id: 'f2', title: 'Nueva' } as never,
			origin: '',
			is_consistent: true,
		});

		// Act
		await useCharacteristicStore.getState().addCharacteristic('prj_01', {
			title: 'Nueva',
			description: 'desc',
		});

		// Assert
		expect(useCharacteristicStore.getState().currentCharacteristics).toEqual([
			{ id: 'f2', title: 'Nueva' },
		]);
	});

	it('addCharacteristic no agrega nada cuando is_saved=false', async () => {
		// Arrange
		api.addCharacteristic.mockResolvedValue({
			is_saved: false,
			feature: null as never,
			origin: '',
			is_consistent: false,
		});

		// Act
		await useCharacteristicStore.getState().addCharacteristic('prj_01', {
			title: 'X',
			description: 'Y',
		});

		// Assert
		expect(useCharacteristicStore.getState().currentCharacteristics).toEqual([]);
	});

	it('appendUserMessage y appendAssistantMessage agregan mensajes locales', () => {
		// Act
		useCharacteristicStore.getState().appendUserMessage('feat_01', 'Pregunta');
		useCharacteristicStore.getState().appendAssistantMessage('feat_01', {
			id: 'm2',
			role: 'assistant',
			content: 'Respuesta local',
		} as never);

		// Assert
		const history = useCharacteristicStore.getState().chatHistories['feat_01'];
		expect(history).toHaveLength(2);
		expect(history[1].content).toBe('Respuesta local');
	});

	it('loadChatHistory reemplaza el historial y guarda cursor/hasMore', async () => {
		// Arrange
		api.getChatHistory.mockResolvedValue({
			phase: 'features',
			context: 'feat_01',
			messages: [{ id: 'm1', role: 'user', content: 'a' } as never],
			has_more: true,
			next_cursor: 'cur_1',
		});

		// Act
		const messages = await useCharacteristicStore.getState().loadChatHistory('feat_01');

		// Assert
		expect(messages).toHaveLength(1);
		expect(useCharacteristicStore.getState().historyHasMore).toBe(true);
		expect(useCharacteristicStore.getState().historyCursor).toBe('cur_1');
	});

	it('loadOlderChatHistory no hace nada si no hay historyCursor', async () => {
		// Act
		await useCharacteristicStore.getState().loadOlderChatHistory('feat_01');

		// Assert
		expect(api.getChatHistory).not.toHaveBeenCalled();
	});

	it('loadOlderChatHistory antepone mensajes más antiguos', async () => {
		// Arrange
		api.getChatHistory
			.mockResolvedValueOnce({
				phase: 'features',
				context: 'feat_01',
				messages: [{ id: 'recent', role: 'user', content: 'reciente' } as never],
				has_more: true,
				next_cursor: 'cur_1',
			})
			.mockResolvedValueOnce({
				phase: 'features',
				context: 'feat_01',
				messages: [{ id: 'old', role: 'user', content: 'antiguo' } as never],
				has_more: false,
				next_cursor: null,
			});
		await useCharacteristicStore.getState().loadChatHistory('feat_01');

		// Act
		await useCharacteristicStore.getState().loadOlderChatHistory('feat_01');

		// Assert
		const history = useCharacteristicStore.getState().chatHistories['feat_01'];
		expect(history[0].id).toBe('old');
		expect(history[1].id).toBe('recent');
		expect(useCharacteristicStore.getState().historyHasMore).toBe(false);
	});

	it('clearChatHistory vacía el historial de una característica', () => {
		// Arrange
		useCharacteristicStore.getState().appendUserMessage('feat_01', 'msg');

		// Act
		useCharacteristicStore.getState().clearChatHistory('feat_01');

		// Assert
		expect(useCharacteristicStore.getState().chatHistories['feat_01']).toEqual([]);
	});

	it('clearAllChatHistories vacía todos los historiales', () => {
		// Arrange
		useCharacteristicStore.getState().appendUserMessage('feat_01', 'msg');
		useCharacteristicStore.getState().appendUserMessage('feat_02', 'msg2');

		// Act
		useCharacteristicStore.getState().clearAllChatHistories();

		// Assert
		expect(useCharacteristicStore.getState().chatHistories).toEqual({});
	});

	it('setSelectedId actualiza la selección', () => {
		useCharacteristicStore.getState().setSelectedId('f1');
		expect(useCharacteristicStore.getState().selectedId).toBe('f1');
	});

	it('clearCharacteristics resetea listas y selección', () => {
		// Arrange
		useCharacteristicStore.getState().setCurrentCharacteristics([{ id: 'f1' } as never]);
		useCharacteristicStore.getState().setCurrentSuggestions([{ number: 1 } as never]);
		useCharacteristicStore.getState().setSelectedId('f1');

		// Act
		useCharacteristicStore.getState().clearCharacteristics();

		// Assert
		const state = useCharacteristicStore.getState();
		expect(state.currentCharacteristics).toEqual([]);
		expect(state.currentSuggestions).toEqual([]);
		expect(state.selectedId).toBeNull();
	});

	it('clearCharacteristicStore limpia el storage persistido y el estado', () => {
		// Arrange
		useCharacteristicStore.getState().setCurrentCharacteristics([{ id: 'f1' } as never]);

		// Act
		clearCharacteristicStore();

		// Assert
		expect(useCharacteristicStore.getState().currentCharacteristics).toEqual([]);
	});
});
