'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { useCallback, useState } from 'react';
import { useController, useForm } from 'react-hook-form';
import z from 'zod';
import { normalizeRepoName } from '../lib';
import { ConfirmacionVisibilidadRepositorio } from './ConfirmacionVisibilidadRepositorio';
import Send from './icons/Send';

type FormValues = {
	repo_name: string;
	is_public: boolean;
};

type Props = {
	suggestedRepoName: string | null;
	submitting?: boolean;
	onSubmit: (input: { repo_name: string; is_public: boolean }) => Promise<void> | void;
};

const repoNameSchema = z.object({
	repo_name: z
		.string()
		.trim()
		.min(1, 'Ingresa el nombre del repositorio')
		.max(100, 'El nombre no puede superar los 100 caracteres'),
	is_public: z.boolean(),
});

const FormularioCreacionRepositorio = ({
	suggestedRepoName,
	submitting = false,
	onSubmit,
}: Props) => {
	const [showConfirm, setShowConfirm] = useState(false);
	const [pendingValues, setPendingValues] = useState<FormValues | null>(null);

	const { control, handleSubmit, setValue } = useForm<FormValues>({
		mode: 'onSubmit',
		resolver: zodResolver(repoNameSchema),
		defaultValues: {
			repo_name: suggestedRepoName ?? 'kosmo-repositorio',
			is_public: false,
		},
	});

	const {
		field: {
			value: repoNameValue,
			onChange: repoNameOnChange,
			onBlur: repoNameOnBlur,
			ref: repoNameRef,
		},
		fieldState: { error: repoNameError },
	} = useController({ name: 'repo_name', control });

	const {
		field: { value: isPublic, onChange: isPublicOnChange },
	} = useController({ name: 'is_public', control });

	const handleRepoNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
		repoNameOnChange(normalizeRepoName(e.target.value));
	};

	const handleFormSubmit = useCallback(
		(values: FormValues) => {
			if (values.is_public) {
				setPendingValues(values);
				setShowConfirm(true);
				return;
			}
			onSubmit(values);
		},
		[onSubmit],
	);

	const handleConfirmPublic = () => {
		if (!pendingValues) return;
		setShowConfirm(false);
		onSubmit(pendingValues);
	};

	const handleCancelConfirm = () => {
		setShowConfirm(false);
		setPendingValues(null);
		setValue('is_public', false);
	};

	return (
		<>
			<form
				onSubmit={handleSubmit(handleFormSubmit)}
				noValidate
				className='flex flex-col gap-4'
			>
				<div className='flex flex-col gap-2'>
					<label
						htmlFor='repo-name'
						className='text-xs font-semibold text-neutral-500 uppercase tracking-wider'
					>
						Nombre del repositorio
					</label>
					<input
						ref={repoNameRef}
						id='repo-name'
						type='text'
						value={repoNameValue}
						onBlur={repoNameOnBlur}
						onChange={handleRepoNameChange}
						placeholder='ej. kosmo-gestion-inventarios'
						className='w-full min-h-11 px-4 py-2.5 font-mono text-sm text-neutral-800 placeholder:text-neutral-400 bg-neutral-50 border border-neutral-300 rounded-md focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none transition-all duration-200'
						autoComplete='off'
						maxLength={100}
					/>
					{repoNameError ? (
						<p className='text-error-500 text-xs' role='alert'>
							{repoNameError.message}
						</p>
					) : (
						<p className='text-neutral-400 text-xs'>
							Solo minúsculas, números y guiones. Se sugiere{' '}
							<span className='font-mono'>{suggestedRepoName ?? 'kosmo-{slug}'}</span>.
						</p>
					)}
				</div>

				<div className='flex flex-col gap-2'>
					<span className='text-xs font-semibold text-neutral-500 uppercase tracking-wider'>
						Visibilidad
					</span>
					<div className='flex gap-2'>
						<button
							type='button'
							onClick={() => isPublicOnChange(false)}
							className={`flex-1 rounded-lg border px-4 py-3 text-left transition-all duration-150 ${
								!isPublic
									? 'border-primary-500 bg-primary-50 shadow-sm'
									: 'border-neutral-200 bg-neutral-50 hover:border-neutral-300'
							}`}
						>
							<span
								className={`block text-sm font-semibold ${
									!isPublic ? 'text-primary-600' : 'text-neutral-800'
								}`}
							>
								Privado
							</span>
							<span className='text-xs text-neutral-500'>
								Solo tú y los colaboradores que invites podrán ver el código.
							</span>
						</button>
						<button
							type='button'
							onClick={() => isPublicOnChange(true)}
							className={`flex-1 rounded-lg border px-4 py-3 text-left transition-all duration-150 ${
								isPublic
									? 'border-warning-500 bg-warning-50 shadow-sm'
									: 'border-neutral-200 bg-neutral-50 hover:border-neutral-300'
							}`}
						>
							<span
								className={`block text-sm font-semibold ${
									isPublic ? 'text-warning-600' : 'text-neutral-800'
								}`}
							>
								Público
							</span>
							<span className='text-xs text-neutral-500'>
								Cualquier persona podrá ver el código fuente.
							</span>
						</button>
					</div>
				</div>

				<div className='flex items-center justify-end gap-3'>
					<button type='submit' disabled={submitting} className='btn btn-primary'>
						<Send color='text-white' size={18} />
						{submitting ? 'Creando repositorio...' : 'Crear repositorio'}
					</button>
				</div>
			</form>

			{showConfirm && (
				<ConfirmacionVisibilidadRepositorio
					repoName={pendingValues?.repo_name ?? ''}
					onCancel={handleCancelConfirm}
					onConfirm={handleConfirmPublic}
					confirmLoading={submitting}
				/>
			)}
		</>
	);
};

export { FormularioCreacionRepositorio };
