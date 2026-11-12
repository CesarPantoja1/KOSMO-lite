import type { ChatHistory, ChatResponse } from '@/shared/model/chat-message';
import { apiClient } from '@/shared/api';
import { USE_MOCKS } from '@/shared/api/config';
import type {
	CharacteristicResponse,
	CreateCharacteristicResponse,
	SuggestCharacteristic,
} from '../model/types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// --- Mock data ---

const mockCharacteristics: CharacteristicResponse[] = [];

const mockSuggestions: SuggestCharacteristic[] = [
	{
		number: 2,
		title: 'Gestión de Inventario',
		description:
			'Control de stock, entradas y salidas de productos, alertas de inventario bajo y registro de movimientos con trazabilidad.',
		origin: '',
	},
	{
		number: 3,
		title: 'Módulo de Ventas',
		description:
			'Registro de ventas con cálculo automático de impuestos, descuentos y múltiples métodos de pago. Genera facturas electrónicas y tickets.',
		origin: '',
	},
	{
		number: 4,
		title: 'Reportes y Dashboard',
		description:
			'Visualización de indicadores clave como ventas diarias, productos más vendidos, márgenes de ganancia y tendencias de consumo.',
		origin: '',
	},
];

const mockChatResponses: ChatResponse[] = [
	{
		message: {
			id: 'mock-chat-1',
			role: 'assistant',
			content: 'Hola, ¿en qué puedo ayudarte con la característica?',
			created_at: new Date().toISOString(),
			change_suggestions: null,
			modification: null,
		},
		modification: null,
		redirect: null,
		consistency: null,
	},
	{
		message: {
			id: 'mock-chat-2',
			role: 'assistant',
			content:
				'Aquí tienes una sugerencia de cambio para mejorar la descripción de la característica.',
			created_at: new Date().toISOString(),
			change_suggestions: [
				{
					id: 'mock-chg-1',
					section: 'Descripción de la característica',
					description: 'Refinar la descripción para mayor claridad.',
					diff_before:
						'Permite crear cuentas para empleados y asignarles roles específicos (Administrador, Cajero, Bodeguero) para restringir el acceso a pantallas y funciones sensibles del sistema.',
					diff_after:
						'Permite crear cuentas para empleados y asignarles roles específicos (Administrador, Cajero, Bodeguero) para controlar el acceso a pantallas y funciones críticas del sistema.',
					rationale: 'Precisión terminológica.',
					applied: true,
					not_applied_reason: null,
				},
			],
			modification: {
				applied: true,
				modified_section: 'Descripción de la característica',
				change_description: 'Se aplicaron los cambios sugeridos.',
				modified_document: null,
				before: null,
				after: null,
				undo_version_id: null,
				clarification_message: null,
			},
		},
		modification: {
			applied: true,
			modified_section: 'Descripción de la característica',
			change_description: 'Se aplicaron los cambios sugeridos.',
			modified_document: null,
			before: null,
			after: null,
			undo_version_id: null,
			clarification_message: null,
		},
		redirect: null,
		consistency: null,
	},
];

let mockStore = [...mockCharacteristics];

// --- Mock implementations ---

const mockGetCharacteristics = async (
	_projectId: string,
): Promise<CharacteristicResponse[]> => {
	await delay(3000);
	return [...mockStore];
};

const mockGenerateCharacteristics = async (
	_projectId: string,
): Promise<CharacteristicResponse[]> => {
	await delay(2000);
	return [
		...mockStore,
		{
			id: '1',
			project_id: 'mock-project-1',
			number: 1,
			title: 'Administración de Perfiles y Permisos de Usuario',
			slug: 'administracion-de-perfiles-y-permisos-de-usuario',
			description:
				'Permite crear cuentas para empleados y asignarles roles específicos (Administrador, Cajero, Bodeguero) para restringir el acceso a pantallas y funciones sensibles del sistema.',
			origin: '',
			display_id: 'C01',
		},
	];
};

const mockGetSuggestCharacteristics = async (
	_projectId: string,
): Promise<SuggestCharacteristic[]> => {
	await delay(5000);
	return [...mockSuggestions];
};

const mockAddCharacteristic = async (
	projectId: string,
	item: { title: string; description: string; origin?: string },
): Promise<CreateCharacteristicResponse> => {
	await delay(600);
	const nextNum = mockStore.length + 1;
	const newChar: CharacteristicResponse = {
		id: `mock-ID-${nextNum}`,
		project_id: projectId,
		number: nextNum,
		title: item.title,
		slug: 'slug-generated-from-title',
		description: item.description,
		origin: item.origin || 'item origin',
		display_id: `C${String(nextNum).padStart(2, '0')}`,
	};
	mockStore = [...mockStore, newChar];
	return {
		is_saved: true,
		feature: newChar,
		origin: '',
		is_consistent: true,
	};
};

const mockSendChatMessage = async (
	_featureId: string,
	_content: string,
): Promise<ChatResponse> => {
	await delay(500);
	return mockChatResponses[Math.floor(Math.random() * mockChatResponses.length)];
};

const mockGetChatHistory = async (featureId: string): Promise<ChatHistory> => {
	await delay(300);
	return {
		phase: 'features',
		context: featureId,
		messages: [],
		has_more: false,
		next_cursor: null,
	};
};

// --- Real implementations ---

const realGetCharacteristics = async (
	projectId: string,
): Promise<CharacteristicResponse[]> => {
	return apiClient<CharacteristicResponse[]>(`/api/v1/projects/${projectId}/features`, {
		method: 'GET',
	});
};

const realGenerateCharacteristics = async (
	projectId: string,
): Promise<CharacteristicResponse[]> => {
	return apiClient<CharacteristicResponse[]>(`/api/v1/projects/${projectId}/features`, {
		method: 'POST',
	});
};

const realGetSuggestCharacteristics = async (
	projectId: string,
): Promise<SuggestCharacteristic[]> => {
	return apiClient<SuggestCharacteristic[]>(
		`/api/v1/projects/${projectId}/features/suggest`,
		{ method: 'POST' },
	);
};

const realAddCharacteristic = async (
	projectId: string,
	item: { title: string; description: string; origin?: string },
): Promise<CreateCharacteristicResponse> => {
	return apiClient<CreateCharacteristicResponse>(
		`/api/v1/projects/${projectId}/features/manual`,
		{
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				title: item.title,
				description: item.description,
				origin: item.origin || '',
			}),
		},
	);
};

const realSendChatMessage = async (
	featureId: string,
	content: string,
): Promise<ChatResponse> => {
	return apiClient<ChatResponse>(`/api/v1/features/${featureId}/chat`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ content }),
	});
};

const realGetChatHistory = (
	featureId: string,
	sessionId: string | null,
	before?: string | null,
) => {
	const query = new URLSearchParams();
	if (sessionId) query.set('session_id', sessionId);
	if (before) query.set('before', before);
	const suffix = query.toString() ? `?${query.toString()}` : '';
	return apiClient<ChatHistory>(`/api/v1/features/${featureId}/chat/history${suffix}`, {
		method: 'GET',
	});
};

const realDeleteFeature = async (projectId: string, featureId: string): Promise<void> => {
	await apiClient<void>(
		`/api/v1/projects/${encodeURIComponent(projectId)}/features/${encodeURIComponent(featureId)}`,
		{ method: 'DELETE' },
	);
};

// --- Exports (switch based on USE_MOCKS) ---

export const getCharacteristics = (
	projectId: string,
): Promise<CharacteristicResponse[]> =>
	USE_MOCKS ? mockGetCharacteristics(projectId) : realGetCharacteristics(projectId);

export const generateCharacteristics = (
	projectId: string,
): Promise<CharacteristicResponse[]> =>
	USE_MOCKS
		? mockGenerateCharacteristics(projectId)
		: realGenerateCharacteristics(projectId);

export const getSuggestCharacteristics = (
	projectId: string,
): Promise<SuggestCharacteristic[]> =>
	USE_MOCKS
		? mockGetSuggestCharacteristics(projectId)
		: realGetSuggestCharacteristics(projectId);

export const addCharacteristic = (
	projectId: string,
	item: { title: string; description: string; origin?: string },
): Promise<CreateCharacteristicResponse> =>
	USE_MOCKS
		? mockAddCharacteristic(projectId, item)
		: realAddCharacteristic(projectId, item);

export const sendChatMessage = (
	featureId: string,
	content: string,
): Promise<ChatResponse> =>
	USE_MOCKS
		? mockSendChatMessage(featureId, content)
		: realSendChatMessage(featureId, content);

export const getChatHistory = (
	featureId: string,
	sessionId: string | null = null,
	before?: string | null,
): Promise<ChatHistory> =>
	USE_MOCKS
		? mockGetChatHistory(featureId)
		: realGetChatHistory(featureId, sessionId, before);

export const deleteFeature = (projectId: string, featureId: string): Promise<void> =>
	USE_MOCKS ? Promise.resolve() : realDeleteFeature(projectId, featureId);
