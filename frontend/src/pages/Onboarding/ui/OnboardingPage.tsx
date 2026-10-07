'use client';

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Logo } from '@/shared/ui';
import { useOnboardingStatus } from '../model/useOnboardingStatus';
import { ApiKeyStep } from './ApiKeyStep';
import { GitHubStep } from './GitHubStep';
import { RailwayStep } from './RailwayStep';
import { StepIndicator } from './StepIndicator';

const STEPS = [
	{ key: 'apikey', label: 'API Key', required: true },
	{ key: 'github', label: 'GitHub', required: true },
	{ key: 'railway', label: 'Railway', required: true },
] as const;

function OnboardingPage() {
	const router = useRouter();
	const { github, railway, hasApiKey, refresh } = useOnboardingStatus();
	const [currentStep, setCurrentStep] = useState(0);
	const [githubConnected, setGithubConnected] = useState(github?.is_connected ?? false);
	const [railwayConnected, setRailwayConnected] = useState(
		railway?.is_connected ?? false,
	);

	const steps = STEPS.map((step) => ({
		...step,
		completed:
			step.key === 'apikey'
				? hasApiKey
				: step.key === 'github'
					? githubConnected
					: step.key === 'railway'
						? railwayConnected
						: false,
	}));

	const handleNext = useCallback(() => {
		if (currentStep === 0 && !hasApiKey) return;
		if (currentStep === 1 && !githubConnected) return;
		if (currentStep === 2 && !railwayConnected) return;

		if (currentStep < STEPS.length - 1) {
			setCurrentStep((prev) => prev + 1);
		} else {
			refresh();
			router.push('/proyecto');
		}
	}, [currentStep, hasApiKey, githubConnected, railwayConnected, refresh, router]);

	const handleGitHubStatusChange = useCallback((connected: boolean) => {
		setGithubConnected(connected);
	}, []);

	const handleRailwayStatusChange = useCallback((connected: boolean) => {
		setRailwayConnected(connected);
	}, []);

	return (
		<div className='min-h-screen flex items-center justify-center p-6'>
			<div className='w-full max-w-2xl'>
				<div className='mb-8 flex flex-col items-center gap-3'>
					<Logo size={40} />
					<h1 className='text-2xl font-bold text-neutral-800'>Bienvenido a KOSMO</h1>
					<p className='text-neutral-500 text-sm text-center max-w-md'>
						Configura tu cuenta para empezar. Cada paso es obligatorio para usar
						KOSMO.
					</p>
				</div>

				<div className='flex justify-center mb-8'>
					<StepIndicator
						currentStep={currentStep}
						totalSteps={STEPS.length}
						steps={steps}
					/>
				</div>

				<div className='bg-neutral-0 border border-neutral-200 rounded-2xl shadow-sm p-8 mb-6'>
					{currentStep === 0 && <ApiKeyStep />}
					{currentStep === 1 && <GitHubStep onStatusChange={handleGitHubStatusChange} />}
					{currentStep === 2 && (
						<RailwayStep onStatusChange={handleRailwayStatusChange} />
					)}
				</div>

				<div className='flex items-center justify-center'>
					<button type='button' onClick={handleNext} className='btn btn-primary'>
						{currentStep === STEPS.length - 1 ? 'Continuar a KOSMO' : 'Continuar'}
					</button>
				</div>

				{!hasApiKey && (
					<p className='text-center text-neutral-400 text-xs mt-4'>
						Paso obligatorio: configura tu API Key de IA para continuar.
					</p>
				)}
			</div>
		</div>
	);
}

export { OnboardingPage };
