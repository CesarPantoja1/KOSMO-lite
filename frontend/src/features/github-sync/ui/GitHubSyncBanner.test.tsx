import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GitHubSyncBanner } from './GitHubSyncBanner';

const mockUseProjectGithubRepo = vi.fn();
const mockPushProjectToGitHub = vi.fn();

vi.mock('../model/useProjectGithubRepo', () => ({
	useProjectGithubRepo: (projectId: string | null) => mockUseProjectGithubRepo(projectId),
}));

vi.mock('@/entities/project', async (importOriginal) => {
	const actual = await importOriginal<typeof import('@/entities/project')>();
	return {
		...actual,
		pushProjectToGitHub: (...args: unknown[]) => mockPushProjectToGitHub(...args),
		useProjectStore: (selector: (s: unknown) => unknown) =>
			selector({
				currentProject: { id: 'prj_1', name: 'Ferretería' },
				githubSyncingProjectId: null,
				setGithubSyncing: vi.fn(),
			}),
	};
});

describe('GitHubSyncBanner', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.useFakeTimers();
	});

	it('no renderiza nada cuando no está sincronizando', () => {
		mockUseProjectGithubRepo.mockReturnValue({
			viewState: 'create',
			status: null,
			error: null,
			refresh: vi.fn(),
		});

		const { container } = render(<GitHubSyncBanner />);
		expect(container).toBeEmptyDOMElement();
	});

	it('muestra el banner inline mientras está en estado syncing con el nombre del repo', () => {
		mockUseProjectGithubRepo.mockReturnValue({
			viewState: 'syncing',
			status: { repo_name: 'kosmo-ferreteria' },
			error: null,
			refresh: vi.fn(),
		});

		render(<GitHubSyncBanner />);
		expect(screen.getByText(/creando repositorio en github:/i)).toBeInTheDocument();
		expect(screen.getByText('kosmo-ferreteria')).toBeInTheDocument();
		expect(screen.getByText(/puedes continuar redactando o avanzando sin esperar/i)).toBeInTheDocument();
	});

	it('muestra estado completado y se auto-destruye tras 4 segundos', () => {
		// Primer render en syncing
		mockUseProjectGithubRepo.mockReturnValue({
			viewState: 'syncing',
			status: { repo_name: 'kosmo-ferreteria' },
			error: null,
			refresh: vi.fn(),
		});

		const { rerender, container } = render(<GitHubSyncBanner />);
		expect(screen.getByText(/creando repositorio en github:/i)).toBeInTheDocument();

		// Segundo render transiciona a synced
		mockUseProjectGithubRepo.mockReturnValue({
			viewState: 'synced',
			status: {
				repo_url: 'https://github.com/user/kosmo-ferreteria',
				repo_name: 'kosmo-ferreteria',
			},
			error: null,
			refresh: vi.fn(),
		});

		rerender(<GitHubSyncBanner />);
		expect(screen.getByText(/repositorio listo en github:/i)).toBeInTheDocument();
		expect(screen.getByRole('link', { name: /ver en github/i })).toHaveAttribute(
			'href',
			'https://github.com/user/kosmo-ferreteria',
		);

		// Avanzar 4 segundos
		act(() => {
			vi.advanceTimersByTime(4000);
		});

		expect(container).toBeEmptyDOMElement();
	});

	it('muestra estado fallido con botón de reintentar y permite reintentar', async () => {
		const refreshMock = vi.fn();
		mockPushProjectToGitHub.mockResolvedValue({});

		// Primer render en syncing
		mockUseProjectGithubRepo.mockReturnValue({
			viewState: 'syncing',
			status: { repo_name: 'kosmo-ferreteria' },
			error: null,
			refresh: refreshMock,
		});

		const { rerender } = render(<GitHubSyncBanner />);

		// Transición a failed
		mockUseProjectGithubRepo.mockReturnValue({
			viewState: 'failed',
			status: { suggested_repo_name: 'kosmo-ferreteria' },
			error: 'Token de GitHub revocado',
			refresh: refreshMock,
		});

		rerender(<GitHubSyncBanner />);
		expect(screen.getByText(/no se pudo inicializar en github:/i)).toBeInTheDocument();
		expect(screen.getByText('Token de GitHub revocado')).toBeInTheDocument();

		const retryBtn = screen.getByRole('button', { name: /reintentar/i });
		await act(async () => {
			fireEvent.click(retryBtn);
		});

		expect(mockPushProjectToGitHub).toHaveBeenCalledWith('prj_1', {
			repo_name: 'kosmo-ferreteria',
			is_public: true,
		});
		expect(refreshMock).toHaveBeenCalled();
	});
});
