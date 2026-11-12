import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/api', () => ({
	getDiscovery: vi.fn(),
	saveDiscovery: vi.fn(),
	generateDiscovery: vi.fn(),
	sendChatMessage: vi.fn(),
	getChatHistory: vi.fn(),
}));

import {
	getDiscovery,
	saveDiscovery,
	generateDiscovery,
	sendChatMessage,
	getChatHistory,
} from '../api/api';
import { useDiscoveryStore, clearDiscoveryStore } from './store';

const api = {
	getDiscovery: vi.mocked(getDiscovery),
	saveDiscovery: vi.mocked(saveDiscovery),
	generateDiscovery: vi.mocked(generateDiscovery),
	sendChatMessage: vi.mocked(sendChatMessage),
	getChatHistory: vi.mocked(getChatHistory),
};

describe('useDiscoveryStore', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		clearDiscoveryStore();
		useDiscoveryStore.setState({ historyHasMore: false, historyCursor: null });
	});

	it('inicializa sin descubrimiento actual ni historial', () => {
		const state = useDiscoveryStore.getState();
		expect(state.currentDiscovery).toBeNull();
		expect(state.chatHistory).toEqual([]);
	});

	it('getDiscovery guarda el resultado en el store', async () => {
		// Arrange
		api.getDiscovery.mockResolvedValue({ id: 'd1', project_id: 'prj_01', content: 'x' });

		// Act
		const result = await useDiscoveryStore.getState().getDiscovery('prj_01');

		// Assert
		expect(result.content).toBe('x');
		expect(useDiscoveryStore.getState().currentDiscovery).toEqual(result);
	});

	it('saveDiscovery actualiza el descubrimiento actual', async () => {
		// Arrange
		api.saveDiscovery.mockResolvedValue({
			id: 'd1',
			project_id: 'prj_01',
			content: 'guardado',
		});

		// Act
		await useDiscoveryStore.getState().saveDiscovery('prj_01', 'guardado');

		// Assert
		expect(useDiscoveryStore.getState().currentDiscovery?.content).toBe('guardado');
	});

	it('generateDiscovery actualiza el descubrimiento actual', async () => {
		// Arrange
		api.generateDiscovery.mockResolvedValue({
			id: 'd1',
			project_id: 'prj_01',
			content: 'generado',
		});

		// Act
		await useDiscoveryStore.getState().generateDiscovery('prj_01');

		// Assert
		expect(useDiscoveryStore.getState().currentDiscovery?.content).toBe('generado');
	});

	it('sendChatMessage agrega el mensaje del usuario y luego la respuesta', async () => {
		// Arrange
		api.sendChatMessage.mockResolvedValue({
			message: { id: 'm1', role: 'assistant', content: 'Respuesta' } as never,
			modification: null,
			redirect: null,
			consistency: null,
		});

		// Act
		await useDiscoveryStore.getState().sendChatMessage('prj_01', 'Hola');

		// Assert
		const history = useDiscoveryStore.getState().chatHistory;
		expect(history).toHaveLength(2);
		expect(history[0].role).toBe('user');
		expect(history[1].content).toBe('Respuesta');
	});

	it('appendUserMessage y appendAssistantMessage agregan mensajes locales', () => {
		// Act
		useDiscoveryStore.getState().appendUserMessage('Pregunta');
		useDiscoveryStore.getState().appendAssistantMessage({
			id: 'm2',
			role: 'assistant',
			content: 'Respuesta local',
		} as never);

		// Assert
		const history = useDiscoveryStore.getState().chatHistory;
		expect(history).toHaveLength(2);
		expect(history[1].content).toBe('Respuesta local');
	});

	it('loadChatHistory reemplaza el historial y guarda cursor/hasMore', async () => {
		// Arrange
		api.getChatHistory.mockResolvedValue({
			phase: 'discovery',
			context: 'prj_01',
			messages: [{ id: 'm1', role: 'user', content: 'a' } as never],
			has_more: true,
			next_cursor: 'cur_1',
		});

		// Act
		const messages = await useDiscoveryStore.getState().loadChatHistory('prj_01');

		// Assert
		expect(messages).toHaveLength(1);
		expect(useDiscoveryStore.getState().historyHasMore).toBe(true);
		expect(useDiscoveryStore.getState().historyCursor).toBe('cur_1');
	});

	it('loadOlderChatHistory no hace nada si no hay historyCursor', async () => {
		// Act
		await useDiscoveryStore.getState().loadOlderChatHistory('prj_01');

		// Assert
		expect(api.getChatHistory).not.toHaveBeenCalled();
	});

	it('loadOlderChatHistory antepone mensajes más antiguos', async () => {
		// Arrange
		api.getChatHistory
			.mockResolvedValueOnce({
				phase: 'discovery',
				context: 'prj_01',
				messages: [{ id: 'recent', role: 'user', content: 'reciente' } as never],
				has_more: true,
				next_cursor: 'cur_1',
			})
			.mockResolvedValueOnce({
				phase: 'discovery',
				context: 'prj_01',
				messages: [{ id: 'old', role: 'user', content: 'antiguo' } as never],
				has_more: false,
				next_cursor: null,
			});
		await useDiscoveryStore.getState().loadChatHistory('prj_01');

		// Act
		await useDiscoveryStore.getState().loadOlderChatHistory('prj_01');

		// Assert
		const history = useDiscoveryStore.getState().chatHistory;
		expect(history[0].id).toBe('old');
		expect(history[1].id).toBe('recent');
		expect(useDiscoveryStore.getState().historyHasMore).toBe(false);
	});

	it('clearChatHistory vacía el historial y el cursor', () => {
		// Arrange
		useDiscoveryStore.getState().appendUserMessage('msg');
		useDiscoveryStore.setState({ historyHasMore: true, historyCursor: 'cur_1' });

		// Act
		useDiscoveryStore.getState().clearChatHistory();

		// Assert
		const state = useDiscoveryStore.getState();
		expect(state.chatHistory).toEqual([]);
		expect(state.historyHasMore).toBe(false);
		expect(state.historyCursor).toBeNull();
	});

	it('clearDiscovery limpia solo el descubrimiento actual', () => {
		// Arrange
		useDiscoveryStore.setState({
			currentDiscovery: { id: 'd1', project_id: 'p', content: 'x' },
		});

		// Act
		useDiscoveryStore.getState().clearDiscovery();

		// Assert
		expect(useDiscoveryStore.getState().currentDiscovery).toBeNull();
	});

	it('resetDiscovery limpia descubrimiento e historial completos', () => {
		// Arrange
		useDiscoveryStore.setState({
			currentDiscovery: { id: 'd1', project_id: 'p', content: 'x' },
			chatHistory: [{ id: 'm1', role: 'user', content: 'a' } as never],
			historyHasMore: true,
			historyCursor: 'cur_1',
		});

		// Act
		useDiscoveryStore.getState().resetDiscovery();

		// Assert
		const state = useDiscoveryStore.getState();
		expect(state.currentDiscovery).toBeNull();
		expect(state.chatHistory).toEqual([]);
		expect(state.historyHasMore).toBe(false);
		expect(state.historyCursor).toBeNull();
	});

	it('clearDiscoveryStore limpia el storage persistido y el estado', () => {
		// Arrange
		useDiscoveryStore.setState({
			currentDiscovery: { id: 'd1', project_id: 'p', content: 'x' },
		});

		// Act
		clearDiscoveryStore();

		// Assert
		expect(useDiscoveryStore.getState().currentDiscovery).toBeNull();
	});
});
