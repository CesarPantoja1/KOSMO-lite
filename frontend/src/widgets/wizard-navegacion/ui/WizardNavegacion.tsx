'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useRef } from 'react';
import { useAppStore } from '@/features/app-state';
import { useProjectStore } from '@/entities/project';
import {
	CONSISTENCY_REVIEW_ROUTES,
	firstPhaseToReview,
	sumPhaseStatus,
} from '@/entities/consistency';
import type {
	ConsistencyStatusResponse,
	ConsistencyTargetPhase,
} from '@/entities/consistency';
import { useConsistencyPolling } from '../model/useConsistencyPolling';
import { toast } from '@/shared/ui';

import { getStyleIconStatus } from '../model/get-status-color';
import { ProjectStatus } from '../model/status';
import WizardItem from './WizardItem';
import { PhaseStatusBadge } from './PhaseStatusBadge';
import { ConsistencyGateButton } from './ConsistencyGateButton';
import { AiProviderToast } from './AiProviderToast';

import {
	Characteristics,
	Discovery,
	Requirements,
	Modeling,
	Implementation,
} from '@/shared/ui';

const phaseItems: {
	href: string;
	Icon: typeof Discovery;
	label: string;
	subtitle: string;
	consistencyPhase: ConsistencyTargetPhase | null;
}[] = [
	{
		href: '/proyecto/descubrimiento',
		Icon: Discovery,
		label: 'DESCUBRIMIENTO',
		subtitle: 'Entender el problema',
		consistencyPhase: null,
	},
	{
		href: '/proyecto/caracteristicas',
		Icon: Characteristics,
		label: 'FUNCIONALIDADES',
		subtitle: 'Qué debe hacer',
		consistencyPhase: 'features',
	},
	{
		href: '/proyecto/requisitos',
		Icon: Requirements,
		label: 'CRITERIOS',
		subtitle: 'Reglas de aceptación',
		consistencyPhase: 'requirements',
	},
	{
		href: '/proyecto/modelo',
		Icon: Modeling,
		label: 'DIAGRAMAS',
		subtitle: 'Flujo de interacción',
		consistencyPhase: 'model',
	},
	{
		href: '/proyecto/codigo',
		Icon: Implementation,
		label: 'IMPLEMENTACIÓN',
		subtitle: 'Generar código',
		consistencyPhase: 'implementation',
	},
];

export function WizardNavegacion() {
	const pathname = usePathname();
	const router = useRouter();
	const isProyectosOpen = useProjectStore((s) => s.isProyectosOpen);
	const currentProject = useProjectStore((s) => s.currentProject);
	const { status: consistencyStatus, isLoading } = useConsistencyPolling(
		currentProject?.id ?? null,
	);

	const handleWizardClick = (href: string) => (e: React.MouseEvent) => {
		const { hasUnsavedChanges, setPendingNavigationPath } = useAppStore.getState();
		if (hasUnsavedChanges) {
			e.preventDefault();
			setPendingNavigationPath(href);
		}
	};

	const prevStatusRef = useRef<ConsistencyStatusResponse | null>(null);

	useEffect(() => {
		const prev = prevStatusRef.current;
		prevStatusRef.current = consistencyStatus;
		if (!consistencyStatus || !prev) return;
		if ((pathname || '').includes('/consistencia')) return;

		const finishedEvaluating =
			sumPhaseStatus(prev, 'evaluating') > 0 &&
			sumPhaseStatus(consistencyStatus, 'evaluating') === 0;
		const pending = sumPhaseStatus(consistencyStatus, 'pending');
		if (!finishedEvaluating || pending === 0) return;

		const route = CONSISTENCY_REVIEW_ROUTES[firstPhaseToReview(consistencyStatus)];
		toast.add(
			{
				variant: 'info',
				title: 'Consistencia evaluada',
				message: `${pending} sugerencia(s) pendiente(s) de revisión`,
				action: {
					label: 'Revisar',
					onAction: () => {
						const { hasUnsavedChanges, setPendingNavigationPath } =
							useAppStore.getState();
						if (hasUnsavedChanges) {
							setPendingNavigationPath(route);
						} else {
							router.push(route);
						}
					},
				},
			},
			{ timeout: 10_000 },
		);
	}, [consistencyStatus, pathname, router]);

	if ((pathname || '').includes('/consistencia')) return null;
	if (!isProyectosOpen) return null;

	const activeIndex = phaseItems.findIndex((item) =>
		(pathname || '').startsWith(item.href),
	);

	return (
		<div>
			<nav className='relative flex items-center justify-center gap-2 px-8 py-3 bg-linear-to-b from-neutral-50 to-neutral-0 border-b border-neutral-200'>
				{phaseItems.map(({ href, Icon, label, subtitle, consistencyPhase }, index) => {
					let status: ProjectStatus = 'disable';
					if (activeIndex !== -1) {
						if (index === activeIndex) {
							status = 'active';
						} else if (index < activeIndex) {
							status = 'completed';
						}
					}

					const colors = getStyleIconStatus(status);
					const isLast = index === phaseItems.length - 1;
					const phaseBadge = consistencyPhase
						? consistencyStatus?.phases?.[consistencyPhase]
						: undefined;

					return (
						<div key={href} className='flex items-center'>
							<div className='relative'>
								<WizardItem
									href={href}
									icon={<Icon size={14} color={colors.iconStyles} />}
									iconContainerStyles={colors.iconContainer}
									label={label}
									subtitle={subtitle}
									labelStyles={colors.labelStyles}
									onClick={handleWizardClick(href)}
								/>
								{consistencyPhase && (
									<span className='absolute -top-1 -left-0.5 z-10'>
										<PhaseStatusBadge status={phaseBadge} isLoading={isLoading} />
									</span>
								)}
							</div>
							{/* Connector line between steps */}
							{!isLast && (
								<div className='w-16 mx-1 shrink-0 flex items-center self-center'>
									<div
										className={`h-0.5 w-full rounded-full transition-all duration-500 ${
											index < activeIndex
												? 'bg-linear-to-r from-wizard-completed to-wizard-completed'
												: 'bg-linear-to-r from-wizard-connector-pending to-wizard-connector-pending'
										}`}
									/>
								</div>
							)}
						</div>
					);
				})}
			</nav>
			<ConsistencyGateButton status={consistencyStatus} />
			<AiProviderToast />
		</div>
	);
}
