export type AIProvider = 'openai' | 'anthropic' | 'google' | 'deepseek' | 'custom';

export type AIModelTier = 'flagship' | 'balanced' | 'fast';

export interface AIModelInfo {
	id: string;
	display_name: string;
	tier: AIModelTier;
}

export interface AIProviderInfo {
	value: string;
	label: string;
	models: AIModelInfo[];
}

export const DEFAULT_AI_PROVIDER: AIProvider = 'google';
export const DEFAULT_AI_MODEL = 'gemini-3.8-flash';

export const TIER_LABELS: Record<AIModelTier, string> = {
	flagship: 'Máxima capacidad',
	balanced: 'Equilibrado',
	fast: 'Más veloz',
};

export interface AIConfigView {
	provider: AIProvider | null;
	model: string | null;
	is_custom: boolean;
	has_api_key: boolean;
	masked_key: string | null;
	updated_at: string | null;
}

export interface SaveAIConfigRequest {
	provider: AIProvider;
	model: string;
	api_key: string;
}

export interface TestAIConnectionRequest {
	provider: AIProvider;
	model: string;
	api_key: string;
}

export interface TestAIConnectionResult {
	is_connected: boolean;
	detected_model: string;
	message: string;
}

export function maskApiKey(key: string | null): string | null {
	if (!key) return null;
	const stripped = key.trim();
	if (!stripped) return null;
	if (stripped.length <= 4) return '••••••••';
	return `••••••••${stripped.slice(-4)}`;
}
