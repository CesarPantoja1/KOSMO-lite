import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
	HttpResponse,
	apiUrl,
	crearAiConfig,
	http,
	mockRouter,
	renderWithProviders,
	server,
} from '@/test';
import { CreateProjectPage } from './CreateProjectPage';

describe('CreateProjectPage (integración)', () => {
	it('muestra un indicador de carga mientras verifica los requisitos', () => {
		const { container } = renderWithProviders(<CreateProjectPage />);

		expect(container.querySelector('.animate-spin-custom')).toBeInTheDocument();
		expect(
			screen.queryByRole('heading', { name: 'Crear Proyecto' }),
		).not.toBeInTheDocument();
	});

	it('con los requisitos cumplidos muestra el formulario de creación', async () => {
		renderWithProviders(<CreateProjectPage />);

		expect(
			await screen.findByRole('heading', { name: 'Crear Proyecto' }),
		).toBeInTheDocument();
		expect(screen.getByLabelText('Nombre del proyecto')).toBeInTheDocument();
		expect(mockRouter.replace).not.toHaveBeenCalled();
	});

	it('sin API key redirige al onboarding y no muestra el formulario', async () => {
		server.use(
			http.get(apiUrl('/api/v1/ai-config'), () =>
				HttpResponse.json(crearAiConfig({ has_api_key: false })),
			),
		);
		renderWithProviders(<CreateProjectPage />);

		await waitFor(() => expect(mockRouter.replace).toHaveBeenCalledWith('/onboarding'));
		expect(
			screen.queryByRole('heading', { name: 'Crear Proyecto' }),
		).not.toBeInTheDocument();
	});
});
