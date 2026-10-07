import { API_BASE_URL } from './config';
import { useAuthStore } from '@/shared/model/auth.store';
import { authHeaders } from './headers';
import type { TokenPairResponse } from './auth.types';
import { parseApiError } from './errors';
import { emitSessionExpired } from '@/shared/lib/session-events';

let isRefreshing = false;
let failedQueue: {
	resolve: (value?: unknown) => void;
	reject: (reason?: unknown) => void;
}[] = [];

const processQueue = (error: Error | null, token: string | null = null) => {
	failedQueue.forEach((prom) => {
		if (error) {
			prom.reject(error);
		} else {
			prom.resolve(token);
		}
	});
	failedQueue = [];
};

export const apiClient = async <T>(
	url: string,
	options: RequestInit = {},
): Promise<T> => {
	const { refreshToken, setTokens } = useAuthStore.getState();
	const isAuthDisabled = process.env.NEXT_PUBLIC_AUTH_DISABLED === 'true';

	const headers = authHeaders(options.headers);

	if (!headers.has('Content-Type')) {
		headers.set('Content-Type', 'application/json; charset=utf-8');
	}

	const config: RequestInit = {
		...options,
		headers,
		cache: options.cache ?? 'no-store',
	};

	let res = await fetch(`${API_BASE_URL}${url}`, config);

	if (
		!isAuthDisabled &&
		res.status === 401 &&
		refreshToken &&
		!url.includes('/auth/token') &&
		!url.includes('/auth/refresh')
	) {
		if (isRefreshing) {
			return new Promise((resolve, reject) => {
				failedQueue.push({ resolve, reject });
			})
				.then((token) => {
					headers.set('Authorization', `Bearer ${token}`);
					return fetch(`${API_BASE_URL}${url}`, { ...config, headers });
				})
				.then(async (retryRes) => {
					if (!retryRes.ok) {
						throw parseApiError(retryRes, await retryRes.json().catch(() => null));
					}
					if (retryRes.status === 204) return null as T;
					return retryRes.json();
				});
		}

		isRefreshing = true;

		try {
			const refreshRes = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					grant_type: 'refresh_token',
					refresh_token: refreshToken,
				}),
			});

			if (!refreshRes.ok) {
				throw parseApiError(refreshRes, await refreshRes.json().catch(() => null));
			}

			const tokens: TokenPairResponse = await refreshRes.json();
			setTokens(tokens.access.token, tokens.refresh.token);

			headers.set('Authorization', `Bearer ${tokens.access.token}`);
			processQueue(null, tokens.access.token);

			res = await fetch(`${API_BASE_URL}${url}`, { ...config, headers });
		} catch (err) {
			processQueue(err as Error, null);
			emitSessionExpired();
			if (typeof window !== 'undefined') {
				window.location.href = '/?session_expired=true';
			}
			throw err;
		} finally {
			isRefreshing = false;
		}
	}

	if (!res.ok) {
		if (
			!isAuthDisabled &&
			res.status === 401 &&
			!url.includes('/auth/token') &&
			!url.includes('/auth/authorize')
		) {
			emitSessionExpired();
			if (typeof window !== 'undefined' && window.location.pathname !== '/') {
				window.location.href = '/?session_expired=true';
			}
		}
		throw parseApiError(res, await res.json().catch(() => null));
	}

	if (res.status === 204) return null as T;

	return res.json();
};

