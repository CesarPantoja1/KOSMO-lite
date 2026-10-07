import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useImplementationStore } from '@/entities/implementation';
import { useCharacteristicStore } from '@/entities/characteristic';
import { useProjectStore } from '@/entities/project';
import { ImplementationSummaryPage } from './ImplementationSummaryPage';

vi.mock('next/navigation', () => ({
	useRouter: () => ({
		back: vi.fn(),
		push: vi.fn(),
	}),
}));

vi.mock('@/features/github-sync', () => ({
	useProjectGithubRepo: () => ({
		viewState: 'synced',
		status: { has_repository: true },
		loading: false,
		error: null,
		createRepo: vi.fn(),
		sync: vi.fn(),
	}),
}));

vi.mock('@/entities/deploy', () => ({
	useDeployStatus: () => ({
		status: null,
		error: null,
		deploying: false,
		deploy: vi.fn(),
		refresh: vi.fn(),
	}),
}));

vi.mock('@/entities/integration', () => ({
	useRailwayOAuth: () => ({
		isConnected: true,
		loading: false,
		actionLoading: false,
		refresh: vi.fn(),
		handleConnect: vi.fn(),
	}),
}));

vi.mock('@/widgets', () => ({
	GestionRepositorioGitHub: () => <div data-testid='github-widget' />,
}));

const mockSummary = {
	featureId: 'feat-01',
	featureTitle: 'Autenticación',
	featureDisplayId: 'C01',
	status: 'completed' as const,
	metrics: [
		{
			value: '5',
			label: 'Archivos generados',
			icon: 'features' as const,
			iconBg: 'bg-ai-100',
			iconColor: 'text-ai-600',
		},
	],
	technologies: ['React', 'Next.js'],
	nextSteps: ['Probar endpoints'],
	generatedAt: '2026-09-29T10:00:00Z',
	generatedFiles: ['src/auth.ts'],
};

describe('ImplementationSummaryPage', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		useImplementationStore.setState({
			summary: null,
			status: 'idle',
			progress: null,
			currentThought: null,
			logs: [],
			errorMessage: null,
			implementations: {},
			requiresReviewByFeature: {},
		});
		useCharacteristicStore.setState({
			currentCharacteristics: [],
			selectedId: null,
		});
		useProjectStore.setState({
			currentProject: { id: 'prj-123', name: 'KOSMO Project' } as never,
		});
	});

	it('muestra "No hay resumen disponible" cuando no hay summary ni características', () => {
		render(<ImplementationSummaryPage />);
		expect(screen.getByText('No hay resumen disponible.')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: /volver a implementación/i })).toBeInTheDocument();
	});

	it('muestra el resumen inmediatamente si el summary ya está en el store (persistido)', () => {
		useImplementationStore.setState({ summary: mockSummary });

		render(<ImplementationSummaryPage />);

		expect(screen.getByText('Resumen de implementación')).toBeInTheDocument();
		expect(screen.getByText('Archivos generados')).toBeInTheDocument();
		expect(screen.getByText('5')).toBeInTheDocument();
		expect(screen.getByText('React')).toBeInTheDocument();
	});

	it('intenta rehidratar la implementación cuando summary es null pero existe característica activa', async () => {
		const loadMock = vi.fn().mockImplementation(async () => {
			useImplementationStore.setState({ summary: mockSummary });
		});
		useImplementationStore.setState({ loadImplementation: loadMock });
		useCharacteristicStore.setState({
			selectedId: 'feat-01',
			currentCharacteristics: [
				{
					id: 'feat-01',
					title: 'Autenticación',
					display_id: 'C01',
					description: 'Login',
					origin: 'Desc',
				} as never,
			],
		});

		render(<ImplementationSummaryPage />);

		await waitFor(() => {
			expect(loadMock).toHaveBeenCalledWith('feat-01', 'Autenticación', 'C01');
		});
	});
});
