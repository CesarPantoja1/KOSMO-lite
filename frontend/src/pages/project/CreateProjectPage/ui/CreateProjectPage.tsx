'use client';

import { getProjects, type Project } from '@/entities/project';
import { useIntegrationGate } from '../model/useIntegrationGate';
import { useEffect, useState } from 'react';
import { CreateProjectForm } from './CreateProjectForm';

const CreateProjectPage = () => {
	const { isReady } = useIntegrationGate();
	const [projects, setProjects] = useState<Project[]>([]);
	const [isLoading, setIsLoading] = useState(true);

	useEffect(() => {
		if (!isReady) return;
		const fetchProjects = async () => {
			try {
				const data = await getProjects();
				setProjects(data);
			} catch (error) {
				console.error('Error fetching projects:', error);
			} finally {
				setIsLoading(false);
			}
		};
		fetchProjects();
	}, [isReady]);

	if (!isReady || isLoading) {
		return (
			<div className='flex items-center justify-center h-full'>
				<div className='animate-spin-custom h-8 w-8 border-2 border-primary-500 border-t-transparent rounded-full' />
			</div>
		);
	}

	const hasNoProjects = projects.length === 0;

	return (
		<div className={`page-container pt-6${hasNoProjects ? ' animate-fade-in' : ''}`}>
			<div className='page-header overflow-y-auto! pb-4'>
				{/* Header row */}
				<div className='flex items-start justify-between gap-4'>
					<div className='flex flex-col gap-1'>
						<h1 className='text-neutral-800 text-lg md:text-xl font-bold'>
							Crear Proyecto
						</h1>
						<p className='text-neutral-500 text-sm md:text-base'>
							Define la idea central y los objetivos de tu aplicación. Una descripción
							clara le permitirá al asistente estructurar correctamente las etapas
							posteriores.
						</p>
					</div>
				</div>

				<CreateProjectForm />
			</div>
		</div>
	);
};

export { CreateProjectPage };
