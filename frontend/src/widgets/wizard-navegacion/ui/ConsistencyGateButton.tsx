'use client';

import { useRouter } from 'next/navigation';

import {
	CONSISTENCY_REVIEW_ROUTES,
	firstPhaseToReview,
	sumPhaseStatus,
} from '@/entities/consistency';
import type { ConsistencyStatusResponse } from '@/entities/consistency';

import { useAppStore } from '@/features/app-state';

interface ConsistencyGateButtonProps {
	status: ConsistencyStatusResponse | null;
}

export function ConsistencyGateButton({ status }: ConsistencyGateButtonProps) {
	const router = useRouter();

	const pending = sumPhaseStatus(status, 'pending');
	const evaluating = sumPhaseStatus(status, 'evaluating');
	const failed = sumPhaseStatus(status, 'failed');

	if (pending === 0 && evaluating === 0 && failed === 0) return null;

	const goToReview = () => {
		const { hasUnsavedChanges, setPendingNavigationPath } = useAppStore.getState();
		const route = CONSISTENCY_REVIEW_ROUTES[firstPhaseToReview(status)];
		if (hasUnsavedChanges) {
			setPendingNavigationPath(route);
		} else {
			router.push(route);
		}
	};

	if (pending > 0) {
		return (
			<button
				type='button'
				onClick={goToReview}
				title='Revisar cambios pendientes'
				className='w-full flex items-center justify-center gap-2 py-2 text-sm font-semibold text-warning-700 bg-warning-50 border-b border-warning-200 cursor-pointer hover:bg-warning-100 transition-colors'
			>
				<span className='h-2 w-2 rounded-full bg-warning-500' />
				Revisar consistencia ({pending} pendiente{pending > 1 ? 's' : ''})
			</button>
		);
	}

	if (failed > 0) {
		return (
			<button
				type='button'
				onClick={goToReview}
				title='Revisar fallos de evaluación'
				className='w-full flex items-center justify-center gap-2 py-2 text-sm font-semibold text-error-700 bg-error-50 border-b border-error-200 cursor-pointer hover:bg-error-100 transition-colors'
			>
				<span className='h-2 w-2 rounded-full bg-error-500' />
				Fallos de consistencia ({failed})
			</button>
		);
	}

	return (
		<span className='w-full flex items-center justify-center gap-2 py-2 text-sm font-medium text-neutral-500 bg-neutral-50 border-b border-neutral-200'>
			<span className='h-2 w-2 animate-pulse rounded-full bg-neutral-400' />
			Analizando consistencia…
		</span>
	);
}
