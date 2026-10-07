import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/entities/integration', () => ({
	getIntegrationStatus: vi.fn(),
}));

vi.mock('@/entities/project', async (importOriginal) => {
	const actual = await importOriginal<typeof import('@/entities/project')>();
	return {
		...actual,
		getProjectGitHubStatus: vi.fn(),
		pushProjectToGitHub: vi.fn(),
	};
});

import { getIntegrationStatus } from '@/entities/integration';
import { getProjectGitHubStatus, pushProjectToGitHub } from '@/entities/project';
import { useProjectGithubRepo } from './useProjectGithubRepo';

const api = {
	getIntegrationStatus: vi.mocked(getIntegrationStatus),
	getProjectGitHubStatus: vi.mocked(getProjectGitHubStatus),
	pushProjectToGitHub: vi.mocked(pushProjectToGitHub),
};

async function flush() {
	await act(async () => {
		await Promise.resolve();
	});
}

describe('useProjectGithubRepo', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('no consulta nada si projectId es null y deja de cargar (not-linked por falta de integración)', async () => {
		// Act
		const { result } = renderHook(() => useProjectGithubRepo(null));
		await flush();

		// Assert
		expect(api.getIntegrationStatus).not.toHaveBeenCalled();
		expect(result.current.loading).toBe(false);
		expect(result.current.viewState).toBe('not-linked');
	});

	it('viewState es not-linked cuando GitHub no está conectado', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: false });
		api.getProjectGitHubStatus.mockResolvedValue({
			has_repository: false,
			sync_status: 'not_created',
		} as never);

		// Act
		const { result } = renderHook(() => useProjectGithubRepo('prj_01'));
		await flush();

		// Assert
		expect(result.current.viewState).toBe('not-linked');
	});

	it('viewState es create cuando está conectado pero sin repositorio', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: true });
		api.getProjectGitHubStatus.mockResolvedValue({
			has_repository: false,
			sync_status: 'not_created',
		} as never);

		// Act
		const { result } = renderHook(() => useProjectGithubRepo('prj_01'));
		await flush();

		// Assert
		expect(result.current.viewState).toBe('create');
	});

	it('viewState es synced cuando ya existe repositorio sincronizado', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: true });
		api.getProjectGitHubStatus.mockResolvedValue({
			has_repository: true,
			sync_status: 'synced',
		} as never);

		// Act
		const { result } = renderHook(() => useProjectGithubRepo('prj_01'));
		await flush();

		// Assert
		expect(result.current.viewState).toBe('synced');
	});

	it('viewState es syncing/failed según sync_status', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: true });
		api.getProjectGitHubStatus.mockResolvedValue({
			has_repository: true,
			sync_status: 'syncing',
		} as never);

		// Act
		const { result } = renderHook(() => useProjectGithubRepo('prj_01'));
		await flush();

		// Assert
		expect(result.current.viewState).toBe('syncing');
	});

	it('establece error cuando falla la consulta inicial', async () => {
		// Arrange
		api.getIntegrationStatus.mockRejectedValue(new Error('network down'));
		api.getProjectGitHubStatus.mockResolvedValue({
			has_repository: false,
			sync_status: 'not_created',
		} as never);

		// Act
		const { result } = renderHook(() => useProjectGithubRepo('prj_01'));
		await flush();

		// Assert
		expect(result.current.error).toBe('network down');
		expect(result.current.loading).toBe(false);
	});

	it('createRepo llama a pushProjectToGitHub con el nombre y visibilidad', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: true });
		api.getProjectGitHubStatus.mockResolvedValue({
			has_repository: false,
			sync_status: 'not_created',
		} as never);
		api.pushProjectToGitHub.mockResolvedValue({
			has_repository: true,
			sync_status: 'synced',
			repo_name: 'mi-repo',
		} as never);
		const { result } = renderHook(() => useProjectGithubRepo('prj_01'));
		await flush();

		// Act
		await act(async () => {
			await result.current.createRepo({ repo_name: 'mi-repo', is_public: true });
		});

		// Assert
		expect(api.pushProjectToGitHub).toHaveBeenCalledWith('prj_01', {
			repo_name: 'mi-repo',
			is_public: true,
		});
		expect(result.current.status?.repo_name).toBe('mi-repo');
	});

	it('sync llama a pushProjectToGitHub sin cuerpo', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: true });
		api.getProjectGitHubStatus.mockResolvedValue({
			has_repository: true,
			sync_status: 'synced',
		} as never);
		api.pushProjectToGitHub.mockResolvedValue({
			has_repository: true,
			sync_status: 'synced',
		} as never);
		const { result } = renderHook(() => useProjectGithubRepo('prj_01'));
		await flush();

		// Act
		await act(async () => {
			await result.current.sync();
		});

		// Assert
		expect(api.pushProjectToGitHub).toHaveBeenCalledWith('prj_01', {});
	});

	it('marca viewState=no-code cuando el push falla por falta de código (409)', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: true });
		api.getProjectGitHubStatus.mockResolvedValue({
			has_repository: false,
			sync_status: 'not_created',
		} as never);
		api.pushProjectToGitHub.mockRejectedValue(
			Object.assign(new Error('El proyecto no tiene funcionalidades implementadas'), {
				status: 409,
			}),
		);
		const { result } = renderHook(() => useProjectGithubRepo('prj_01'));
		await flush();

		// Act
		await act(async () => {
			await expect(result.current.sync()).rejects.toThrow();
		});

		// Assert
		expect(result.current.viewState).toBe('no-code');
	});

	it('establece un error genérico cuando el push falla por otra razón', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: true });
		api.getProjectGitHubStatus.mockResolvedValue({
			has_repository: false,
			sync_status: 'not_created',
		} as never);
		api.pushProjectToGitHub.mockRejectedValue(new Error('server error'));
		const { result } = renderHook(() => useProjectGithubRepo('prj_01'));
		await flush();

		// Act
		await act(async () => {
			await expect(result.current.sync()).rejects.toThrow('server error');
		});

		// Assert
		expect(result.current.error).toBe('server error');
	});

	it('refresh vuelve a consultar integración y estado', async () => {
		// Arrange
		api.getIntegrationStatus.mockResolvedValue({ provider: 'github', is_connected: true });
		api.getProjectGitHubStatus.mockResolvedValue({
			has_repository: false,
			sync_status: 'not_created',
		} as never);
		const { result } = renderHook(() => useProjectGithubRepo('prj_01'));
		await flush();

		// Act
		await act(async () => {
			await result.current.refresh();
		});

		// Assert
		expect(api.getIntegrationStatus).toHaveBeenCalledTimes(2);
	});
});
