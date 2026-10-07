'use client';

import {
	createProject,
	pushProjectToGitHub,
	useProjectStore,
	type Project,
} from '@/entities/project';
import { formatApiError } from '@/shared/api';
import {
	CharacterCounter,
	GitHub,
	Send,
	toast,
} from '@/shared/ui';
import { useAppStore } from '@/features/app-state';
import { zodResolver } from '@hookform/resolvers/zod';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { useController, useForm } from 'react-hook-form';
import { createProjectSchema, type ProjectFormData } from '../model/types';

const alphaRegex = /[^a-zA-Z\s]/g;

const CreateProjectForm = () => {
	const router = useRouter();
	const setProjectState = useProjectStore((s) => s.setProjectState);
	const projects = useProjectStore((s) => s.projects);
	const getProjects = useProjectStore((s) => s.getProjects);
	const [isSubmitting, setIsSubmitting] = useState(false);
	const createdProjectRef = useRef<Project | null>(null);

	useEffect(() => {
		if (projects.length === 0) void getProjects();
	}, [projects.length, getProjects]);

	const { control, handleSubmit, setValue } = useForm<ProjectFormData>({
		mode: 'onSubmit',
		resolver: zodResolver(createProjectSchema(projects)),
		defaultValues: {
			name: '',
			description: '',
			repo_name: 'kosmo-repositorio',
			is_public: true,
		},
	});

	const {
		field: { value: nameValue, onChange: nameOnChange, onBlur: nameOnBlur, ref: nameRef },
		fieldState: { error: nameError },
	} = useController({ name: 'name', control });

	const {
		field: { value: descValue, onChange: descOnChange, onBlur: descOnBlur, ref: descRef },
		fieldState: { error: descError },
	} = useController({ name: 'description', control });

	const {
		field: { value: repoNameValue, ref: repoNameRef },
		fieldState: { error: repoNameError },
	} = useController({ name: 'repo_name', control });

	const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
		let value = e.target.value;
		value = value.replace(alphaRegex, '');
		if (value.length > 25) {
			value = value.slice(0, 25);
		}
		nameOnChange(value);
		const repoName = value.trim()
			? `kosmo-${value.toLowerCase().replace(/\s+/g, '-')}`
			: 'kosmo-repositorio';
		setValue('repo_name', repoName);
	};

	const handleDescChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
		let value = e.target.value;
		if (value.length > 1000) {
			value = value.slice(0, 1000);
		}
		descOnChange(value);
	};

	const doSubmit = async (data: ProjectFormData) => {
		setIsSubmitting(true);
		try {
			const project =
				createdProjectRef.current ??
				(await createProject({ name: data.name, description: data.description }));
			createdProjectRef.current = project;

			useProjectStore.getState().addProject(project);
			useProjectStore.getState().setGithubSyncing(project.id, true);
			setProjectState(project);
			void useAppStore.getState().initializeProject(project.id);

			toast.success('Proyecto creado correctamente');

			// Se inicia la creación del repositorio en GitHub en segundo plano
			// sin bloquear la navegación inmediata del usuario a Descubrimiento.
			pushProjectToGitHub(project.id, {
				repo_name: data.repo_name,
				is_public: data.is_public,
			})
				.then(() => {
					useProjectStore.getState().setGithubSyncing(project.id, false);
				})
				.catch((err) => {
					console.error('Error al inicializar repositorio en segundo plano:', err);
					useProjectStore.getState().setGithubSyncing(project.id, false);
					toast.warning(
						'No se pudo inicializar el repositorio en GitHub en segundo plano. Podrás reintentarlo desde Implementación.',
					);
				});

			router.replace('/proyecto/descubrimiento');
		} catch (err) {
			toast.error(formatApiError(err, 'Error al crear el proyecto'));
			setIsSubmitting(false);
		}
	};

	const onSubmit = (data: ProjectFormData) => {
		void doSubmit(data);
	};

	const handleFormSubmit: React.FormEventHandler<HTMLFormElement> = (e) => {
		void handleSubmit(onSubmit)(e);
	};

	return (
		<>
			<form
				onSubmit={handleFormSubmit}
				className='flex-1 flex flex-col gap-5 px-0.5'
				noValidate
			>
				{/* Form card */}
				<div className='flex flex-col px-8 pt-8 pb-6 rounded-xl shadow-sm border border-neutral-200 bg-neutral-0'>
					{/* Name field */}
					<div className='flex flex-col gap-2'>
						<label
							htmlFor='project-name'
							className='text-xs font-semibold text-neutral-500 uppercase tracking-wider'
						>
							Nombre del proyecto
						</label>
						<input
							ref={nameRef}
							id='project-name'
							type='text'
							value={nameValue}
							onBlur={nameOnBlur}
							onChange={handleNameChange}
							placeholder='Ej. Ferretería'
							className='w-full min-h-11 px-4 py-2.5 text-neutral-800 placeholder:text-neutral-400 bg-neutral-50 border border-neutral-300 rounded-md focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none transition-all duration-200'
							autoComplete='off'
						/>
						<div className='flex justify-between items-center gap-2'>
							{nameError ? (
								<p className='text-error-500 text-xs' role='alert'>
									{nameError.message}
								</p>
							) : (
								<span />
							)}
							<CharacterCounter current={nameValue.length} max={25} />
						</div>
					</div>

					{/* Description field */}
					<div className='flex flex-col gap-2'>
						<label
							htmlFor='project-description'
							className='text-xs font-semibold text-neutral-500 uppercase tracking-wider'
						>
							Descripción
						</label>
						<textarea
							ref={descRef}
							id='project-description'
							value={descValue}
							onBlur={descOnBlur}
							onChange={handleDescChange}
							placeholder='Describe el problema de negocio que quieres resolver...'
							className='w-full min-h-30 px-4 py-3 text-neutral-800 placeholder:text-neutral-400 bg-neutral-50 border border-neutral-300 rounded-md focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none transition-all duration-200 resize-none'
						/>
						<div className='flex justify-between items-center gap-2'>
							{descError ? (
								<p className='text-error-500 text-xs' role='alert'>
									{descError.message}
								</p>
							) : (
								<span />
							)}
							<CharacterCounter current={descValue.length} max={1000} />
						</div>
					</div>

					{/* Repository section */}
					<div className='flex flex-col gap-5 pt-4'>
						<div className='flex items-center gap-2'>
							<div className='flex h-8 w-8 items-center justify-center rounded-md bg-neutral-100'>
								<GitHub size={18} color='text-neutral-800' />
							</div>
							<h3 className='text-sm font-semibold text-neutral-800'>
								Repositorio en GitHub
							</h3>
						</div>

						{/* Repo name field */}
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
								readOnly
								disabled
								placeholder='ej. kosmo-gestion-inventarios'
								className='w-full min-h-11 px-4 py-2.5 font-mono text-sm text-neutral-500 bg-neutral-100 border border-neutral-200 rounded-md cursor-not-allowed'
								autoComplete='off'
								maxLength={100}
							/>
							{repoNameError ? (
								<p className='text-error-500 text-xs' role='alert'>
									{repoNameError.message}
								</p>
							) : (
								<p className='text-neutral-400 text-xs'>
									Se creará automáticamente en segundo plano en tu cuenta de GitHub.
								</p>
							)}
						</div>

					</div>

					{/* Actions — al final del formulario */}
					<div className='flex items-center justify-end gap-3 pt-2 mt-4'>
						<button
							type='button'
							onClick={() => router.push('/proyecto')}
							className='btn btn-secondary'
						>
							Cancelar
						</button>
						<button type='submit' disabled={isSubmitting} className='btn btn-primary'>
							<Send color='-rotate-45' size={18} />
							{isSubmitting ? 'Creando proyecto...' : 'Crear proyecto'}
						</button>
					</div>
				</div>
			</form>

		</>
	);
};

export { CreateProjectForm };
