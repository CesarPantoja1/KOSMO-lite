/**
 * Integración de la landing: navbar + secciones + modal de autenticación + detección de
 * sesión expirada + video introductorio.
 */
import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useAuthStore } from '@/shared/model/auth-store';
import { crearUsuario, mockRouter, renderWithProviders } from '@/test';
import { RootPage } from './RootPage';

describe('RootPage (landing)', () => {
	it('renderiza todas las secciones principales', () => {
		renderWithProviders(<RootPage />, { route: { pathname: '/' } });

		expect(
			screen.getByRole('heading', { level: 1, name: /Convierte tu idea/ }),
		).toBeInTheDocument();
		expect(
			screen.getByRole('heading', { name: /¿Listo para construir\?/ }),
		).toBeInTheDocument();
		expect(screen.getAllByRole('heading', { level: 2 }).length).toBeGreaterThanOrEqual(4);
	});

	it.each([
		[
			'la barra de navegación',
			() => within(screen.getByRole('banner')).getByRole('button', { name: 'Comenzar' }),
		],
		['el hero', () => screen.getByRole('button', { name: /^Comenzar ahora$/ })],
		['la sección final', () => screen.getByRole('button', { name: 'Comenzar ahora →' })],
	])('"Comenzar" desde %s abre el inicio de sesión', async (_origen, boton) => {
		const { user } = renderWithProviders(<RootPage />, { route: { pathname: '/' } });

		await user.click(boton());

		expect(screen.getByText('Iniciar sesión')).toBeInTheDocument();
		expect(screen.queryByText(/Tu sesión ha expirado/)).not.toBeInTheDocument();
	});

	it('con sesión iniciada lleva a "Mis Proyectos" en lugar de abrir el login', async () => {
		useAuthStore.getState().setUser(crearUsuario());
		const { user } = renderWithProviders(<RootPage />, { route: { pathname: '/' } });

		await user.click(screen.getAllByRole('button', { name: /Mis Proyectos/ })[0]);

		expect(mockRouter.push).toHaveBeenCalledWith('/proyecto');
		expect(screen.queryByText('Iniciar sesión')).not.toBeInTheDocument();
	});

	it('si llega con ?session_expired=true abre el login con el aviso y limpia la URL', () => {
		renderWithProviders(<RootPage />, {
			route: { pathname: '/', searchParams: { session_expired: 'true' } },
		});

		expect(screen.getByText('Iniciar sesión')).toBeInTheDocument();
		expect(screen.getByText(/Tu sesión ha expirado/)).toBeInTheDocument();
		expect(mockRouter.replace).toHaveBeenCalledWith('/');
	});

	it('"Ver cómo funciona" reproduce el video introductorio', async () => {
		const { user, container } = renderWithProviders(<RootPage />, {
			route: { pathname: '/' },
		});

		await user.click(screen.getByRole('button', { name: /Ver cómo funciona/ }));

		expect(container.querySelector('video')).toHaveAttribute(
			'src',
			'/kosmo_intruduction.mp4',
		);
	});

	it('la demo del hero avanza paso a paso hasta invitar a comenzar', async () => {
		const { user } = renderWithProviders(<RootPage />, { route: { pathname: '/' } });

		let siguiente = screen.queryByRole('button', { name: /^Siguiente:/ });
		let pasos = 0;
		while (siguiente && pasos < 10) {
			await user.click(siguiente);
			pasos++;
			siguiente = screen.queryByRole('button', { name: /^Siguiente:/ });
		}

		expect(pasos).toBe(5);
		expect(
			screen.getAllByRole('button', { name: /Comenzar ahora/ }).length,
		).toBeGreaterThanOrEqual(2);
	});
});
