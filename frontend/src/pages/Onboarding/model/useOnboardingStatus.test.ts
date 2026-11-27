import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
	HttpResponse,
	apiUrl,
	crearAiConfig,
	crearIntegracion,
	http,
	server,
} from '@/test';
import { useOnboardingStatus } from './useOnboardingStatus';

const URL_INTEGRACION = '/api/v1/integrations/:provider/status';

describe('useOnboardingStatus', () => {
	it('inicia en estado de carga', () => {
		const { result } = renderHook(() => useOnboardingStatus());

		expect(result.current.loading).toBe(true);
		expect(result.current.github).toBeNull();
		expect(result.current.railway).toBeNull();
	});

	it('carga el estado de GitHub, Railway y la API key', async () => {
		const { result } = renderHook(() => useOnboardingStatus());

		await waitFor(() => expect(result.current.loading).toBe(false));

		expect(result.current.github).toMatchObject({
			provider: 'github',
			is_connected: true,
		});
		expect(result.current.railway).toMatchObject({
			provider: 'railway',
			is_connected: true,
		});
		expect(result.current.hasApiKey).toBe(true);
	});

	it('refleja las integraciones pendientes de conectar', async () => {
		server.use(
			http.get(apiUrl(URL_INTEGRACION), ({ params }) =>
				HttpResponse.json(
					crearIntegracion({
						provider: params.provider as 'github' | 'railway',
						is_connected: params.provider === 'github',
					}),
				),
			),
			http.get(apiUrl('/api/v1/ai-config'), () =>
				HttpResponse.json(crearAiConfig({ has_api_key: false })),
			),
		);
		const { result } = renderHook(() => useOnboardingStatus());

		await waitFor(() => expect(result.current.loading).toBe(false));

		expect(result.current.github?.is_connected).toBe(true);
		expect(result.current.railway?.is_connected).toBe(false);
		expect(result.current.hasApiKey).toBe(false);
	});

	it('termina la carga sin datos si falla una integración', async () => {
		server.use(
			http.get(apiUrl(URL_INTEGRACION), () => HttpResponse.json({}, { status: 500 })),
		);
		const { result } = renderHook(() => useOnboardingStatus());

		await waitFor(() => expect(result.current.loading).toBe(false));

		expect(result.current.github).toBeNull();
		expect(result.current.railway).toBeNull();
		expect(result.current.hasApiKey).toBe(false);
	});

	it('refresh() vuelve a consultar y actualiza el estado', async () => {
		server.use(
			http.get(apiUrl(URL_INTEGRACION), ({ params }) =>
				HttpResponse.json(
					crearIntegracion({
						provider: params.provider as 'github' | 'railway',
						is_connected: false,
					}),
				),
			),
		);
		const { result } = renderHook(() => useOnboardingStatus());
		await waitFor(() => expect(result.current.loading).toBe(false));
		expect(result.current.github?.is_connected).toBe(false);

		// El usuario conecta GitHub en otra ventana y vuelve.
		server.resetHandlers();
		await act(() => result.current.refresh());

		expect(result.current.github?.is_connected).toBe(true);
		expect(result.current.loading).toBe(false);
	});
});
