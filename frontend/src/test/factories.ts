/**
 * Fábricas de datos de prueba. Devuelven objetos válidos con valores por defecto
 * que cada test puede sobrescribir solo en lo que le interesa.
 *
 * @example
 *   const proyecto = crearProyecto({ name: 'Mi App' });
 */
import type { AIConfigView, AIProviderInfo } from '@/entities/ai-config/model/types';
import type {
	CharacteristicResponse,
	SuggestCharacteristic,
} from '@/entities/characteristic/model/types';
import type { ChatSessionSummary } from '@/entities/chat/model/types';
import type { ConsistencyStatusResponse } from '@/entities/consistency/model/types';
import type { IntegrationStatus } from '@/entities/integration/model/types';
import type { Project } from '@/entities/project/model/types';
import type { PrincipalView, TokenPairResponse } from '@/shared/model/auth-types';
import type { ChangeSuggestion, ChatMessage } from '@/shared/model/chat-message';

let secuencia = 0;
const siguienteId = () => ++secuencia;

/** Reinicia el contador de ids; se llama en `afterEach` para tests deterministas. */
export const resetFactories = () => {
	secuencia = 0;
};

const FECHA_FIJA = '2026-01-15T10:00:00.000Z';

export function crearProyecto(overrides: Partial<Project> = {}): Project {
	const n = siguienteId();
	return {
		id: `prj_${n}`,
		name: `Proyecto ${n}`,
		slug: `proyecto-${n}`,
		description: `Descripción del proyecto ${n}`,
		owner_id: 'usr_test',
		created_at: FECHA_FIJA,
		updated_at: FECHA_FIJA,
		current_phase: 'discovery',
		status: 'active',
		...overrides,
	};
}

export function crearCaracteristica(
	overrides: Partial<CharacteristicResponse> = {},
): CharacteristicResponse {
	const n = siguienteId();
	return {
		id: `feat_${n}`,
		project_id: 'prj_1',
		number: n,
		title: `Característica ${n}`,
		slug: `caracteristica-${n}`,
		description: `Descripción de la característica ${n}`,
		origin: 'manual',
		display_id: `F-${String(n).padStart(3, '0')}`,
		warnings: [],
		...overrides,
	};
}

export function crearUsuario(overrides: Partial<PrincipalView> = {}): PrincipalView {
	return {
		subject: 'usr_test',
		name: 'Usuario de Prueba',
		email: 'usuario@test.com',
		avatar_url: null,
		scopes: ['agent:run', 'profile:read'],
		...overrides,
	};
}

export function crearIntegracion(
	overrides: Partial<IntegrationStatus> = {},
): IntegrationStatus {
	return {
		provider: 'github',
		is_connected: true,
		username: 'usuario-test',
		connected_at: FECHA_FIJA,
		...overrides,
	};
}

export function crearAiConfig(overrides: Partial<AIConfigView> = {}): AIConfigView {
	return {
		provider: 'google',
		model: 'gemini-3.8-flash',
		is_custom: false,
		has_api_key: true,
		masked_key: '••••1234',
		updated_at: FECHA_FIJA,
		...overrides,
	};
}

/** Catálogo de proveedores de IA con modelos en varios niveles (tiers). */
export function crearProveedoresIA(): AIProviderInfo[] {
	return [
		{
			value: 'google',
			label: 'Google Gemini',
			models: [
				{ id: 'gemini-3.8-pro', display_name: 'Gemini 3.8 Pro', tier: 'flagship' },
				{ id: 'gemini-3.8-flash', display_name: 'Gemini 3.8 Flash', tier: 'fast' },
			],
		},
		{
			value: 'anthropic',
			label: 'Anthropic',
			models: [
				{ id: 'claude-opus-5-5', display_name: 'Claude Opus 5.5', tier: 'flagship' },
				{ id: 'claude-sonnet-5-5', display_name: 'Claude Sonnet 5.5', tier: 'balanced' },
				{
					id: 'claude-legacy',
					display_name: 'Claude Legacy',
					tier: 'balanced',
					is_deprecated: true,
				},
			],
		},
	];
}

export function crearEstadoConsistencia(
	phases: Partial<ConsistencyStatusResponse['phases']> = {},
): ConsistencyStatusResponse {
	const vacio = { pending: 0, evaluating: 0, failed: 0 };
	return {
		phases: {
			features: vacio,
			requirements: vacio,
			implementation: vacio,
			...phases,
		},
	};
}

export function crearSugerencia(
	overrides: Partial<SuggestCharacteristic> = {},
): SuggestCharacteristic {
	const n = siguienteId();
	return {
		number: n,
		title: `Sugerencia ${n}`,
		description: `Descripción de la sugerencia ${n}`,
		origin: 'ai',
		...overrides,
	};
}

export function crearCambioSugerido(
	overrides: Partial<ChangeSuggestion> = {},
): ChangeSuggestion {
	const n = siguienteId();
	return {
		id: `chg_${n}`,
		section: 'Alcance',
		description: `Cambio sugerido ${n}`,
		diff_before: 'Texto anterior',
		diff_after: 'Texto propuesto',
		rationale: null,
		applied: false,
		not_applied_reason: null,
		...overrides,
	};
}

export function crearMensaje(overrides: Partial<ChatMessage> = {}): ChatMessage {
	const n = siguienteId();
	return {
		id: `msg_${n}`,
		role: 'assistant',
		content: `Mensaje ${n}`,
		created_at: FECHA_FIJA,
		change_suggestions: null,
		modification: null,
		...overrides,
	};
}

export function crearSesionChat(
	overrides: Partial<ChatSessionSummary> = {},
): ChatSessionSummary {
	const n = siguienteId();
	return {
		id: `ses_${n}`,
		phase: 'features',
		context_id: null,
		created_at: FECHA_FIJA,
		message_count: 0,
		last_message_at: null,
		title: `Chat ${n}`,
		...overrides,
	};
}

export function crearTokens(
	overrides: Partial<TokenPairResponse> = {},
): TokenPairResponse {
	return {
		access: { token: 'access-token-test', jti: 'jti-access', expires_at: FECHA_FIJA },
		refresh: { token: 'refresh-token-test', jti: 'jti-refresh', expires_at: FECHA_FIJA },
		token_type: 'Bearer',
		...overrides,
	};
}
