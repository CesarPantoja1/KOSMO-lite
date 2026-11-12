import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PreconditionState } from '@/entities/deploy';
import { renderWithProviders } from '@/test';
import { DeployPreconditionPanel } from './DeployPreconditionPanel';

type Props = Parameters<typeof DeployPreconditionPanel>[0];

function renderizar(props: Partial<Props> = {}) {
	const onDeploy = vi.fn();
	const utils = renderWithProviders(
		<DeployPreconditionPanel
			precondition='ready'
			onDeploy={onDeploy}
			deploying={false}
			{...props}
		/>,
	);
	return { ...utils, onDeploy };
}

describe('DeployPreconditionPanel', () => {
	it.each<[PreconditionState, string]>([
		['loading', 'Verificando condiciones de despliegue...'],
		['github-not-linked', 'Repositorio no vinculado'],
		['github-not-synced', 'Sincroniza tu código primero'],
		['railway-not-linked', 'Vincula tu cuenta de Railway'],
	])(
		'con la precondición "%s" explica qué falta y no permite desplegar',
		(precondition, texto) => {
			renderizar({ precondition });

			expect(screen.getByText(texto)).toBeInTheDocument();
			expect(
				screen.queryByRole('button', { name: /Desplegar en Railway/ }),
			).not.toBeInTheDocument();
		},
	);

	describe('Railway sin vincular', () => {
		it('sin acción propia enlaza al perfil', () => {
			renderizar({ precondition: 'railway-not-linked' });

			expect(screen.getByRole('link', { name: 'Conectar Railway' })).toHaveAttribute(
				'href',
				'/perfil',
			);
		});

		it('con acción propia conecta directamente y muestra el progreso', async () => {
			const onConnectRailway = vi.fn();
			const { user, rerender } = renderizar({
				precondition: 'railway-not-linked',
				onConnectRailway,
			});

			await user.click(screen.getByRole('button', { name: 'Conectar Railway' }));
			expect(onConnectRailway).toHaveBeenCalledOnce();

			rerender(
				<DeployPreconditionPanel
					precondition='railway-not-linked'
					onDeploy={vi.fn()}
					deploying={false}
					onConnectRailway={onConnectRailway}
					connectingRailway
				/>,
			);
			expect(screen.getByRole('button', { name: /Conectando/ })).toBeDisabled();
		});
	});

	describe('listo para desplegar', () => {
		it('despliega con un clic', async () => {
			const { user, onDeploy } = renderizar();

			await user.click(screen.getByRole('button', { name: /Desplegar en Railway/ }));

			expect(onDeploy).toHaveBeenCalledOnce();
		});

		it('bloquea el botón mientras inicia el despliegue', () => {
			renderizar({ deploying: true });

			expect(screen.getByRole('button', { name: /Iniciando despliegue/ })).toBeDisabled();
		});

		it('muestra el error del despliegue y ofrece reconectar Railway', async () => {
			const onConnectRailway = vi.fn();
			const { user } = renderizar({
				deployError: 'El token de Railway no tiene permisos de escritura',
				onConnectRailway,
			});

			expect(screen.getByText('Error al iniciar el despliegue')).toBeInTheDocument();
			expect(
				screen.getByText('El token de Railway no tiene permisos de escritura'),
			).toBeInTheDocument();
			await user.click(
				screen.getByRole('button', { name: 'Reconectar Railway con nuevos permisos' }),
			);

			expect(onConnectRailway).toHaveBeenCalledOnce();
		});

		it('sin acción de reconexión solo muestra el error', () => {
			renderizar({ deployError: 'Fallo' });

			expect(
				screen.queryByRole('button', { name: /Reconectar/ }),
			).not.toBeInTheDocument();
		});
	});
});
