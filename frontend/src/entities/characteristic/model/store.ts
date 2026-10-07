import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
	addCharacteristic,
	generateCharacteristics,
	getCharacteristics,
	getChatHistory,
	getSuggestCharacteristics,
	sendChatMessage,
} from '../api/api';
import type {
	CharacteristicResponse,
	CreateCharacteristicResponse,
	SuggestCharacteristic,
} from './types';
import { appendMessage, createUserMessage } from '@/shared/model/chat-message';
import type { ChatMessage, ChatResponse } from '@/shared/model/chat-message';

interface CharacteristicStore {
	currentCharacteristics: CharacteristicResponse[];
	chatHistories: Record<string, ChatMessage[]>;
	setCurrentCharacteristics: (characteristics: CharacteristicResponse[]) => void;
	currentSuggestions: SuggestCharacteristic[];
	setCurrentSuggestions: (suggestions: SuggestCharacteristic[]) => void;
	clearCharacteristics: () => void;
	clearChatHistory: (featureId: string) => void;
	clearAllChatHistories: () => void;
	getCharacteristics: (projectId: string) => Promise<CharacteristicResponse[]>;
	generateCharacteristics: (projectId: string) => Promise<CharacteristicResponse[]>;
	getSuggestCharacteristics: (projectId: string) => Promise<SuggestCharacteristic[]>;
	addCharacteristic: (
		projectId: string,
		item: { title: string; description: string; origin?: string },
	) => Promise<CreateCharacteristicResponse>;

	sendChatMessage: (featureId: string, content: string) => Promise<ChatResponse>;
	loadChatHistory: (
		featureId: string,
		sessionId?: string | null,
	) => Promise<ChatMessage[]>;
	historyHasMore: boolean;
	historyCursor: string | null;
	loadOlderChatHistory: (
		featureId: string,
		sessionId?: string | null,
	) => Promise<void>;
	appendUserMessage: (featureId: string, content: string) => void;
	appendAssistantMessage: (featureId: string, message: ChatMessage) => void;

	selectedId: string | null;
	setSelectedId: (id: string | null) => void;
}

export const useCharacteristicStore = create<CharacteristicStore>()(
	persist(
		(set, get) => ({
			currentCharacteristics: [],
			setCurrentCharacteristics: (characteristics) =>
				set({ currentCharacteristics: characteristics }),
			currentSuggestions: [],
			setCurrentSuggestions: (suggestions) => set({ currentSuggestions: suggestions }),
			clearCharacteristics: () =>
				set({ currentCharacteristics: [], currentSuggestions: [], selectedId: null }),

			chatHistories: {},
			historyHasMore: false,
			historyCursor: null,
			clearChatHistory: (featureId) => {
				const { chatHistories } = get();
				set({ chatHistories: { ...chatHistories, [featureId]: [] } });
			},
			clearAllChatHistories: () => set({ chatHistories: {} }),

			getCharacteristics: async (projectId) => {
				const data = await getCharacteristics(projectId);
				set({ currentCharacteristics: data });
				return data;
			},

			generateCharacteristics: async (projectId) => {
				const data = await generateCharacteristics(projectId);
				set({ currentCharacteristics: data });
				return data;
			},

			getSuggestCharacteristics: async (projectId) => {
				const data = await getSuggestCharacteristics(projectId);
				set({ currentSuggestions: data });
				return data;
			},

			addCharacteristic: async (projectId, item) => {
				const data = await addCharacteristic(projectId, item);
				const feat = data.feature;
				if (data.is_saved && feat) {
					set((state) => ({
						currentCharacteristics: [...state.currentCharacteristics, feat],
					}));
				}
				return data;
			},

			sendChatMessage: async (featureId, content) => {
				const userMessage = createUserMessage(content);

				const current = get().chatHistories[featureId] ?? [];
				set({
					chatHistories: {
						...get().chatHistories,
						[featureId]: appendMessage(current, userMessage),
					},
				});

				const response = await sendChatMessage(featureId, content);

				const afterUser = get().chatHistories[featureId] ?? [];
				set({
					chatHistories: {
						...get().chatHistories,
						[featureId]: appendMessage(afterUser, response.message),
					},
				});

				return response;
			},

			appendUserMessage: (featureId, content) => {
				const current = get().chatHistories[featureId] ?? [];
				set({
					chatHistories: {
						...get().chatHistories,
						[featureId]: appendMessage(current, createUserMessage(content)),
					},
				});
			},

			appendAssistantMessage: (featureId, message) => {
				const current = get().chatHistories[featureId] ?? [];
				set({
					chatHistories: {
						...get().chatHistories,
						[featureId]: appendMessage(current, message),
					},
				});
			},

			loadChatHistory: async (featureId, sessionId = null) => {
				const history = await getChatHistory(featureId, sessionId);
				set((state) => ({
					chatHistories: {
						...state.chatHistories,
						[featureId]: history.messages ?? [],
					},
					historyHasMore: history.has_more,
					historyCursor: history.next_cursor,
				}));
				return history.messages ?? [];
			},

			loadOlderChatHistory: async (featureId, sessionId = null) => {
				const { historyCursor, chatHistories } = get();
				if (!historyCursor) return;
				const history = await getChatHistory(featureId, sessionId, historyCursor);
				set((state) => ({
					chatHistories: {
						...state.chatHistories,
						[featureId]: [
							...(history.messages ?? []),
							...(chatHistories[featureId] ?? []),
						],
					},
					historyHasMore: history.has_more,
					historyCursor: history.next_cursor,
				}));
			},

			selectedId: null,
			setSelectedId: (id) => set({ selectedId: id }),
		}),
		{
			name: 'kosmo-characteristic-store',
			version: 2,
			partialize: (state) => ({
				selectedId: state.selectedId,
			}),
			migrate: () => ({
				currentCharacteristics: [],
				currentSuggestions: [],
				chatHistories: {},
				selectedId: null,
			}),
		},
	),
);

export const clearCharacteristicStore = () => {
	useCharacteristicStore.persist.clearStorage();
	useCharacteristicStore.setState({
		currentCharacteristics: [],
		currentSuggestions: [],
		chatHistories: {},
		selectedId: null,
	});
};
