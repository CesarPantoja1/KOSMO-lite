import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/api', () => ({
	getIntegrationStatus: vi.fn(),
	connectIntegration: vi.fn(),
	disconnectIntegration: vi.fn(),
}));

vi.mock('@/shared/api', () => ({
	authApi: { getMe: vi.fn() },
	PUBLIC_APP_DOMAIN: 'http://localhost:3000',
	formatApiError: (_err: unknown, fallback: string) => fallback,
}));

vi.mock('@/shared/model', () => ({
	useAuthStore: { getState: () => ({ setUser: vi.fn() }) },
}));

vi.mock('@/shared/ui/toast/toast', () => ({
	toast: { success: vi.fn(), error: vi.fn() },
}));

import { getIntegrationStatus, connectIntegration, disconnectIntegration } from '../api/api';
import { authApi } from '@/shared/api';
import { toast } from '@/shared/ui/toast/toast';
import { useOAuthIntegration } from './useOAuthIntegration';

const api = {
	getIntegrationStatus: vi.mocked(getIntegrationStatus),
	connectIntegration: vi.mocked(connectIntegration),
	disconnectIntegration: vi.mocked(disconnectIntegration),
};

const baseParams = {
	provider: 'github' as const,
	label: 'GitHub',
	messageType: 'github-oauth-code',
	buildAuthUrl: (redirectUri: string, state: string, codeChallenge: string) =>
		`https://auth.example.com?redirect=${redirectUri}&state=${state}&challenge=${codeChallenge}`,
	redirectUri: 'https://app.example.com/perfil',
};

describe('useOAuthIntegration', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});

	it('consulta el estado de la integración al montar y lo expone', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({
			provider: 'github',
			is_connected: true,
			username: 'octocat',
		});
		const onStatusChange = vi.fn();

		// Act
		const { result } = renderHook(() => useOAuthIntegration({ ...baseParams, onStatusChange }));

		// Assert
		await waitFor(() => expect(result.current.loading).toBe(false));
		expect(result.current.isConnected).toBe(true);
		expect(result.current.username).toBe('octocat');
		expect(onStatusChange).toHaveBeenCalledWith(
			expect.objectContaining({ is_connected: true }),
		);
	});

	it('muestra un toast de error si falla la consulta de estado', async () => {
		// Arrange
		api.getIntegrationStatus.mockRejectedValue(new Error('network error'));

		// Act
		const { result } = renderHook(() => useOAuthIntegration(baseParams));

		// Assert
		await waitFor(() => expect(result.current.loading).toBe(false));
		expect(vi.mocked(toast.error)).toHaveBeenCalled();
	});

	it('handleConnect abre un popup con la URL de autorización', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: false });
		const assign = vi.fn();
		const popup = { location: { assign }, close: vi.fn() } as unknown as Window;
		const openSpy = vi.spyOn(window, 'open').mockReturnValue(popup);
		const { result } = renderHook(() => useOAuthIntegration(baseParams));
		await waitFor(() => expect(result.current.loading).toBe(false));

		// Act
		act(() => {
			result.current.handleConnect();
		});

		// Assert
		expect(openSpy).toHaveBeenCalledWith(
			'',
			'oauth-github',
			'width=600,height=700',
		);
		await waitFor(() =>
			expect(assign).toHaveBeenCalledWith(
				expect.stringContaining(
					'https://auth.example.com?redirect=https://app.example.com/perfil&state=github.',
				),
			),
		);
	});

	it('ignora mensajes postMessage de origen distinto', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: false });
		const { result } = renderHook(() => useOAuthIntegration(baseParams));
		await waitFor(() => expect(result.current.loading).toBe(false));

		// Act
		act(() => {
			window.dispatchEvent(
				new MessageEvent('message', {
					origin: 'https://otro-origen.com',
					data: { type: 'github-oauth-code', code: 'abc' },
				}),
			);
		});

		// Assert
		expect(api.connectIntegration).not.toHaveBeenCalled();
	});

	it('procesa el código recibido por postMessage y conecta la integración', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: false });
		api.connectIntegration.mockResolvedValue({
			provider: 'github',
			is_connected: true,
			username: 'octocat',
		});
		window.sessionStorage.setItem('kosmo.oauth.github.state', 'github.test-state');
		window.sessionStorage.setItem('kosmo.oauth.github.verifier', 'v'.repeat(64));
		vi.mocked(authApi.getMe).mockResolvedValue({ subject: 'usr_1' } as never);
		const { result } = renderHook(() => useOAuthIntegration(baseParams));
		await waitFor(() => expect(result.current.loading).toBe(false));

		// Act
		await act(async () => {
			window.dispatchEvent(
				new MessageEvent('message', {
					origin: window.location.origin,
					data: { type: 'github-oauth-code', code: 'abc123', state: 'github.test-state' },
				}),
			);
		});

		// Assert
		await waitFor(() => expect(result.current.isConnected).toBe(true));
		expect(api.connectIntegration).toHaveBeenCalledWith('github', {
			code: 'abc123',
			redirect_uri: baseParams.redirectUri,
			code_verifier: 'v'.repeat(64),
		});
		expect(vi.mocked(toast.success)).toHaveBeenCalled();
	});

	it('ignora mensajes postMessage duplicados con el mismo código sin mostrar error', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: false });
		api.connectIntegration.mockResolvedValue({
			provider: 'github',
			is_connected: true,
			username: 'octocat',
		});
		window.sessionStorage.setItem('kosmo.oauth.github.state', 'github.test-state');
		window.sessionStorage.setItem('kosmo.oauth.github.verifier', 'v'.repeat(64));
		vi.mocked(authApi.getMe).mockResolvedValue({ subject: 'usr_1' } as never);
		const { result } = renderHook(() => useOAuthIntegration(baseParams));
		await waitFor(() => expect(result.current.loading).toBe(false));

		// Act: emitimos el mensaje dos veces seguidas (como ocurre en re-renders del popup)
		await act(async () => {
			window.dispatchEvent(
				new MessageEvent('message', {
					origin: window.location.origin,
					data: { type: 'github-oauth-code', code: 'duplicate-code-1', state: 'github.test-state' },
				}),
			);
			window.dispatchEvent(
				new MessageEvent('message', {
					origin: window.location.origin,
					data: { type: 'github-oauth-code', code: 'duplicate-code-1', state: 'github.test-state' },
				}),
			);
		});

		// Assert
		expect(api.connectIntegration).toHaveBeenCalledTimes(1);
		expect(vi.mocked(toast.error)).not.toHaveBeenCalled();
		expect(vi.mocked(toast.success)).toHaveBeenCalledTimes(1);
	});

	it('muestra un toast de error cuando el popup reporta oauth-error', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: false });
		const { result } = renderHook(() => useOAuthIntegration(baseParams));
		await waitFor(() => expect(result.current.loading).toBe(false));

		// Act
		act(() => {
			window.dispatchEvent(
				new MessageEvent('message', {
					origin: window.location.origin,
					data: { type: 'oauth-error', error: 'access_denied' },
				}),
			);
		});

		// Assert
		expect(vi.mocked(toast.error)).toHaveBeenCalledWith(expect.stringContaining('access_denied'));
	});

	it('handleDisconnect actualiza el estado a desconectado', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: true });
		api.disconnectIntegration.mockResolvedValue(undefined);
		const { result } = renderHook(() => useOAuthIntegration(baseParams));
		await waitFor(() => expect(result.current.isConnected).toBe(true));

		// Act
		await act(async () => {
			result.current.handleDisconnect();
			await Promise.resolve();
		});

		// Assert
		await waitFor(() => expect(result.current.isConnected).toBe(false));
		expect(vi.mocked(toast.success)).toHaveBeenCalled();
	});
});
