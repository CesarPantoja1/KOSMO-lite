'use client';

import { useCallback, useEffect, useState } from 'react';
import {
	pushProjectToGitHub,
	useProjectStore,
} from '@/entities/project';
import { useProjectGithubRepo } from '../model/useProjectGithubRepo';
import { Check, Close, GitHub, WarningIcon } from '@/shared/ui';

export function GitHubSyncBanner() {
	const currentProject = useProjectStore((s) => s.currentProject);
	const githubSyncingProjectId = useProjectStore((s) => s.githubSyncingProjectId);
	const setGithubSyncing = useProjectStore((s) => s.setGithubSyncing);

	const currentProjectId = currentProject?.id ?? null;

	const { status, viewState, error, refresh } = useProjectGithubRepo(
		currentProjectId,
	);

	const isCurrentSyncing = Boolean(
		currentProjectId &&
			(githubSyncingProjectId === currentProjectId || viewState === 'syncing'),
	);

	const [wasSyncing, setWasSyncing] = useState(isCurrentSyncing);
	const [prevSyncing, setPrevSyncing] = useState(isCurrentSyncing);
	const [prevProjectId, setPrevProjectId] = useState<string | null>(currentProjectId);
	const [isDismissed, setIsDismissed] = useState(false);
	const [isRetrying, setIsRetrying] = useState(false);

	if (currentProjectId !== prevProjectId) {
		setPrevProjectId(currentProjectId);
		setIsDismissed(false);
		setWasSyncing(Boolean(currentProjectId && githubSyncingProjectId === currentProjectId));
	} else if (isCurrentSyncing !== prevSyncing) {
		setPrevSyncing(isCurrentSyncing);
		if (isCurrentSyncing) {
			setWasSyncing(true);
			setIsDismissed(false);
		}
	}

	// Auto-destrucción tras 4 segundos de éxito
	useEffect(() => {
		if (wasSyncing && viewState === 'synced') {
			const timer = setTimeout(() => {
				setIsDismissed(true);
			}, 4000);
			return () => clearTimeout(timer);
		}
	}, [wasSyncing, viewState]);

	const handleRetry = useCallback(async () => {
		if (!currentProjectId) return;
		setIsRetrying(true);
		setGithubSyncing(currentProjectId, true);
		try {
			await pushProjectToGitHub(currentProjectId, {
				repo_name: status?.suggested_repo_name ?? undefined,
				is_public: status?.is_public ?? true,
			});
			await refresh();
		} catch (err) {
			console.error('Error al reintentar creación de repositorio:', err);
		} finally {
			setIsRetrying(false);
		}
	}, [currentProjectId, status, setGithubSyncing, refresh]);

	if (isDismissed || !currentProject) return null;

	const repoName = status?.repo_name || status?.suggested_repo_name || currentProject.name;
	const repoUrl =
		status?.repo_url ||
		(status?.repo_name ? `https://github.com/${status.repo_name}` : null);

	// 1. Estado Sincronizando (Progreso claro con nombre de repo)
	if (isCurrentSyncing || isRetrying) {
		return (
			<div
				role='status'
				aria-live='polite'
				className='bg-primary-50/90 border-b border-primary-200/80 text-primary-950 px-6 py-2 flex items-center justify-between gap-4 transition-all duration-300 shrink-0 select-none'
			>
				<div className='flex items-center gap-2.5 min-w-0'>
					<div className='flex items-center justify-center h-5 w-5 rounded bg-primary-100/80 text-primary-700 shrink-0'>
						<GitHub size={13} color='text-current' />
					</div>
					<div className='h-3.5 w-3.5 border-2 border-primary-600 border-t-transparent animate-spin rounded-full shrink-0' />
					<p className='text-xs text-primary-900 truncate'>
						<span className='font-semibold'>Creando repositorio en GitHub:</span>{' '}
						<span className='font-mono font-medium text-primary-800 bg-primary-100/60 px-1.5 py-0.5 rounded'>
							{repoName}
						</span>
						<span className='text-primary-700 ml-2 hidden sm:inline'>
							Puedes continuar redactando o avanzando sin esperar.
						</span>
					</p>
				</div>
				<span className='text-[11px] font-medium text-primary-600 shrink-0 bg-primary-100/60 px-2 py-0.5 rounded-full'>
					Segundo plano
				</span>
			</div>
		);
	}

	// 2. Estado Completado exitosamente (Auto-destrucción a los 4s)
	if (wasSyncing && viewState === 'synced') {
		return (
			<div
				role='status'
				aria-live='polite'
				className='bg-emerald-50/90 border-b border-emerald-200/80 text-emerald-950 px-6 py-2 flex items-center justify-between gap-4 transition-all duration-300 shrink-0 animate-in fade-in duration-300'
			>
				<div className='flex items-center gap-2.5 min-w-0'>
					<div className='flex items-center justify-center h-5 w-5 rounded bg-emerald-100 text-emerald-700 shrink-0'>
						<Check size={13} />
					</div>
					<p className='text-xs text-emerald-900 truncate'>
						<span className='font-semibold'>Repositorio listo en GitHub:</span>{' '}
						<span className='font-mono font-medium text-emerald-800 bg-emerald-100/60 px-1.5 py-0.5 rounded'>
							{repoName}
						</span>
						{repoUrl && (
							<a
								href={repoUrl}
								target='_blank'
								rel='noopener noreferrer'
								className='text-primary-600 hover:text-primary-800 hover:underline font-semibold ml-2 inline-flex items-center gap-1'
							>
								Ver en GitHub ↗
							</a>
						)}
					</p>
				</div>
				<button
					type='button'
					onClick={() => setIsDismissed(true)}
					className='text-neutral-400 hover:text-neutral-700 p-1 rounded transition-colors shrink-0'
					title='Cerrar aviso'
				>
					<Close size={12} color='text-current' />
				</button>
			</div>
		);
	}

	// 3. Estado Fallido con acción de reintento directo
	if (wasSyncing && viewState === 'failed') {
		return (
			<div
				role='alert'
				className='bg-amber-50/95 border-b border-amber-200 text-amber-950 px-6 py-2 flex items-center justify-between gap-4 transition-all duration-300 shrink-0'
			>
				<div className='flex items-center gap-2.5 min-w-0'>
					<div className='flex items-center justify-center h-5 w-5 rounded bg-amber-100 text-amber-700 shrink-0'>
						<WarningIcon size={14} />
					</div>
					<p className='text-xs text-amber-900 truncate'>
						<span className='font-semibold'>No se pudo inicializar en GitHub:</span>{' '}
						<span className='text-amber-800'>
							{error || 'Error de conexión o permisos'}
						</span>
					</p>
				</div>
				<div className='flex items-center gap-2 shrink-0'>
					<button
						type='button'
						onClick={handleRetry}
						disabled={isRetrying}
						className='btn btn-primary py-1 px-3 text-xs font-medium cursor-pointer'
					>
						{isRetrying ? 'Reintentando...' : 'Reintentar'}
					</button>
					<button
						type='button'
						onClick={() => setIsDismissed(true)}
						className='text-neutral-400 hover:text-neutral-700 p-1 rounded transition-colors'
						title='Cerrar aviso'
					>
						<Close size={12} color='text-current' />
					</button>
				</div>
			</div>
		);
	}

	return null;
}
