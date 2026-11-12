import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useProjectStore } from '@/entities/project';
import { useAppStore } from '@/features/app-state';
import type { User } from '@/shared/model/auth-store';
import { useAuthStore } from '@/shared/model/auth-store';
import {
	HttpResponse,
	apiUrl,
	crearProyecto,
	crearUsuario,
	http,
	mockRouter,
	renderWithProviders,
	server,
} from '@/test';
import { UserSection } from './UserSection';

function iniciarSesion() {
	useAuthStore.getState().setTokens('access', 'refresh');
	useProjectStore.setState({ projects: [crearProyecto()] });
}

function contarLogout() {
	const llamadas: unknown[] = [];
	server.use(
		http.post(apiUrl('/api/v1/auth/logout'), async ({ request }) => {
			llamadas.push(await request.json());
			return new HttpResponse(null, { status: 204 });
		}),
	);
	return llamadas;
}

const renderizar = (user: User | null, isSidebarExpanded = true) =>
	renderWithProviders(<UserSection user={user} isSidebarExpanded={isSidebarExpanded} />);

describe('UserSection', () => {
	describe('con cambios sin guardar', () => {
		it('pide confirmación antes de cerrar sesión', async () => {
			iniciarSesion();
			useAppStore.setState({ hasUnsavedChanges: true });
			const llamadas = contarLogout();
			const { user } = renderizar(crearUsuario());

			await user.click(screen.getByRole('button', { name: 'Cerrar sesión' }));

			expect(screen.getByRole('dialog', { name: 'Cerrar sesión' })).toBeInTheDocument();
			expect(llamadas).toHaveLength(0);
			expect(useAuthStore.getState().accessToken).toBe('access');
		});

		it('cancelar mantiene la sesión', async () => {
			iniciarSesion();
			useAppStore.setState({ hasUnsavedChanges: true });
			const { user } = renderizar(crearUsuario());
			await user.click(screen.getByRole('button', { name: 'Cerrar sesión' }));

			await user.click(screen.getByRole('button', { name: 'Cancelar' }));

			expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
			expect(useAuthStore.getState().accessToken).toBe('access');
		});

		it('confirmar cierra la sesión', async () => {
			iniciarSesion();
			useAppStore.setState({ hasUnsavedChanges: true });
			const { user } = renderizar(crearUsuario());
			await user.click(screen.getByRole('button', { name: 'Cerrar sesión' }));

			const dialogo = screen.getByRole('dialog');
			await user.click(
				Array.from(dialogo.querySelectorAll('button')).find(
					(b) => b.textContent === 'Cerrar sesión',
				)!,
			);

			await waitFor(() => expect(mockRouter.push).toHaveBeenCalledWith('/'));
			expect(useAuthStore.getState().accessToken).toBeNull();
		});
	});

	describe('barra contraída', () => {
		const usuarioConAvatar = () =>
			crearUsuario({ name: 'Ada', avatar_url: 'https://x.dev/ada.png' });

		it('abre un menú con Perfil y Cerrar sesión al pulsar el avatar', async () => {
			const { user } = renderizar(usuarioConAvatar(), false);
			expect(screen.queryByRole('button', { name: 'Perfil' })).not.toBeInTheDocument();

			await user.click(screen.getByRole('button', { name: 'Ada' }));

			expect(screen.getByRole('button', { name: 'Perfil' })).toBeInTheDocument();
			expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeInTheDocument();
		});

		it('elegir Perfil navega y cierra el menú', async () => {
			const { user } = renderizar(usuarioConAvatar(), false);
			await user.click(screen.getByRole('button', { name: 'Ada' }));

			await user.click(screen.getByRole('button', { name: 'Perfil' }));

			expect(mockRouter.push).toHaveBeenCalledWith('/perfil');
			expect(screen.queryByRole('button', { name: 'Perfil' })).not.toBeInTheDocument();
		});
	});
});
