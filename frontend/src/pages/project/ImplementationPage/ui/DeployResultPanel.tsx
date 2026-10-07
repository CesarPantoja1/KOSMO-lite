'use client';

import type { ProjectDeployStatusResponse } from '@/entities/deploy';
import { deleteDeployment } from '@/entities/deploy';
import {
	Clock,
	ComputerDesktop,
	Load,
	ModalConfirm,
	Railway,
	SuccessCheckIcon,
	WarningIcon,
} from '@/shared/ui';
import { toast } from '@/shared/ui';
import { useCallback, useEffect, useState } from 'react';

const DeployResultPanel = ({
	projectId,
	status,
	error,
	onRedeploy,
	deploying = false,
	onDeleteSuccess,
	onRefresh,
	refreshing = false,
}: {
	projectId: string;
	status: ProjectDeployStatusResponse;
	error: string | null;
	onRedeploy?: () => void;
	deploying?: boolean;
	onDeleteSuccess?: () => void;
	onRefresh?: () => void;
	refreshing?: boolean;
}) => {
	const [copied, setCopied] = useState(false);
	const [deleting, setDeleting] = useState(false);
	const [showConfirmDelete, setShowConfirmDelete] = useState(false);
	const [now, setNow] = useState(() => Date.now());

	const isDeploying = status.status === 'building' || status.status === 'pending';

	useEffect(() => {
		if (!isDeploying) return;

		const interval = setInterval(() => {
			setNow(Date.now());
		}, 1000);

		return () => clearInterval(interval);
	}, [isDeploying]);

	const elapsedSeconds = (() => {
		if (!isDeploying || !status.last_deploy_at) return 0;
		const diff = Math.floor((now - new Date(status.last_deploy_at).getTime()) / 1000);
		return !Number.isNaN(diff) && diff >= 0 && diff < 1800 ? diff : 0;
	})();

	const formatElapsed = (seconds: number) => {
		const mins = Math.floor(seconds / 60);
		const secs = seconds % 60;
		if (mins === 0) return `${secs}s`;
		return `${mins}m ${secs.toString().padStart(2, '0')}s`;
	};

	const handleConfirmDelete = async () => {
		setShowConfirmDelete(false);
		try {
			setDeleting(true);
			await deleteDeployment(projectId);
			toast.success('Despliegue eliminado exitosamente');
			onDeleteSuccess?.();
		} catch {
			toast.error('Error al eliminar el despliegue');
		} finally {
			setDeleting(false);
		}
	};

	const handleCopy = useCallback(async () => {
		if (!status.deploy_url) return;
		try {
			await navigator.clipboard.writeText(status.deploy_url);
			setCopied(true);
			toast.success('URL copiada al portapapeles');
			setTimeout(() => setCopied(false), 2000);
		} catch {
			toast.error('No se pudo copiar la URL');
		}
	}, [status.deploy_url]);

	const formatDate = (iso: string | null): string => {
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

	return (
		<div className='bg-neutral-0 border border-neutral-200 rounded-xl shadow-sm p-6 w-full'>
			<div className='flex items-center gap-2 mb-4'>
				<div className='flex h-8 w-8 items-center justify-center rounded-md bg-railway-50'>
					<Railway size={18} color='text-railway-700' />
				</div>
				<h3 className='text-lg font-semibold text-neutral-800'>
					Estado del despliegue
				</h3>
				{onRefresh && (
					<button
						type='button'
						onClick={onRefresh}
						disabled={refreshing || deploying}
						className='inline-flex items-center justify-center p-1 rounded-md text-neutral-400 hover:text-neutral-600 hover:bg-neutral-100 transition-colors'
						title='Actualizar estado'
						aria-label='Actualizar estado'
					>
						<Load size={14} color={refreshing ? 'animate-spin text-primary-600' : 'text-neutral-500'} />
					</button>
				)}
				{status.status === 'ready' && (
					<span className='ml-auto inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-success-50 text-success-700 border border-success-500/20'>
						<SuccessCheckIcon size={14} />
						Activo
					</span>
				)}
				{status.status === 'building' && (
					<span className='ml-auto inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-ai-50 text-ai-700 border border-ai-500/20'>
						<span className='inline-flex animate-spin h-3.5 w-3.5 rounded-full border-2 border-ai-200 border-t-ai-600' />
						Construyendo
					</span>
				)}
				{status.status === 'pending' && (
					<span className='ml-auto inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-warning-50 text-warning-700 border border-warning-500/20'>
						<Clock size={14} color='text-warning-600' />
						Pendiente
					</span>
				)}
				{status.status === 'failed' && (
					<span className='ml-auto inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-error-50 text-error-700 border border-error-500/20'>
						<WarningIcon size={14} color='text-error-600' />
						Fallido
					</span>
				)}
			</div>

			{(status.status === 'building' || status.status === 'pending') && (
				<div className='flex flex-col gap-2 py-4'>
					<div className='flex items-center gap-3 text-neutral-600 text-sm font-medium'>
						<span className='inline-flex animate-spin h-4 w-4 shrink-0 rounded-full border-2 border-neutral-300 border-t-primary-600' />
						<span>
							{status.status === 'building'
								? 'Construyendo y desplegando tu aplicación...'
								: 'Esperando inicio del despliegue...'}
						</span>
						{elapsedSeconds > 0 && (
							<span className='text-xs text-neutral-400 font-normal'>
								({formatElapsed(elapsedSeconds)} transcurridos)
							</span>
						)}
					</div>
					<p className='text-xs text-neutral-400 pl-7'>
						Los despliegues en Railway suelen tardar entre 4 y 7 minutos. Puedes cambiar de pestaña con tranquilidad, el estado se actualizará automáticamente.
					</p>
				</div>
			)}

			{status.status === 'ready' && status.deploy_url && (
				<div className='flex flex-col gap-3'>
					<div className='flex flex-col gap-1'>
						<span className='text-xs font-medium text-neutral-400 uppercase tracking-wider'>
							URL pública
						</span>
						<div className='flex items-center gap-2'>
							<a
								href={status.deploy_url}
								target='_blank'
								rel='noopener noreferrer'
								className='inline-flex items-center gap-1.5 text-sm font-semibold text-primary-600 hover:text-primary-700 hover:underline transition-colors'
							>
								<ComputerDesktop size={14} color='text-primary-600' />
								{status.deploy_url}
							</a>
							<button
								type='button'
								onClick={handleCopy}
								className='inline-flex items-center gap-1 rounded-md border border-neutral-200 bg-neutral-0 px-2 py-1 text-xs text-neutral-600 hover:bg-neutral-50 transition-colors'
								title='Copiar URL'
							>
								{copied ? <SuccessCheckIcon size={12} /> : 'Copiar'}
							</button>
						</div>
					</div>
					{status.service_name && (
						<div className='flex flex-col gap-1'>
							<span className='text-xs font-medium text-neutral-400 uppercase tracking-wider'>
								Servicio
							</span>
							<span className='text-sm text-neutral-600'>{status.service_name}</span>
						</div>
					)}
					{status.last_deploy_at && (
						<div className='flex flex-col gap-1'>
							<span className='text-xs font-medium text-neutral-400 uppercase tracking-wider'>
								Último despliegue
							</span>
							<span className='inline-flex items-center gap-1.5 text-sm text-neutral-600'>
								<Clock size={14} color='text-neutral-400' />
								{formatDate(status.last_deploy_at)}
							</span>
						</div>
					)}
					{onRedeploy && (
						<div className='pt-3 mt-1 border-t border-neutral-100 flex items-center justify-between gap-3'>
							<span className='text-xs text-neutral-500'>
								¿Subiste nuevos cambios a GitHub?
							</span>
							<div className='flex gap-2'>
								<button
									type='button'
									onClick={() => setShowConfirmDelete(true)}
									disabled={deleting || deploying}
									className='btn btn-secondary btn-sm inline-flex items-center gap-1.5 text-error-600 hover:bg-error-50 hover:text-error-700 hover:border-error-200'
								>
									{deleting ? (
										<>
											<Load size={14} />
											Eliminando...
										</>
									) : (
										'Eliminar despliegue'
									)}
								</button>
								<button
									type='button'
									onClick={onRedeploy}
									disabled={deploying || deleting}
									className='btn btn-secondary btn-sm inline-flex items-center gap-1.5'
								>
									{deploying ? (
										<>
											<Load size={14} />
											Actualizando...
										</>
									) : (
										<>
											<Railway size={14} color='text-railway-700' />
											Actualizar despliegue
										</>
									)}
								</button>
							</div>
						</div>
					)}
				</div>
			)}

			{status.status === 'failed' && (
				<div className='flex flex-col gap-3'>
					<div className='flex items-start gap-3 rounded-lg border border-error-500/20 bg-error-50 px-4 py-3'>
						<WarningIcon size={20} color='text-error-600' />
						<div className='flex flex-col gap-1'>
							<p className='text-sm font-semibold text-error-700'>
								Error en el despliegue
							</p>
							<p className='text-sm text-error-700/80'>
								{status.error_message ??
									error ??
									'Ocurrió un error durante el despliegue.'}
							</p>
						</div>
					</div>
					<div className='flex items-center justify-between gap-3'>
						{status.error_log_url ? (
							<a
								href={status.error_log_url}
								target='_blank'
								rel='noopener noreferrer'
								className='inline-flex items-center gap-1.5 text-sm font-semibold text-primary-600 hover:text-primary-700 hover:underline transition-colors'
							>
								Ver registros de compilación
							</a>
						) : (
							<div />
						)}
						{onRedeploy && (
							<button
								type='button'
								onClick={onRedeploy}
								disabled={deploying}
								className='btn btn-secondary btn-sm inline-flex items-center gap-1.5'
							>
								{deploying ? (
									<>
										<Load size={14} />
										Reintentando...
									</>
								) : (
									<>
										<Railway size={14} color='text-railway-700' />
										Reintentar despliegue
									</>
								)}
							</button>
						)}
					</div>
				</div>
			)}

			{showConfirmDelete && (
				<ModalConfirm
					title='Eliminar despliegue'
					description='¿Estás seguro de que deseas eliminar el despliegue? Esta acción eliminará el servicio en la nube.'
					cancelText='Cancelar'
					confirmText='Eliminar'
					onCancel={() => setShowConfirmDelete(false)}
					onConfirm={handleConfirmDelete}
				/>
			)}
		</div>
	);
};

export { DeployResultPanel };
