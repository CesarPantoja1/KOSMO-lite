import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '@/shared/model/auth.store';
import { apiClient } from './client';

describe('apiClient', () => {
	beforeEach(() => {
		vi.restoreAllMocks();
		useAuthStore.setState({
			accessToken: 'old-access-token',
			refreshToken: 'valid-refresh-token',
			user: null,
			mockUserId: null,
		});
		delete process.env.NEXT_PUBLIC_AUTH_DISABLED;
	});

	it('retorna null cuando la respuesta directa es 204 No Content', async () => {
		global.fetch = vi.fn().mockResolvedValue(
			new Response(null, {
				status: 204,
				statusText: 'No Content',
			}),
		);

		const result = await apiClient<void>('/api/v1/test');
		expect(result).toBeNull();
	});

	it('retorna null en peticiones encoladas en failedQueue cuando el reintento responde 204 No Content', async () => {
		let callCount = 0;
		global.fetch = vi.fn().mockImplementation(async (url: string) => {
			callCount++;
			// Petición 1: 401 que inicia el refresh
			if (callCount === 1) {
				return new Response(JSON.stringify({ detail: 'Token expired' }), {
					status: 401,
					headers: { 'Content-Type': 'application/json' },
				});
			}
			// Petición 2 (concurrente): 401 que entra en failedQueue mientras isRefreshing es true
			if (callCount === 2) {
				return new Response(JSON.stringify({ detail: 'Token expired' }), {
					status: 401,
					headers: { 'Content-Type': 'application/json' },
				});
			}
			// Petición de refresco de tokens
			if (url.includes('/api/v1/auth/refresh')) {
				return new Response(
					JSON.stringify({
						access: { token: 'new-access-token', expires_in: 900 },
						refresh: { token: 'new-refresh-token', expires_in: 604800 },
					}),
					{
						status: 200,
						headers: { 'Content-Type': 'application/json' },
					},
				);
			}
			// Reintento de la primera petición
			if (callCount === 4) {
				return new Response(JSON.stringify({ ok: true }), {
					status: 200,
					headers: { 'Content-Type': 'application/json' },
				});
			}
			// Reintento de la segunda petición (encolada): 204 No Content
			if (callCount === 5) {
				return new Response(null, {
					status: 204,
					statusText: 'No Content',
				});
			}
			return new Response(null, { status: 500 });
		});

		// Disparamos ambas peticiones concurrentemente
		const [res1, res2] = await Promise.all([
			apiClient<{ ok: boolean }>('/api/v1/first'),
			apiClient<void>('/api/v1/second-delete'),
		]);

		expect(res1).toEqual({ ok: true });
		expect(res2).toBeNull();
	});
});
