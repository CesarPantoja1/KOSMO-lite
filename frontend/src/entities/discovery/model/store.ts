import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
	generateDiscovery,
	getChatHistory,
	getDiscovery,
	saveDiscovery,
	sendChatMessage as sendChatMessageApi,
} from '../api/api';
import type { DiscoveryResponse } from './types';
import { appendMessage, createUserMessage } from '@/shared/model/chat-message';
import type { ChatMessage, ChatResponse } from '@/shared/model/chat-message';

interface DiscoveryStore {
	currentDiscovery: DiscoveryResponse | null;
	chatHistory: ChatMessage[];
	setCurrentDiscovery: (discovery: DiscoveryResponse) => void;
	clearDiscovery: () => void;
	clearChatHistory: () => void;
	resetDiscovery: () => void;
	getDiscovery: (projectId: string) => Promise<DiscoveryResponse>;
	saveDiscovery: (projectId: string, content: string) => Promise<DiscoveryResponse>;
	generateDiscovery: (projectId: string) => Promise<DiscoveryResponse>;
	sendChatMessage: (projectId: string, content: string) => Promise<ChatResponse>;
	loadChatHistory: (
		projectId: string,
		sessionId?: string | null,
	) => Promise<ChatMessage[]>;
	historyHasMore: boolean;
	historyCursor: string | null;
	loadOlderChatHistory: (projectId: string, sessionId?: string | null) => Promise<void>;
	appendUserMessage: (content: string) => void;
	appendAssistantMessage: (message: ChatMessage) => void;
}

export const useDiscoveryStore = create<DiscoveryStore>()(
	persist(
		(set, get) => ({
			currentDiscovery: null,
			chatHistory: [],
			historyHasMore: false,
			historyCursor: null,

			setCurrentDiscovery: (discovery) => set({ currentDiscovery: discovery }),
			clearDiscovery: () => set({ currentDiscovery: null }),
			clearChatHistory: () =>
				set({ chatHistory: [], historyHasMore: false, historyCursor: null }),
			resetDiscovery: () =>
				set({
					currentDiscovery: null,
					chatHistory: [],
					historyHasMore: false,
					historyCursor: null,
				}),

			getDiscovery: async (projectId) => {
				const data = await getDiscovery(projectId);
				set({ currentDiscovery: data });
				return data;
			},

			saveDiscovery: async (projectId, content) => {
				const data = await saveDiscovery(projectId, content);
				set({ currentDiscovery: data });
				return data;
			},

			generateDiscovery: async (projectId) => {
				const data = await generateDiscovery(projectId);
				set({ currentDiscovery: data });
				return data;
			},

			sendChatMessage: async (projectId, content) => {
				const userMessage = createUserMessage(content);
				set((state) => ({ chatHistory: appendMessage(state.chatHistory, userMessage) }));

				const response = await sendChatMessageApi(projectId, content);
				set((state) => ({
					chatHistory: appendMessage(state.chatHistory, response.message),
				}));
				return response;
			},

			appendUserMessage: (content) =>
				set((state) => ({
					chatHistory: appendMessage(state.chatHistory, createUserMessage(content)),
				})),

			appendAssistantMessage: (message) =>
				set((state) => ({ chatHistory: appendMessage(state.chatHistory, message) })),

			loadChatHistory: async (projectId, sessionId = null) => {
				const history = await getChatHistory(projectId, sessionId);
				set({
					chatHistory: history.messages ?? [],
					historyHasMore: history.has_more,
					historyCursor: history.next_cursor,
				});
				return history.messages ?? [];
			},

			loadOlderChatHistory: async (projectId, sessionId = null) => {
				const { historyCursor, chatHistory } = get();
				if (!historyCursor) return;
				const history = await getChatHistory(projectId, sessionId, historyCursor);
				set({
					chatHistory: [...(history.messages ?? []), ...chatHistory],
					historyHasMore: history.has_more,
					historyCursor: history.next_cursor,
				});
			},
		}),
		{
			name: 'kosmo-discovery-store',
			partialize: (state) => ({
				currentDiscovery: state.currentDiscovery,
				chatHistory: state.chatHistory,
			}),
		},
	),
);

export const clearDiscoveryStore = () => {
	useDiscoveryStore.persist.clearStorage();
	useDiscoveryStore.setState({ currentDiscovery: null, chatHistory: [] });
};
