import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
	HttpResponse,
	apiUrl,
	crearAiConfig,
	crearIntegracion,
	http,
	mockRouter,
	renderWithProviders,
	server,
} from '@/test';
import { OnboardingPage } from './OnboardingPage';

type Estado = { apiKey: boolean; github: boolean; railway: boolean };

function configurar({ apiKey, github, railway }: Estado) {
	server.use(
		http.get(apiUrl('/api/v1/ai-config'), () =>
			HttpResponse.json(
				crearAiConfig({ has_api_key: apiKey, masked_key: apiKey ? '••••1234' : null }),
			),
		),
		http.get(apiUrl('/api/v1/integrations/:provider/status'), ({ params }) =>
			HttpResponse.json(
				crearIntegracion({
					provider: params.provider as 'github' | 'railway',
					is_connected: params.provider === 'github' ? github : railway,
					username: `${params.provider}-user`,
				}),
			),
		),
	);
}

const continuar = () => screen.getByRole('button', { name: /^Continuar/ });

async function renderizar(estado: Estado) {
	configurar(estado);
	const utils = renderWithProviders(<OnboardingPage />);
	await screen.findByRole('heading', { name: 'Configura tu API Key' });
	return utils;
}

describe('OnboardingPage (integración de componentes)', () => {
	it('presenta los tres pasos obligatorios empezando por la API key', async () => {
		await renderizar({ apiKey: false, github: false, railway: false });

		expect(
			screen.getByRole('heading', { name: 'Bienvenido a KOSMO' }),
		).toBeInTheDocument();
		['API Key', 'GitHub', 'Railway'].forEach((paso) =>
			expect(screen.getByText(paso)).toBeInTheDocument(),
		);
		expect(
			screen.getByText(/Paso obligatorio: configura tu API Key/),
		).toBeInTheDocument();
	});

	it('no avanza sin API key', async () => {
		const { user } = await renderizar({ apiKey: false, github: true, railway: true });

		await user.click(continuar());

		expect(
			screen.getByRole('heading', { name: 'Configura tu API Key' }),
		).toBeInTheDocument();
	});

	it('con todo configurado recorre los pasos y entra a KOSMO', async () => {
		const { user } = await renderizar({ apiKey: true, github: true, railway: true });
		await screen.findByText('Configurado');

		await user.click(continuar());
		expect(
			screen.getByRole('heading', { name: 'Conecta tu cuenta de GitHub' }),
		).toBeInTheDocument();
		expect(await screen.findByText('@github-user')).toBeInTheDocument();

		await user.click(continuar());
		expect(
			screen.getByRole('heading', { name: 'Conecta tu cuenta de Railway' }),
		).toBeInTheDocument();
		expect(await screen.findByText('@railway-user')).toBeInTheDocument();

		await user.click(screen.getByRole('button', { name: 'Continuar a KOSMO' }));
		expect(mockRouter.push).toHaveBeenCalledWith('/proyecto');
	});

	it('no deja pasar del paso de GitHub si no está conectado', async () => {
		const { user } = await renderizar({ apiKey: true, github: false, railway: true });
		await screen.findByText('Configurado');
		await user.click(continuar());
		expect(await screen.findByText('No conectado')).toBeInTheDocument();

		await user.click(continuar());

		expect(
			screen.getByRole('heading', { name: 'Conecta tu cuenta de GitHub' }),
		).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Conectar' })).toBeInTheDocument();
	});

	it('no deja terminar si Railway no está conectado', async () => {
		const { user } = await renderizar({ apiKey: true, github: true, railway: false });
		await screen.findByText('Configurado');
		await user.click(continuar());
		await screen.findByText('@github-user');
		await user.click(continuar());
		await screen.findByText('No conectado');

		await user.click(screen.getByRole('button', { name: 'Continuar a KOSMO' }));

		expect(mockRouter.push).not.toHaveBeenCalled();
	});

	it('el paso de Railway se presenta como obligatorio, coherente con el bloqueo', async () => {
		const { user } = await renderizar({ apiKey: true, github: true, railway: false });
		await screen.findByText('Configurado');
		await user.click(continuar());
		await screen.findByText('@github-user');

		await user.click(continuar());

		expect(
			screen.getByText(/^Obligatorio\. Necesitas conectar Railway/),
		).toBeInTheDocument();
		expect(screen.queryByText(/Opcional/)).not.toBeInTheDocument();
	});

	it('desconectar GitHub en el paso lo marca como pendiente', async () => {
		server.use(
			http.delete(
				apiUrl('/api/v1/integrations/:provider'),
				() => new HttpResponse(null, { status: 204 }),
			),
		);
		const { user } = await renderizar({ apiKey: true, github: true, railway: true });
		await screen.findByText('Configurado');
		await user.click(continuar());

		await user.click(await screen.findByRole('button', { name: 'Desconectar' }));

		await waitFor(() => expect(screen.getByText('No conectado')).toBeInTheDocument());
		await user.click(continuar());
		expect(
			screen.getByRole('heading', { name: 'Conecta tu cuenta de GitHub' }),
		).toBeInTheDocument();
	});
});
