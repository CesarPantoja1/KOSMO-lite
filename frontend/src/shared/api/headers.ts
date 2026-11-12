import { useAuthStore } from '../model';

export function authHeaders(extra: HeadersInit = {}): Headers {
	const headers = new Headers(extra);
	const { accessToken, mockUserId } = useAuthStore.getState();
	const isAuthDisabled = process.env.NEXT_PUBLIC_AUTH_DISABLED === 'true';

	if (accessToken && !headers.has('Authorization')) {
		headers.set('Authorization', `Bearer ${accessToken}`);
	} else if (isAuthDisabled && mockUserId && !headers.has('X-Mock-User')) {
		headers.set('X-Mock-User', mockUserId);
	}

	return headers;
}
