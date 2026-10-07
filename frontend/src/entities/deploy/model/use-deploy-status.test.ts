import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/api', () => ({
	getDeployStatus: vi.fn(),
	startDeployRailway: vi.fn(),
}));

import { getDeployStatus, startDeployRailway } from '../api/api';
import { useDeployStatus } from './use-deploy-status';
import type { ProjectDeployStatusResponse } from './types';

const api = {
	getDeployStatus: vi.mocked(getDeployStatus),
	startDeployRailway: vi.mocked(startDeployRailway),
};

function makeStatus(overrides: Partial<ProjectDeployStatusResponse> = {}): ProjectDeployStatusResponse {
	return {
		service_id: null,
		service_name: null,
		deploy_url: null,
		status: 'idle',
		last_deploy_at: null,
		error_message: null,
		error_log_url: null,
		...overrides,
	};
}

async function flushInit() {
	await act(async () => {
		await vi.advanceTimersByTimeAsync(0);
	});
}

describe('useDeployStatus', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
	});

	it('no consulta el estado si projectId es null y deja loading en false', async () => {
		// Act
		const { result } = renderHook(() => useDeployStatus(null));

		// Assert
		await flushInit();
		expect(result.current.loading).toBe(false);
		expect(api.getDeployStatus).not.toHaveBeenCalled();
		expect(result.current.status).toBeNull();
	});

	it('consulta el estado al montar y lo expone', async () => {
		// Arrange
		api.getDeployStatus.mockResolvedValue(makeStatus({ status: 'ready' }));

		// Act
		const { result } = renderHook(() => useDeployStatus('prj_01'));

		// Assert
		await flushInit();
		expect(result.current.loading).toBe(false);
		expect(result.current.status?.status).toBe('ready');
		expect(api.getDeployStatus).toHaveBeenCalledWith('prj_01');
	});

	it('establece un mensaje de error si falla la consulta inicial', async () => {
		// Arrange
		api.getDeployStatus.mockRejectedValue(new Error('network error'));

		// Act
		const { result } = renderHook(() => useDeployStatus('prj_01'));

		// Assert
		await flushInit();
		expect(result.current.loading).toBe(false);
		expect(result.current.error).toBe('network error');
	});

	it('no reprograma polling cuando el estado es terminal (ready)', async () => {
		// Arrange
		api.getDeployStatus.mockResolvedValue(makeStatus({ status: 'ready' }));
		const { result } = renderHook(() => useDeployStatus('prj_01'));
		await flushInit();
		expect(result.current.loading).toBe(false);

		// Act
		await act(async () => {
			await vi.advanceTimersByTimeAsync(10_000);
		});

		// Assert
		expect(api.getDeployStatus).toHaveBeenCalledTimes(1);
	});

	it('reprograma polling cada 5s cuando el estado no es terminal (building)', async () => {
		// Arrange
		api.getDeployStatus.mockResolvedValue(makeStatus({ status: 'building' }));
		const { result } = renderHook(() => useDeployStatus('prj_01'));
		await flushInit();
		expect(result.current.loading).toBe(false);

		// Act
		await act(async () => {
			await vi.advanceTimersByTimeAsync(5_000);
		});

		// Assert
		expect(api.getDeployStatus).toHaveBeenCalledTimes(2);
	});

	it('deploy inicia el despliegue y actualiza el estado', async () => {
		// Arrange
		api.getDeployStatus.mockResolvedValue(makeStatus({ status: 'idle' }));
		api.startDeployRailway.mockResolvedValue(makeStatus({ status: 'building', service_id: 'srv_1' }));
		const { result } = renderHook(() => useDeployStatus('prj_01'));
		await flushInit();
		expect(result.current.loading).toBe(false);

		// Act
		await act(async () => {
			await result.current.deploy({ service_name: 'kosmo-app' });
		});

		// Assert
		expect(api.startDeployRailway).toHaveBeenCalledWith('prj_01', { service_name: 'kosmo-app' });
		expect(result.current.status?.status).toBe('building');
		expect(result.current.deploying).toBe(false);
	});

	it('deploy establece un error si falla el inicio del despliegue', async () => {
		// Arrange
		api.getDeployStatus.mockResolvedValue(makeStatus({ status: 'idle' }));
		api.startDeployRailway.mockRejectedValue(new Error('deploy failed'));
		const { result } = renderHook(() => useDeployStatus('prj_01'));
		await flushInit();
		expect(result.current.loading).toBe(false);

		// Act
		await act(async () => {
			await result.current.deploy();
		});

		// Assert
		expect(result.current.error).toBe('deploy failed');
	});

	it('refresh vuelve a consultar el estado', async () => {
		// Arrange
		api.getDeployStatus.mockResolvedValue(makeStatus({ status: 'ready' }));
		const { result } = renderHook(() => useDeployStatus('prj_01'));
		await flushInit();
		expect(result.current.loading).toBe(false);

		// Act
		await act(async () => {
			await result.current.refresh();
		});

		// Assert
		expect(api.getDeployStatus).toHaveBeenCalledTimes(2);
	});

	it('mantiene el sondeo activo incluso si ocurre un error transitorio de red durante building', async () => {
		// Arrange
		api.getDeployStatus
			.mockResolvedValueOnce(makeStatus({ status: 'building' })) // init
			.mockRejectedValueOnce(new Error('Network glitch')) // primer poll (5s)
			.mockResolvedValueOnce(makeStatus({ status: 'ready' })); // segundo poll

		const { result } = renderHook(() => useDeployStatus('prj_01'));
		await flushInit();
		expect(result.current.loading).toBe(false);

		// Act: avanza al primer poll (falla con error)
		await act(async () => {
			await vi.advanceTimersByTimeAsync(5_000);
		});
		expect(result.current.error).toBe('Network glitch');
		expect(api.getDeployStatus).toHaveBeenCalledTimes(2);

		// Act: avanza al siguiente poll (se recupera a ready)
		await act(async () => {
			await vi.advanceTimersByTimeAsync(5_000);
		});

		// Assert
		expect(api.getDeployStatus).toHaveBeenCalledTimes(3);
		expect(result.current.status?.status).toBe('ready');
		expect(result.current.error).toBeNull();
	});

	it('revalida de inmediato al recibir evento de visibilidad visible si no es terminal', async () => {
		// Arrange
		api.getDeployStatus.mockResolvedValue(makeStatus({ status: 'building' }));
		const { result } = renderHook(() => useDeployStatus('prj_01'));
		await flushInit();
		expect(api.getDeployStatus).toHaveBeenCalledTimes(1);

		// Act: dispara evento de visibilidad
		await act(async () => {
			document.dispatchEvent(new Event('visibilitychange'));
		});

		// Assert: se consultó de inmediato sin esperar el temporizador
		expect(api.getDeployStatus).toHaveBeenCalledTimes(2);
		expect(result.current.status?.status).toBe('building');
	});
});

