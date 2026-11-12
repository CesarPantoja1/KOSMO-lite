import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test';
import { AuthModal } from './AuthModal';

function renderizar(props: Partial<Parameters<typeof AuthModal>[0]> = {}) {
	const onClose = vi.fn();
	const utils = renderWithProviders(<AuthModal isOpen onClose={onClose} {...props} />);
	return { ...utils, onClose };
}

describe('AuthModal', () => {
	it('no renderiza nada cerrado', () => {
		renderizar({ isOpen: false });

		expect(screen.queryByText('Iniciar sesión')).not.toBeInTheDocument();
	});

	it('abre mostrando el inicio de sesión', () => {
		renderizar();

		expect(screen.getByText('Iniciar sesión')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Entrar' })).toBeInTheDocument();
	});

	it('alterna entre inicio de sesión y registro', async () => {
		const { user } = renderizar();

		await user.click(screen.getByRole('button', { name: '¿No tienes cuenta? Regístrate' }));
		expect(screen.getByText('Crear cuenta')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Registrarse' })).toBeInTheDocument();

		await user.click(screen.getByRole('button', { name: '¿Ya tienes cuenta? Inicia sesión' }));
		expect(screen.getByText('Iniciar sesión')).toBeInTheDocument();
	});

	it('transmite el aviso de sesión expirada al login', () => {
		renderizar({ sessionExpired: true });

		expect(screen.getByText(/Tu sesión ha expirado/)).toBeInTheDocument();
	});

	it('se cierra al hacer clic en el fondo, pero no al hacer clic dentro', async () => {
		const { user, onClose, container } = renderizar();

		await user.click(screen.getByText('Iniciar sesión'));
		expect(onClose).not.toHaveBeenCalled();

		await user.click(container.querySelector('.fixed')!);
		expect(onClose).toHaveBeenCalledOnce();
	});
});
