'use client';

import Link from 'next/link';

import { formatApiError } from '@/shared/api';
import {
	ArrowRight,
	Clock,
	FormularioCreacionRepositorio,
	GitHub,
	Load,
	SuccessCheckIcon,
	toast,
	WarningIcon,
} from '@/shared/ui';

import type { ProjectGitHubStatus } from '@/entities/project';

import type { ProjectGithubViewState } from '@/features/github-sync';

type Props = {
	viewState: ProjectGithubViewState;
	status: ProjectGitHubStatus | null;
	loading: boolean;
	error: string | null;
	onCreate: (input: { repo_name: string; is_public: boolean }) => Promise<void>;
	onSync: () => Promise<void>;
};

const formatDate = (iso: string | null | undefined): string => {
	if (!iso) return '—';
	const date = new Date(iso);
	if (Number.isNaN(date.getTime())) return '—';
	return date.toLocaleString('es-ES', {
		day: '2-digit',
		month: 'short',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit',
	});
};

const shortHash = (hash: string | null | undefined): string =>
	hash ? hash.slice(0, 7) : '—';

const GestionRepositorioGitHub = ({
	viewState,
	status,
	loading,
	error,
	onCreate,
	onSync,
}: Props) => {
	const handleCreate = async (input: { repo_name: string; is_public: boolean }) => {
		try {
			await onCreate(input);
			toast.success('Repositorio creado y sincronizado con GitHub.');
		} catch (err) {
			toast.error(formatApiError(err, 'No se pudo crear el repositorio en GitHub'));
		}
	};

	const handleSync = async () => {
		try {
			await onSync();
			toast.success('Código sincronizado con GitHub.');
		} catch (err) {
			toast.error(formatApiError(err, 'No se pudo sincronizar con GitHub'));
		}
	};

	return (
		<div className='bg-neutral-0 border border-neutral-200 rounded-xl shadow-sm p-6 w-full'>
			<div className='flex items-center justify-between mb-4'>
				<div className='flex items-center gap-2'>
					<div className='flex h-8 w-8 items-center justify-center rounded-md bg-neutral-100'>
						<GitHub size={18} color='text-neutral-800' />
					</div>
					<h3 className='text-lg font-semibold text-neutral-800'>
						Repositorio en GitHub
					</h3>
				</div>
				{viewState === 'synced' && status?.is_public ? (
					<span className='text-xs font-medium px-2.5 py-1 rounded-full bg-warning-50 text-warning-700 border border-warning-500/20'>
						Público
					</span>
				) : viewState === 'synced' ? (
					<span className='text-xs font-medium px-2.5 py-1 rounded-full bg-neutral-100 text-neutral-600 border border-neutral-200'>
						Privado
					</span>
				) : null}
			</div>

			{error && (
				<div className='mb-4 flex items-center gap-2 rounded-lg border border-error-500/20 bg-error-50 px-4 py-3 text-sm text-error-700'>
					<WarningIcon size={18} color='text-error-600' />
					{error}
				</div>
			)}

			{viewState === 'loading' && (
				<div className='flex items-center gap-3 py-4 text-neutral-500 text-sm'>
					<span className='inline-flex animate-spin text-primary-500'>
						<Load size={18} color='text-current' />
					</span>
					Verificando estado del repositorio...
				</div>
			)}

			{viewState === 'not-linked' && (
				<div className='flex flex-col gap-4'>
					<div className='flex flex-col gap-1'>
						<p className='text-sm font-semibold text-neutral-800'>
							Vincula tu cuenta de GitHub
						</p>
						<p className='text-sm text-neutral-500'>
							Necesitas conectar tu cuenta de GitHub para poder crear o sincronizar el
							repositorio de tu proyecto.
						</p>
					</div>
					<div className='flex items-center gap-3'>
						<Link href='/perfil' className='btn btn-primary btn-sm'>
							Conectar cuenta de GitHub
						</Link>
					</div>
				</div>
			)}

			{viewState === 'no-code' && (
				<div className='flex items-start gap-3 rounded-lg border border-warning-200 bg-warning-50 px-4 py-3'>
					<WarningIcon size={20} color='text-warning-600' />
					<div className='flex flex-col gap-1'>
						<p className='text-sm font-semibold text-warning-700'>
							Aún no hay código generado
						</p>
						<p className='text-sm text-warning-700/80'>
							Genera el código de al menos una funcionalidad antes de crear el repositorio
							en GitHub.
						</p>
					</div>
				</div>
			)}

			{viewState === 'create' && (
				<div className='flex flex-col gap-3'>
					<div className='flex flex-col gap-1'>
						<p className='text-sm font-semibold text-neutral-800'>
							Crea el repositorio de tu proyecto
						</p>
						<p className='text-sm text-neutral-500'>
							Define el nombre y la visibilidad. El código de tus funcionalidades se
							subirá al repositorio de GitHub.
						</p>
					</div>
					<FormularioCreacionRepositorio
						suggestedRepoName={status?.suggested_repo_name ?? null}
						submitting={loading}
						onSubmit={handleCreate}
					/>
				</div>
			)}

			{viewState === 'syncing' && (
				<div className='flex items-center gap-3 py-4 text-neutral-500 text-sm'>
					<span className='inline-flex animate-spin text-primary-500'>
						<Load size={18} color='text-current' />
					</span>
					Sincronizando el código con GitHub...
				</div>
			)}

			{viewState === 'failed' && (
				<div className='flex flex-col gap-3'>
					<div className='flex items-start gap-3 rounded-lg border border-error-500/20 bg-error-50 px-4 py-3'>
						<WarningIcon size={20} color='text-error-600' />
						<div className='flex flex-col gap-1'>
							<p className='text-sm font-semibold text-error-700'>
								La sincronización falló
							</p>
							<p className='text-sm text-error-700/80'>
								{status?.error_message ?? error ?? 'Ocurrió un error al sincronizar.'}
							</p>
						</div>
					</div>
					<div className='flex items-center gap-3'>
						<button
							type='button'
							onClick={handleSync}
							disabled={loading}
							className='btn btn-primary btn-sm'
						>
							{loading ? 'Reintentando...' : 'Reintentar'}
						</button>
					</div>
				</div>
			)}

			{viewState === 'synced' && status?.has_repository && (
				<div className='flex flex-col gap-4'>
					<div className='flex flex-wrap gap-x-8 gap-y-3'>
						<div className='flex flex-col gap-1'>
							<span className='text-xs font-medium text-neutral-400 uppercase tracking-wider'>
								Repositorio
							</span>
							{status.repo_url ? (
								<a
									href={status.repo_url}
									target='_blank'
									rel='noopener noreferrer'
									className='inline-flex items-center gap-1 text-sm font-semibold text-primary-600 hover:text-primary-700 hover:underline transition-colors'
								>
									{status.repo_name ?? status.repo_url}
									<span className='inline-flex -rotate-45'>
										<ArrowRight size={14} color='text-current' />
									</span>
								</a>
							) : (
								<span className='text-sm font-medium text-neutral-800'>
									{status.repo_name}
								</span>
							)}
						</div>
						<div className='flex flex-col gap-1'>
							<span className='text-xs font-medium text-neutral-400 uppercase tracking-wider'>
								Última sincronización
							</span>
							<span className='inline-flex items-center gap-1.5 text-sm text-neutral-600'>
								<Clock size={14} color='text-neutral-400' />
								{formatDate(status.last_push_at)}
							</span>
						</div>
						<div className='flex flex-col gap-1'>
							<span className='text-xs font-medium text-neutral-400 uppercase tracking-wider'>
								Último commit
							</span>
							<span className='font-mono text-sm text-neutral-600'>
								{shortHash(status.last_commit_hash)}
							</span>
						</div>
					</div>

					<div className='flex items-center gap-3'>
						<button
							type='button'
							onClick={handleSync}
							disabled={loading}
							className='btn btn-secondary btn-sm'
						>
							{loading ? 'Sincronizando...' : 'Sincronizar ahora'}
						</button>
						<span className='inline-flex items-center gap-1.5 text-xs text-success-700'>
							<SuccessCheckIcon size={14} />
							Al día
						</span>
					</div>
				</div>
			)}
		</div>
	);
};

export { GestionRepositorioGitHub };
