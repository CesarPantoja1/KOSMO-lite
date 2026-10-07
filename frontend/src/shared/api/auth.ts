import { apiClient } from './client';
import { generateCodeVerifier, generateCodeChallenge } from '@/shared/lib/pkce';
import { useAuthStore } from '@/shared/model/auth.store';
import type {
	RegisterResponse,
	AuthorizationCodeResponse,
	TokenPairResponse,
	PrincipalView,
} from './auth.types';

export const authApi = {
	async register(name: string, email: string, password: string): Promise<RegisterResponse> {
		return apiClient<RegisterResponse>('/api/v1/auth/register', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name, email, password }),
		});
	},

	async authorize(email: string, password: string): Promise<{ code: string; verifier: string }> {
		const verifier = generateCodeVerifier();
		const challenge = await generateCodeChallenge(verifier);

		const response = await apiClient<AuthorizationCodeResponse>('/api/v1/auth/authorize', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				email,
				password,
				code_challenge: challenge,
				code_challenge_method: 'S256',
				scopes: ['profile:read', 'agent:run'],
			}),
		});

		return { code: response.authorization_code, verifier };
	},

	async exchangeToken(code: string, verifier: string): Promise<TokenPairResponse> {
		return apiClient<TokenPairResponse>('/api/v1/auth/token', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				grant_type: 'authorization_code',
				code,
				code_verifier: verifier,
			}),
		});
	},

	async getMe(): Promise<PrincipalView> {
		return apiClient<PrincipalView>('/api/v1/auth/me', {
			method: 'GET',
		});
	},

	async login(email: string, password: string): Promise<void> {
		const { code, verifier } = await this.authorize(email, password);
		const tokens = await this.exchangeToken(code, verifier);
		
		const { setTokens, setUser } = useAuthStore.getState();
		setTokens(tokens.access.token, tokens.refresh.token);
		
		const user = await this.getMe();
		setUser(user);
	},

	async logout(): Promise<void> {
		const { refreshToken, clearAuth } = useAuthStore.getState();
		
		if (refreshToken) {
			try {
				await apiClient('/api/v1/auth/logout', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ refresh_token: refreshToken }),
				});
			} catch (e) {
				console.error('Error on logout', e);
			}
		}
		
		clearAuth();
	},
};
