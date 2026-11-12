import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test';
import { OAuthIntegration, type OAuthIntegrationProps } from './OAuthIntegration';

function renderizar(props: Partial<OAuthIntegrationProps> = {}) {
	const onConnect = vi.fn();
	const onDisconnect = vi.fn();
	const utils = renderWithProviders(
		<OAuthIntegration
			label='GitHub'
			icon={<svg aria-hidden='true' />}
			loading={false}
			actionLoading={false}
			isConnected={false}
			onConnect={onConnect}
			onDisconnect={onDisconnect}
			{...props}
		/>,
	);
	return { ...utils, onConnect, onDisconnect };
}

describe('OAuthIntegration', () => {
	it('mientras verifica no muestra botón de acción', () => {
		renderizar({ loading: true });

		expect(screen.getByText('Verificando...')).toBeInTheDocument();
		expect(screen.queryByRole('button')).not.toBeInTheDocument();
	});

	it('sin conexión ofrece conectar', async () => {
		const { user, onConnect, onDisconnect } = renderizar();

		expect(screen.getByText('No conectado')).toBeInTheDocument();
		await user.click(screen.getByRole('button', { name: 'Conectar' }));

		expect(onConnect).toHaveBeenCalledOnce();
		expect(onDisconnect).not.toHaveBeenCalled();
	});

	it('conectado muestra el usuario y ofrece desconectar', async () => {
		const { user, onConnect, onDisconnect } = renderizar({
			isConnected: true,
			username: 'octocat',
		});

		expect(screen.getByText('@octocat')).toBeInTheDocument();
		await user.click(screen.getByRole('button', { name: 'Desconectar' }));

		expect(onDisconnect).toHaveBeenCalledOnce();
		expect(onConnect).not.toHaveBeenCalled();
	});

	it('conectado sin nombre de usuario no muestra "@"', () => {
		renderizar({ isConnected: true, username: null });

		expect(screen.queryByText(/@/)).not.toBeInTheDocument();
	});

	it('bloquea el botón mientras procesa la acción', async () => {
		const { user, onConnect } = renderizar({ actionLoading: true });

		const boton = screen.getByRole('button', { name: 'Procesando...' });
		await user.click(boton);

		expect(boton).toBeDisabled();
		expect(onConnect).not.toHaveBeenCalled();
	});
});
