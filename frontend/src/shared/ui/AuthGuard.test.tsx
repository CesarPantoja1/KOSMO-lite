import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '@/shared/model/auth-store';
import { mockRouter, renderWithProviders } from '@/test';
import { AuthGuard } from './AuthGuard';

const contenidoPrivado = <p>Contenido privado</p>;

describe('AuthGuard', () => {
	afterEach(() => {
		vi.unstubAllEnvs();
	});

	it('muestra el contenido cuando hay sesión', () => {
		useAuthStore.getState().setTokens('access', 'refresh');

		renderWithProviders(<AuthGuard>{contenidoPrivado}</AuthGuard>, {
			route: { pathname: '/proyecto' },
		});

		expect(screen.getByText('Contenido privado')).toBeInTheDocument();
		expect(mockRouter.push).not.toHaveBeenCalled();
	});

	it('oculta el contenido y redirige al inicio cuando no hay sesión', () => {
		renderWithProviders(<AuthGuard>{contenidoPrivado}</AuthGuard>, {
			route: { pathname: '/proyecto' },
		});

		expect(screen.queryByText('Contenido privado')).not.toBeInTheDocument();
		expect(mockRouter.push).toHaveBeenCalledWith('/');
	});

	it.each(['/login', '/register', '/login/callback'])(
		'permite la ruta pública %s sin sesión',
		(pathname) => {
			renderWithProviders(<AuthGuard>{contenidoPrivado}</AuthGuard>, {
				route: { pathname },
			});

			expect(screen.getByText('Contenido privado')).toBeInTheDocument();
			expect(mockRouter.push).not.toHaveBeenCalled();
		},
	);

	it('redirige cuando la sesión se cierra estando dentro', () => {
		useAuthStore.getState().setTokens('access', 'refresh');
		const { rerender } = renderWithProviders(<AuthGuard>{contenidoPrivado}</AuthGuard>, {
			route: { pathname: '/perfil' },
		});

		useAuthStore.getState().clearAuth();
		rerender(<AuthGuard>{contenidoPrivado}</AuthGuard>);

		expect(screen.queryByText('Contenido privado')).not.toBeInTheDocument();
		expect(mockRouter.push).toHaveBeenCalledWith('/');
	});
});
