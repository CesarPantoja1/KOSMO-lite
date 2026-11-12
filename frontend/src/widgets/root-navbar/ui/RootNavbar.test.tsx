import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '@/shared/model/auth-store';
import { crearUsuario, mockRouter, renderWithProviders } from '@/test';
import { RootNavbar } from './RootNavbar';

describe('RootNavbar', () => {
	describe('sin sesión', () => {
		it('"Comenzar" lleva a los proyectos por defecto', async () => {
			const { user } = renderWithProviders(<RootNavbar />);

			await user.click(screen.getByRole('button', { name: 'Comenzar' }));

			expect(mockRouter.push).toHaveBeenCalledWith('/proyecto');
		});

		it('"Comenzar" usa la acción personalizada si se indica (p. ej. abrir el login)', async () => {
			const onComenzar = vi.fn();
			const { user } = renderWithProviders(<RootNavbar onComenzar={onComenzar} />);

			await user.click(screen.getByRole('button', { name: 'Comenzar' }));

			expect(onComenzar).toHaveBeenCalledOnce();
			expect(mockRouter.push).not.toHaveBeenCalled();
		});
	});

	it('con sesión muestra el acceso a "Mi Cuenta"', () => {
		useAuthStore.getState().setUser(crearUsuario());

		renderWithProviders(<RootNavbar />);

		expect(screen.getByRole('link', { name: 'Mi Cuenta' })).toHaveAttribute(
			'href',
			'/perfil',
		);
		expect(screen.queryByRole('button', { name: 'Comenzar' })).not.toBeInTheDocument();
	});
});
