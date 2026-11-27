import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
	HttpResponse,
	apiUrl,
	crearAiConfig,
	crearIntegracion,
	http,
	mockRouter,
	server,
} from '@/test';
import { useIntegrationGate } from './useIntegrationGate';

type Requisitos = { github: boolean; railway: boolean; apiKey: boolean };

function configurarRequisitos({ github, railway, apiKey }: Requisitos) {
	server.use(
		http.get(apiUrl('/api/v1/integrations/:provider/status'), ({ params }) =>
			HttpResponse.json(
				crearIntegracion({
					provider: params.provider as 'github' | 'railway',
					is_connected: params.provider === 'github' ? github : railway,
				}),
			),
		),
		http.get(apiUrl('/api/v1/ai-config'), () =>
			HttpResponse.json(crearAiConfig({ has_api_key: apiKey })),
		),
	);
}

describe('useIntegrationGate', () => {
	it('no está listo mientras verifica los requisitos', () => {
		const { result } = renderHook(() => useIntegrationGate());

		expect(result.current).toEqual({
			isReady: false,
			githubConnected: false,
			railwayConnected: false,
		});
	});

	it('habilita la creación cuando GitHub, Railway y la API key están configurados', async () => {
		configurarRequisitos({ github: true, railway: true, apiKey: true });
		const { result } = renderHook(() => useIntegrationGate());

		await waitFor(() => expect(result.current.isReady).toBe(true));

		expect(result.current.githubConnected).toBe(true);
		expect(result.current.railwayConnected).toBe(true);
		expect(mockRouter.replace).not.toHaveBeenCalled();
	});

	it.each<[string, Requisitos]>([
		['falta GitHub', { github: false, railway: true, apiKey: true }],
		['falta Railway', { github: true, railway: false, apiKey: true }],
		['falta la API key', { github: true, railway: true, apiKey: false }],
		['falta todo', { github: false, railway: false, apiKey: false }],
	])('redirige al onboarding cuando %s', async (_caso, requisitos) => {
		configurarRequisitos(requisitos);
		const { result } = renderHook(() => useIntegrationGate());

		await waitFor(() => expect(mockRouter.replace).toHaveBeenCalledWith('/onboarding'));

		expect(result.current.isReady).toBe(false);
	});

	it('redirige al onboarding si no se puede verificar una integración', async () => {
		server.use(
			http.get(apiUrl('/api/v1/integrations/:provider/status'), () =>
				HttpResponse.json({ detail: 'caído' }, { status: 503 }),
			),
		);
		const { result } = renderHook(() => useIntegrationGate());

		await waitFor(() => expect(mockRouter.replace).toHaveBeenCalledWith('/onboarding'));

		expect(result.current.isReady).toBe(false);
	});

	it('no redirige si el componente se desmonta antes de terminar la verificación', async () => {
		configurarRequisitos({ github: false, railway: false, apiKey: false });
		const { unmount } = renderHook(() => useIntegrationGate());

		unmount();
		await new Promise((r) => setTimeout(r, 50));

		expect(mockRouter.replace).not.toHaveBeenCalled();
	});
});
