import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ProjectDeployStatusResponse } from '@/entities/deploy';
import { DeployResultPanel } from './DeployResultPanel';

vi.mock('@/entities/deploy', () => ({
	deleteDeployment: vi.fn(),
}));

vi.mock('@/shared/ui/toast/toast', () => ({
	toast: {
		success: vi.fn(),
		error: vi.fn(),
		info: vi.fn(),
	},
}));

import { deleteDeployment } from '@/entities/deploy';
import { toast } from '@/shared/ui/toast/toast';

const mockDeleteDeployment = vi.mocked(deleteDeployment);
const mockToast = vi.mocked(toast);

function makeStatus(
	overrides: Partial<ProjectDeployStatusResponse> = {},
): ProjectDeployStatusResponse {
	return {
		service_id: 'srv-123',
		service_name: 'kosmo-api',
		deploy_url: 'https://kosmo-api.up.railway.app',
		status: 'ready',
		last_deploy_at: '2026-03-30T12:00:00Z',
		error_message: null,
		error_log_url: null,
		...overrides,
	};
}

describe('DeployResultPanel', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('abre el ModalConfirm al hacer clic en "Eliminar despliegue" sin invocar deleteDeployment de inmediato', () => {
		render(
			<DeployResultPanel
				projectId='prj_123'
				status={makeStatus()}
				error={null}
				onRedeploy={vi.fn()}
			/>,
		);

		const deleteBtn = screen.getByRole('button', { name: /eliminar despliegue/i });
		expect(deleteBtn).toBeInTheDocument();

		fireEvent.click(deleteBtn);

		const dialog = screen.getByRole('dialog');
		expect(dialog).toBeInTheDocument();
		expect(
			screen.getByRole('heading', { name: 'Eliminar despliegue' }),
		).toBeInTheDocument();
		expect(
			screen.getByText(
				'¿Estás seguro de que deseas eliminar el despliegue? Esta acción eliminará el servicio en la nube.',
			),
		).toBeInTheDocument();

		expect(mockDeleteDeployment).not.toHaveBeenCalled();
	});

	it('cierra el ModalConfirm al presionar Cancelar y no ejecuta la eliminación', () => {
		render(
			<DeployResultPanel
				projectId='prj_123'
				status={makeStatus()}
				error={null}
				onRedeploy={vi.fn()}
			/>,
		);

		fireEvent.click(screen.getByRole('button', { name: /eliminar despliegue/i }));
		expect(screen.getByRole('dialog')).toBeInTheDocument();

		const cancelBtn = screen.getByRole('button', { name: /cancelar/i });
		fireEvent.click(cancelBtn);

		expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
		expect(mockDeleteDeployment).not.toHaveBeenCalled();
	});

	it('ejecuta deleteDeployment y onDeleteSuccess tras confirmar la eliminación en el modal', async () => {
		const onDeleteSuccess = vi.fn();
		mockDeleteDeployment.mockResolvedValueOnce({
			project_id: 'prj_123',
			status: 'deleted',
		});

		render(
			<DeployResultPanel
				projectId='prj_123'
				status={makeStatus()}
				error={null}
				onRedeploy={vi.fn()}
				onDeleteSuccess={onDeleteSuccess}
			/>,
		);

		fireEvent.click(screen.getByRole('button', { name: /eliminar despliegue/i }));

		// El botón de confirmación en el modal tiene el texto "Eliminar"
		const confirmBtn = screen.getByRole('button', { name: 'Eliminar' });
		fireEvent.click(confirmBtn);

		expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
		expect(mockDeleteDeployment).toHaveBeenCalledWith('prj_123');

		await waitFor(() => {
			expect(mockToast.success).toHaveBeenCalledWith(
				'Despliegue eliminado exitosamente',
			);
			expect(onDeleteSuccess).toHaveBeenCalledTimes(1);
		});
	});

	it('muestra toast.error si la llamada a deleteDeployment falla', async () => {
		mockDeleteDeployment.mockRejectedValueOnce(new Error('Network error'));

		render(
			<DeployResultPanel
				projectId='prj_123'
				status={makeStatus()}
				error={null}
				onRedeploy={vi.fn()}
			/>,
		);

		fireEvent.click(screen.getByRole('button', { name: /eliminar despliegue/i }));
		const confirmBtn = screen.getByRole('button', { name: 'Eliminar' });
		fireEvent.click(confirmBtn);

		await waitFor(() => {
			expect(mockToast.error).toHaveBeenCalledWith(
				'Error al eliminar el despliegue',
			);
		});
	});

	it('muestra mensaje informativo durante el estado building y permite cambiar de pestaña', () => {
		render(
			<DeployResultPanel
				projectId='prj_123'
				status={makeStatus({ status: 'building' })}
				error={null}
			/>,
		);

		expect(
			screen.getByText('Construyendo y desplegando tu aplicación...'),
		).toBeInTheDocument();
		expect(
			screen.getByText(
				/Los despliegues en Railway suelen tardar entre 4 y 7 minutos. Puedes cambiar de pestaña con tranquilidad/i,
			),
		).toBeInTheDocument();
	});

	it('invoca onRefresh al hacer clic en el botón de actualizar estado', () => {
		const onRefresh = vi.fn();

		render(
			<DeployResultPanel
				projectId='prj_123'
				status={makeStatus({ status: 'building' })}
				error={null}
				onRefresh={onRefresh}
			/>,
		);

		const refreshBtn = screen.getByRole('button', { name: /actualizar estado/i });
		expect(refreshBtn).toBeInTheDocument();

		fireEvent.click(refreshBtn);
		expect(onRefresh).toHaveBeenCalledTimes(1);
	});
});
