import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useAiConfigStore } from '@/entities/ai-config';
import { HttpResponse, apiUrl, crearAiConfig, http, renderWithProviders, server } from '@/test';
import { AiProviderToast } from './AiProviderToast';

function configIA(overrides: Parameters<typeof crearAiConfig>[0]) {
	server.use(http.get(apiUrl('/api/v1/ai-config'), () => HttpResponse.json(crearAiConfig(overrides))));
}

describe('AiProviderToast', () => {
	it('avisa y enlaza al onboarding cuando no hay API key configurada', async () => {
		configIA({ has_api_key: false, is_custom: false });

		renderWithProviders(<AiProviderToast />);

		expect(await screen.findByText(/API Key de IA no configurada/)).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Configurar ahora' })).toHaveAttribute(
			'href',
			'/onboarding',
		);
	});

	it.each([
		['hay API key', { has_api_key: true, is_custom: false }],
		['el proveedor es personalizado', { has_api_key: false, is_custom: true }],
	])('no avisa cuando %s', async (_caso, overrides) => {
		configIA(overrides);

		const { container } = renderWithProviders(<AiProviderToast />);

		await waitFor(() => expect(useAiConfigStore.getState().config).not.toBeNull());
		expect(container).toBeEmptyDOMElement();
	});

	it('consulta la configuración de IA al montarse', async () => {
		renderWithProviders(<AiProviderToast />);

		await waitFor(() => expect(useAiConfigStore.getState().config?.has_api_key).toBe(true));
	});
});
