'use client';

import { useEffect, useId, useRef } from 'react';
import { WarningIcon } from '@/shared/ui';

type Props = {
	repoName: string;
	onCancel: () => void;
	onConfirm: () => void;
	confirmLoading?: boolean;
};

const ConfirmacionVisibilidadRepositorio = ({
	repoName,
	onCancel,
	onConfirm,
	confirmLoading = false,
}: Props) => {
	const titleId = useId();
	const confirmRef = useRef<HTMLButtonElement>(null);

	useEffect(() => {
		confirmRef.current?.focus();
	}, []);

	useEffect(() => {
		const handleKeyDown = (e: KeyboardEvent) => {
			if (e.key === 'Escape') onCancel();
		};
		document.addEventListener('keydown', handleKeyDown);
		return () => document.removeEventListener('keydown', handleKeyDown);
	}, [onCancel]);
	return (
		<div
			role='button'
			tabIndex={-1}
			className='warning-popup'
			onClick={onCancel}
			onKeyDown={(e) => {
				if (e.key === 'Enter' || e.key === ' ') {
					onCancel();
				}
			}}
		>
			<div
				role='dialog'
				aria-modal='true'
				aria-labelledby={titleId}
				className='bg-neutral-0 rounded-xl shadow-lg py-8 px-10 w-full max-w-md mx-4 border border-warning-200'
				onClick={(e) => e.stopPropagation()}
			>
				<div className='mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-warning-50'>
					<WarningIcon size={24} color='text-warning-600' />
				</div>
				<h3
					id={titleId}
					className='text-lg font-semibold text-neutral-800 mb-2 text-center'
				>
					Crear repositorio público
				</h3>
				<p className='text-neutral-500 text-sm text-center leading-relaxed'>
					El repositorio <span className='font-mono text-neutral-700'>{repoName}</span>{' '}
					será visible por cualquier persona y el código fuente quedará expuesto
					públicamente.
				</p>
				<div className='flex justify-center gap-3 mt-6'>
					<button
						type='button'
						className='btn btn-secondary'
						onClick={onCancel}
						disabled={confirmLoading}
					>
						Cancelar
					</button>
					<button
						type='button'
						ref={confirmRef}
						className='btn btn-primary'
						onClick={onConfirm}
						disabled={confirmLoading}
					>
						{confirmLoading ? 'Creando...' : 'Crear repositorio público'}
					</button>
				</div>
			</div>
		</div>
	);
};

export { ConfirmacionVisibilidadRepositorio };
