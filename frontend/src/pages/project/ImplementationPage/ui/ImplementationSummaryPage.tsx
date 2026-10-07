'use client';

import { useCharacteristicStore } from '@/entities/characteristic';
import type { ImplementationMetric } from '@/entities/implementation';
import { useImplementationStore } from '@/entities/implementation';
import { useRailwayOAuth } from '@/entities/integration';
import { useProjectStore } from '@/entities/project';
import { useProjectGithubRepo, type ProjectGithubViewState } from '@/features/github-sync';
import {
	AiOrbCenterIcon,
	ArrowLeft,
	CheckCircleWhiteIcon,
	EntitiesIcon,
	FlowIcon,
	GitHub,
	RulesIcon,
	ScreensIcon,
	ShieldCheckIcon,
	SmallCheckIcon,
	SparkleIcon,
	StarIcon,
	WarningIcon,
} from '@/shared/ui';
import { GestionRepositorioGitHub } from '@/widgets';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

import type { PreconditionState } from '@/entities/deploy';
import { useDeployStatus } from '@/entities/deploy';
import { DeployPreconditionPanel } from './DeployPreconditionPanel';
import { DeployResultPanel } from './DeployResultPanel';

const iconMap: Record<ImplementationMetric['icon'], React.ReactNode> = {
	features: <SparkleIcon color='text-ai-600' />,
	screens: <ScreensIcon color='text-ai-600' />,
	entities: <EntitiesIcon color='text-primary-600' />,
	rules: <RulesIcon color='text-warning-600' />,
	integrations: <StarIcon color='text-primary-600' />,
	validations: <ShieldCheckIcon color='text-info-700' />,
	actions: <FlowIcon color='text-ai-600' />,
};

const heroMeta: Record<
	ProjectGithubViewState,
	{ title: string; subtitle: string; badgeBg: string; badgeContent: React.ReactNode }
> = {
	loading: {
		title: 'Verificando tu proyecto…',
		subtitle: 'Consultando el estado de tu código y repositorio.',
		badgeBg: 'bg-neutral-200',
		badgeContent: (
			<span className='inline-flex animate-spin h-4 w-4 rounded-full border-2 border-neutral-300 border-t-neutral-500' />
		),
	},
	'not-linked': {
		title: 'Publica tu código en GitHub',
		subtitle: 'Conecta tu cuenta de GitHub para sincronizar y publicar tu aplicación.',
		badgeBg: 'bg-neutral-200',
		badgeContent: <GitHub size={16} color='text-neutral-700' />,
	},
	'no-code': {
		title: 'Aún no hay código generado',
		subtitle: 'Genera el código de al menos una funcionalidad antes de publicar.',
		badgeBg: 'bg-warning-100',
		badgeContent: <WarningIcon size={16} color='text-warning-600' />,
	},
	create: {
		title: 'Tu código está listo',
		subtitle: 'Crea el repositorio de tu proyecto para publicar tu aplicación en GitHub.',
		badgeBg: 'bg-ai-100',
		badgeContent: <GitHub size={16} color='text-ai-600' />,
	},
	syncing: {
		title: 'Sincronizando con GitHub…',
		subtitle: 'Tu código se está subiendo al repositorio.',
		badgeBg: 'bg-ai-100',
		badgeContent: (
			<span className='inline-flex animate-spin h-4 w-4 rounded-full border-2 border-ai-200 border-t-ai-600' />
		),
	},
	synced: {
		title: '¡Tu aplicación está lista!',
		subtitle:
			'Hemos generado la estructura y lógica de tu proyecto a partir de todo lo que definiste en KOSMO.',
		badgeBg: 'bg-success-500',
		badgeContent: <CheckCircleWhiteIcon size={18} color='text-neutral-0' />,
	},
	failed: {
		title: 'Hubo un problema al sincronizar',
		subtitle:
			'No se pudo subir tu código a GitHub. Reintenta desde el panel a continuación.',
		badgeBg: 'bg-error-100',
		badgeContent: <WarningIcon size={16} color='text-error-600' />,
	},
};

const ImplementationSummaryPage = () => {
	const router = useRouter();
	const summary = useImplementationStore((s) => s.summary);
	const requiresReviewByFeature = useImplementationStore((s) => s.requiresReviewByFeature);

	const currentProjectId = useProjectStore((s) => s.currentProject?.id ?? null);
	const github = useProjectGithubRepo(currentProjectId);
	const deploy = useDeployStatus(currentProjectId);
	const railway = useRailwayOAuth();

	const loadImplementation = useImplementationStore((s) => s.loadImplementation);
	const currentCharacteristics = useCharacteristicStore((s) => s.currentCharacteristics);
	const selectedCharacteristic = useCharacteristicStore(
		(s) => s.currentCharacteristics.find((c) => c.id === s.selectedId) ?? null,
	);

	useEffect(() => {
		if (summary) return;
		const target = selectedCharacteristic ?? currentCharacteristics[0] ?? null;
		if (!target) return;
		loadImplementation(
			target.id,
			target.title,
			target.display_id,
		);
	}, [summary, selectedCharacteristic, currentCharacteristics, loadImplementation]);

	const refreshRailway = railway.refresh;
	const refreshDeploy = deploy.refresh;
	useEffect(() => {
		const handleFocus = () => {
			void refreshRailway();
			void refreshDeploy();
		};
		window.addEventListener('focus', handleFocus);
		document.addEventListener('visibilitychange', handleFocus);

		return () => {
			window.removeEventListener('focus', handleFocus);
			document.removeEventListener('visibilitychange', handleFocus);
		};
	}, [refreshRailway, refreshDeploy]);

	const precondition: PreconditionState = (() => {
		if (github.loading || railway.loading) return 'loading';
		if (!github.status?.has_repository) {
			if (github.viewState === 'not-linked') return 'github-not-linked';
			return 'github-not-synced';
		}
		if (!railway.isConnected) return 'railway-not-linked';
		return 'ready';
	})();

	if (!summary) {
		return (
			<div className='h-full w-full overflow-y-auto px-4 md:px-6 py-6 pb-24'>
				<div className='max-w-7xl mx-auto flex flex-col items-center justify-center min-h-[50vh] gap-4'>
					<p className='text-neutral-500'>No hay resumen disponible.</p>
					<Link href='/proyecto/codigo' className='btn btn-secondary'>
						<ArrowLeft color='' size={18} />
						Volver a Implementación
					</Link>
				</div>
			</div>
		);
	}

	const meta = heroMeta[github.viewState] ?? heroMeta.synced;
	const activeFeatureId = selectedCharacteristic?.id ?? summary.featureId;
	const isRequiresReview =
		summary.status === 'requires_review' ||
		(activeFeatureId ? !!requiresReviewByFeature[activeFeatureId] : false);

	return (
		<div className='page-container'>
			<div className='page-header overflow-y-auto! pb-8'>
				<div className='flex items-start justify-between gap-4 pb-4'>
					<div className='flex flex-col gap-1'>
						<h1 className='text-neutral-800 text-lg md:text-xl font-bold'>
							Resumen de implementación
						</h1>
						<p className='text-neutral-500 text-sm md:text-base'>
							Estos son los elementos que forman parte de tu proyecto.
						</p>
					</div>
					<button onClick={() => router.back()} className='btn btn-secondary shrink-0'>
						<ArrowLeft color='' size={18} />
						Volver
					</button>
				</div>

				{isRequiresReview && (
					<div className='mb-6 flex items-center justify-between gap-4 rounded-xl border border-warning-200 bg-warning-50 p-4'>
						<div className='flex items-center gap-3'>
							<div className='flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-warning-100'>
								<WarningIcon size={20} color='text-warning-700' />
							</div>
							<div>
								<h3 className='text-sm font-semibold text-warning-900'>
									Implementación desactualizada
								</h3>
								<p className='text-xs text-warning-700'>
									Las especificaciones de esta funcionalidad cambiaron en fases anteriores. El código actual no está sincronizado con la última versión de los requisitos.
								</p>
							</div>
						</div>
						<Link href='/proyecto/codigo' className='btn btn-ai btn-sm shrink-0'>
							Regenerar código
						</Link>
					</div>
				)}

				<div className='grid lg:grid-cols-2 gap-6'>
					<div className='flex flex-col gap-6'>
						<div className='grid grid-cols-2 gap-4'>
							{summary.metrics.map((metric) => (
								<div
									key={metric.label}
									className='rounded-xl border border-neutral-200 bg-neutral-0 p-5 shadow-xs transition-shadow hover:shadow-sm'
								>
									<div
										className={`mb-3 flex h-9 w-9 items-center justify-center rounded-lg ${metric.iconBg}`}
									>
										{iconMap[metric.icon]}
									</div>
									<p className='text-2xl font-bold text-neutral-900'>{metric.value}</p>
									<p className='mt-1 text-xs md:text-sm text-neutral-500 font-medium'>
										{metric.label}
									</p>
								</div>
							))}
						</div>

						<div className='rounded-xl border border-neutral-200 bg-neutral-0 p-5 shadow-xs'>
							<h3 className='mb-3 text-sm font-semibold text-neutral-800'>Tecnologías</h3>
							<div className='flex flex-wrap gap-2'>
								{summary.technologies.map((t) => (
									<span
										key={t}
										className='rounded-full bg-neutral-100 px-3 py-1.5 text-xs font-medium text-neutral-700'
									>
										{t}
									</span>
								))}
							</div>
						</div>

						<div className='rounded-xl border border-neutral-200 bg-neutral-0 p-5 shadow-xs'>
							<h3 className='mb-3 text-sm font-semibold text-neutral-800'>
								¿Qué puedes hacer ahora?
							</h3>
							<div className='space-y-3'>
								{summary.nextSteps.map((step) => (
									<div key={step} className='flex items-start gap-3'>
										<div className='mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-success-50'>
											<SmallCheckIcon color='text-success-700' />
										</div>
										<p className='text-sm text-neutral-600'>{step}</p>
									</div>
								))}
							</div>
						</div>
					</div>

					<div className='flex flex-col items-start gap-6 rounded-2xl bg-ai-50/40 border border-ai-200/60 p-6 md:p-8 shadow-xs'>
						<div className='flex gap-6'>
							<div className='relative shrink-0 flex h-32 w-32 items-center justify-center'>
								<div className='absolute inset-3 rounded-2xl bg-ai-100/70' />
								<div className='relative flex h-18 w-18 items-center justify-center rounded-xl border-2 border-ai-500 bg-neutral-0 shadow-md'>
									<AiOrbCenterIcon size={36} color='text-ai-600' />
								</div>
								<div
									className={`absolute right-0 top-0 flex h-9 w-9 items-center justify-center rounded-full shadow-md ${meta.badgeBg}`}
								>
									{meta.badgeContent}
								</div>
								<div className='absolute left-0 top-3 text-ai-500'>
									<SparkleIcon size={18} />
								</div>
								<div className='absolute bottom-2 right-0 text-ai-500'>
									<SparkleIcon size={14} />
								</div>
							</div>

							<div className='flex flex-col gap-6 text-center'>
								<h3 className='text-lg md:text-xl font-bold text-neutral-900'>
									{meta.title}
								</h3>
								<p className='mt-2 max-w-sm text-sm text-neutral-500 leading-relaxed'>
									{meta.subtitle}
								</p>

							</div>
						</div>

						{currentProjectId && (
							<GestionRepositorioGitHub
								viewState={github.viewState}
								status={github.status}
								loading={github.loading}
								error={github.error}
								onCreate={async (input) => {
									await github.createRepo(input);
								}}
								onSync={async () => {
									await github.sync();
								}}
							/>
						)}

						{currentProjectId &&
							(deploy.status && deploy.status.status !== 'idle' ? (
								<DeployResultPanel
									projectId={currentProjectId}
									status={deploy.status}
									error={deploy.error}
									onRedeploy={() => deploy.deploy()}
									deploying={deploy.deploying}
									onDeleteSuccess={deploy.refresh}
									onRefresh={deploy.refresh}
									refreshing={deploy.loading}
								/>
							) : (
								<DeployPreconditionPanel
									precondition={precondition}
									onDeploy={() => deploy.deploy()}
									deploying={deploy.deploying}
									onConnectRailway={railway.handleConnect}
									connectingRailway={railway.actionLoading}
									deployError={deploy.error}
								/>
							))}
					</div>
				</div>
			</div>
		</div>
	);
};

export { ImplementationSummaryPage };
