import type { ChatHistory } from '@/shared/model/chat-message';
import { apiClient } from '@/shared/api';
import { USE_MOCKS } from '@/shared/api/config';
import type { DiscoveryResponse } from '../model/types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// --- Mock state ---

let mockContent =
	'## Visión del producto\n\nEste es un descubrimiento de prueba en modo mock.';

// --- Mock implementations ---

const mockGetDiscovery = async (projectId: string): Promise<DiscoveryResponse> => {
	await delay(5000);
	return {
		id: 'mock-discovery-1',
		project_id: projectId,
		content: mockContent,
	};
};

const mockSaveDiscovery = async (
	projectId: string,
	content: string,
): Promise<DiscoveryResponse> => {
	await delay(500);
	// mockContent = content;
	return {
		id: 'mock-discovery-1',
		project_id: projectId,
		content,
	};
};

const mockGenerateDiscovery = async (projectId: string): Promise<DiscoveryResponse> => {
	await delay(2000);
	mockContent = '## Visión del producto\n\nDescubrimiento generado en modo mock.';
	return {
		id: 'mock-discovery-1',
		project_id: projectId,
		content: mockContent,
	};
};

const mockGetChatHistory = async (projectId: string): Promise<ChatHistory> => {
	await delay(300);
	return {
		phase: 'discovery',
		context: projectId,
		messages: [],
		has_more: false,
		next_cursor: null,
	};
};

// --- Real implementations ---

const realGetDiscovery = (projectId: string) => {
	return apiClient<DiscoveryResponse>(
		`/api/v1/projects/${projectId}/discovery?_t=${Date.now()}`,
		{
			method: 'GET',
		},
	);
};

const realSaveDiscovery = (projectId: string, content: string) => {
	return apiClient<DiscoveryResponse>(`/api/v1/projects/${projectId}/discovery`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ content }),
	});
};

const realGenerateDiscovery = (projectId: string) => {
	return apiClient<DiscoveryResponse>(`/api/v1/projects/${projectId}/discovery`, {
		method: 'POST',
	});
};

const realGetChatHistory = (
	projectId: string,
	sessionId: string | null,
	before?: string | null,
) => {
	const query = new URLSearchParams();
	if (sessionId) query.set('session_id', sessionId);
	if (before) query.set('before', before);
	const suffix = query.toString() ? `?${query.toString()}` : '';
	return apiClient<ChatHistory>(`/api/v1/projects/${projectId}/discovery/chat${suffix}`, {
		method: 'GET',
	});
};

// --- Exports (switch based on USE_MOCKS) ---

export const getDiscovery = (projectId: string): Promise<DiscoveryResponse> =>
	USE_MOCKS ? mockGetDiscovery(projectId) : realGetDiscovery(projectId);

export const saveDiscovery = (
	projectId: string,
	content: string,
): Promise<DiscoveryResponse> =>
	USE_MOCKS
		? mockSaveDiscovery(projectId, content)
		: realSaveDiscovery(projectId, content);

export const generateDiscovery = (projectId: string): Promise<DiscoveryResponse> =>
	USE_MOCKS ? mockGenerateDiscovery(projectId) : realGenerateDiscovery(projectId);

export const getChatHistory = (
	projectId: string,
	sessionId: string | null = null,
	before?: string | null,
): Promise<ChatHistory> =>
	USE_MOCKS
		? mockGetChatHistory(projectId)
		: realGetChatHistory(projectId, sessionId, before);
