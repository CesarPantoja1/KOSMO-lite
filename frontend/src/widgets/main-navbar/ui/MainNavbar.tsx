'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { useAppStore } from '@/features/app-state';

import { Project, useProjectStore } from '@/entities/project';
import { useAuthStore } from '@/entities/user';
import { WizardNavegacion } from '@/widgets/wizard-navegacion';
import { GitHubSyncBanner } from '@/features/github-sync';

import { ProjectNavigation } from './ProjectNavigation';
import { SidebarBrand } from './SidebarBrand';
import { UserSection } from './UserSection';

interface MainNavbarProps {
	children: React.ReactNode;
}

export function MainNavbar({ children }: MainNavbarProps) {
	const projects = useProjectStore((s) => s.projects);
	const getProjectsStore = useProjectStore((s) => s.getProjects);
	const user = useAuthStore((s) => s.user);

	const [isSidebarExpanded, setIsSidebarExpanded] = useState(false);
	const router = useRouter();

	useEffect(() => {
		const fetchProjects = async () => {
			try {
				await getProjectsStore();
			} catch (error) {
				console.error('Failed to load projects', error);
			}
		};
		void fetchProjects();
	}, [getProjectsStore]);

	const currentProject = useProjectStore((s) => s.currentProject);
	const isEditorMaximized = useAppStore((s) => s.isEditorMaximized);

	const handleHomeClick = () => {
		const { hasUnsavedChanges, setPendingNavigationPath } = useAppStore.getState();
		if (hasUnsavedChanges) {
			setPendingNavigationPath('/proyecto');
			return;
		}
		router.push('/proyecto');
	};

	const initializeProject = useAppStore((s) => s.initializeProject);

	const handleProjectClick = (project: Project) => {
		useAppStore.getState().resetStateBeforeChangeProject();
		useProjectStore.getState().setProjectState(project);
		initializeProject(project.id);

		router.push('/proyecto/descubrimiento');
	};

	return (
		<>
			<header className='flex h-screen max-h-screen overflow-hidden transition-all duration-300'>
				{!isEditorMaximized && (
					<div
						className={`flex max-h-screen flex-col bg-neutral-900 transition-all duration-300 shrink-0 ${isSidebarExpanded ? 'w-64' : 'w-13'}`}
					>
						<SidebarBrand
							isSidebarExpanded={isSidebarExpanded}
							onToggle={() => setIsSidebarExpanded(!isSidebarExpanded)}
						/>

						<ProjectNavigation
							projects={projects}
							currentProject={currentProject}
							isSidebarExpanded={isSidebarExpanded}
							onHomeClick={handleHomeClick}
							onProjectClick={handleProjectClick}
						/>

						<UserSection user={user} isSidebarExpanded={isSidebarExpanded} />
					</div>
				)}

				<main
					className={`flex flex-1 min-h-0 flex-col overflow-hidden transition-all duration-300 ${isEditorMaximized ? '' : 'mx-8'}`}
				>
					{!isEditorMaximized && (
						<div className='z-50 shrink-0'>
							<WizardNavegacion />
							<GitHubSyncBanner />
						</div>
					)}
					<section className='min-h-0 flex-1 overflow-hidden'>{children}</section>
				</main>
			</header>
		</>
	);
}
