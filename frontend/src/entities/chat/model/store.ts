'use client';

import { useEffect } from 'react';
import { create } from 'zustand';
import { createChatSession, deleteChatSession, listChatSessions } from '../api/api';
import type {
	ChatPhase,
	ChatSessionSummary,
	CreateChatSessionResponse,
} from './types';

export const sessionKey = (
	projectId: string,
	phase: ChatPhase,
	contextId: string | null,
): string => `${projectId}:${phase}:${contextId ?? ''}`;

const EMPTY_SESSIONS: ChatSessionSummary[] = [];

interface ChatSessionsState {
	sessions: Record<string, ChatSessionSummary[]>;
	activeSessionId: Record<string, string | null>;
	loading: boolean;
	error: unknown;
	listSessions: (projectId: string, phase: ChatPhase, contextId: string | null) => Promise<void>;
	createSession: (
		projectId: string,
		phase: ChatPhase,
		contextId: string | null,
	) => Promise<CreateChatSessionResponse>;
	deleteSession: (
		projectId: string,
		phase: ChatPhase,
		contextId: string | null,
		sessionId: string,
	) => Promise<void>;
	setActiveSessionId: (key: string, sessionId: string | null) => void;
	reset: () => void;
}

export const useChatSessionsStore = create<ChatSessionsState>()((set) => ({
	sessions: {},
	activeSessionId: {},
	loading: false,
	error: null,

	listSessions: async (projectId, phase, contextId) => {
		const key = sessionKey(projectId, phase, contextId);
		set({ loading: true, error: null });
		try {
			const data = await listChatSessions(projectId, phase, contextId);
			set((state) => ({ sessions: { ...state.sessions, [key]: data }, loading: false }));
		} catch (error) {
			set({ loading: false, error });
		}
	},

	createSession: async (projectId, phase, contextId) => {
		const key = sessionKey(projectId, phase, contextId);
		const created = await createChatSession(projectId, phase, contextId);
		set((state) => ({
			sessions: { ...state.sessions, [key]: [created, ...(state.sessions[key] ?? [])] },
		}));
		return created;
	},

	deleteSession: async (projectId, phase, contextId, sessionId) => {
		const key = sessionKey(projectId, phase, contextId);
		await deleteChatSession(projectId, sessionId);
		set((state) => ({
			sessions: {
				...state.sessions,
				[key]: (state.sessions[key] ?? []).filter((s) => s.id !== sessionId),
			},
			activeSessionId: {
				...state.activeSessionId,
				[key]: state.activeSessionId[key] === sessionId ? null : state.activeSessionId[key],
			},
		}));
	},

	setActiveSessionId: (key, sessionId) =>
		set((state) => ({ activeSessionId: { ...state.activeSessionId, [key]: sessionId } })),

	reset: () => set({ sessions: {}, activeSessionId: {}, loading: false, error: null }),
}));

export function useChatSessions(
	projectId: string | null,
	phase: ChatPhase | null,
	contextId: string | null = null,
) {
	const key = projectId && phase ? sessionKey(projectId, phase, contextId) : null;

	const sessions = useChatSessionsStore((s) =>
		key ? (s.sessions[key] ?? EMPTY_SESSIONS) : EMPTY_SESSIONS,
	);
	const activeSessionId = useChatSessionsStore((s) =>
		key ? (s.activeSessionId[key] ?? null) : null,
	);
	const loading = useChatSessionsStore((s) => s.loading);
	const listSessions = useChatSessionsStore((s) => s.listSessions);
	const createSession = useChatSessionsStore((s) => s.createSession);
	const deleteSession = useChatSessionsStore((s) => s.deleteSession);
	const setActiveSessionId = useChatSessionsStore((s) => s.setActiveSessionId);

	useEffect(() => {
		if (!key || !projectId || !phase) return;
		const timer = window.setTimeout(() => {
			void listSessions(projectId, phase, contextId);
		}, 0);
		return () => window.clearTimeout(timer);
	}, [key, projectId, phase, contextId, listSessions]);

	return {
		sessions,
		activeSessionId,
		loading,
		selectSession: (sessionId: string | null) => {
			if (key) setActiveSessionId(key, sessionId);
		},
		createNewSession: async () => {
			if (!projectId || !phase) return null;
			const created = await createSession(projectId, phase, contextId);
			setActiveSessionId(sessionKey(projectId, phase, contextId), created.session_id);
			return created;
		},
		deleteSession: async (sessionId: string) => {
			if (!projectId || !phase) return;
			await deleteSession(projectId, phase, contextId, sessionId);
		},
		refresh: async () => {
			if (!projectId || !phase) return;
			await listSessions(projectId, phase, contextId);
		},
	};
}
