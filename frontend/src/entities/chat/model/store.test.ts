import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
	listChatSessions: vi.fn(),
	createChatSession: vi.fn(),
	deleteChatSession: vi.fn(),
}));

vi.mock('../api/api', () => apiMocks);

import { sessionKey, useChatSessionsStore } from './store';

const sessionFixture = {
	id: 'cht_01',
	phase: 'requirements' as const,
	context_id: 'feat_01',
	created_at: '2026-08-14T10:00:00Z',
	message_count: 3,
	last_message_at: '2026-08-14T11:00:00Z',
	title: 'Revisar criterios de aceptación',
};

describe('chat sessions store', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		useChatSessionsStore.getState().reset();
	});

	it('sessionKey combina proyecto, fase y contexto', () => {
		expect(sessionKey('prj_01', 'requirements', 'feat_01')).toBe(
			'prj_01:requirements:feat_01',
		);
		expect(sessionKey('prj_01', 'discovery', null)).toBe('prj_01:discovery:');
	});

	it('listSessions guarda los hilos por clave', async () => {
		apiMocks.listChatSessions.mockResolvedValue([sessionFixture]);

		await useChatSessionsStore
			.getState()
			.listSessions('prj_01', 'requirements', 'feat_01');

		const key = sessionKey('prj_01', 'requirements', 'feat_01');
		expect(useChatSessionsStore.getState().sessions[key]).toHaveLength(1);
		expect(useChatSessionsStore.getState().loading).toBe(false);
	});

	it('createSession antepone el hilo nuevo y selecciona su id', async () => {
		apiMocks.createChatSession.mockResolvedValue({
			...sessionFixture,
			id: 'cht_02',
			session_id: 'cht_02',
			message_count: 0,
			last_message_at: null,
		});

		await useChatSessionsStore
			.getState()
			.createSession('prj_01', 'requirements', 'feat_01');

		const key = sessionKey('prj_01', 'requirements', 'feat_01');
		const sessions = useChatSessionsStore.getState().sessions[key];
		expect(sessions).toHaveLength(1);
		expect(sessions[0].id).toBe('cht_02');

		useChatSessionsStore.getState().setActiveSessionId(key, 'cht_02');
		expect(useChatSessionsStore.getState().activeSessionId[key]).toBe('cht_02');
	});

	it('reset limpia sesiones, selección y error', async () => {
		apiMocks.listChatSessions.mockRejectedValue(new Error('network'));
		await useChatSessionsStore
			.getState()
			.listSessions('prj_01', 'requirements', null)
			.catch(() => undefined);

		useChatSessionsStore.getState().reset();

		expect(useChatSessionsStore.getState().sessions).toEqual({});
		expect(useChatSessionsStore.getState().error).toBeNull();
	});

	it('deleteSession elimina el hilo de la lista y resetea la sesión activa', async () => {
		apiMocks.listChatSessions.mockResolvedValue([sessionFixture]);
		await useChatSessionsStore
			.getState()
			.listSessions('prj_01', 'requirements', 'feat_01');
		const key = sessionKey('prj_01', 'requirements', 'feat_01');
		useChatSessionsStore.getState().setActiveSessionId(key, 'cht_01');
		apiMocks.deleteChatSession.mockResolvedValue(undefined);

		await useChatSessionsStore
			.getState()
			.deleteSession('prj_01', 'requirements', 'feat_01', 'cht_01');

		expect(apiMocks.deleteChatSession).toHaveBeenCalledWith('prj_01', 'cht_01');
		expect(useChatSessionsStore.getState().sessions[key]).toHaveLength(0);
		expect(useChatSessionsStore.getState().activeSessionId[key]).toBeNull();
	});

	it('deleteSession conserva la sesión activa si elimina otra', async () => {
		apiMocks.listChatSessions.mockResolvedValue([
			sessionFixture,
			{ ...sessionFixture, id: 'cht_02', title: 'Otro chat' },
		]);
		await useChatSessionsStore
			.getState()
			.listSessions('prj_01', 'requirements', 'feat_01');
		const key = sessionKey('prj_01', 'requirements', 'feat_01');
		useChatSessionsStore.getState().setActiveSessionId(key, 'cht_02');
		apiMocks.deleteChatSession.mockResolvedValue(undefined);

		await useChatSessionsStore
			.getState()
			.deleteSession('prj_01', 'requirements', 'feat_01', 'cht_01');

		expect(useChatSessionsStore.getState().sessions[key]).toHaveLength(1);
		expect(useChatSessionsStore.getState().activeSessionId[key]).toBe('cht_02');
	});
});
