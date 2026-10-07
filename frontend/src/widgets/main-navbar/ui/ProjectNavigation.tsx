import { Project } from '@/entities/project';
import { ComputerDesktop, Home } from '@/shared/ui';

interface ProjectNavigationProps {
	projects: Project[];
	currentProject: Project | null;
	isSidebarExpanded: boolean;
	onHomeClick: () => void;
	onProjectClick: (project: Project) => void;
}

export function ProjectNavigation({
	projects,
	currentProject,
	isSidebarExpanded,
	onHomeClick,
	onProjectClick,
}: ProjectNavigationProps) {
	return (
		<div className='flex flex-col flex-1 py-3 px-1 overflow-y-auto'>
			{isSidebarExpanded ? (
				<div className='flex flex-col gap-1'>
					<button
						className='flex items-center px-3 py-2.5 gap-2.5 cursor-pointer rounded-md transition-colors text-neutral-300 hover:bg-neutral-800 hover:text-neutral-0 border-transparent'
						onClick={onHomeClick}
						title='Inicio'
					>
						<Home size={20} color='text-neutral-500' />
						<span className='flex-1 text-left truncate font-medium'>Inicio</span>
					</button>
					<span className='text-neutral-500 text-xs font-semibold uppercase tracking-wider px-3 pb-2 pt-1'>
						Proyectos
					</span>
					{projects.map((project) => {
						const isActive = currentProject?.id === project.id;
						return (
							<button
								key={project.id}
								type='button'
								className={`flex items-center px-3 py-2.5 gap-2.5 cursor-pointer rounded-md transition-colors text-left ${
									isActive
										? 'bg-neutral-700 text-neutral-0'
										: 'text-neutral-300 hover:bg-neutral-800 hover:text-neutral-0 border-transparent'
								}`}
								onClick={() => onProjectClick(project)}
								title={project.name}
							>
								<ComputerDesktop
									size={20}
									color={isActive ? 'text-primary-500' : 'text-neutral-500'}
								/>
								<span className='flex-1 text-left truncate font-medium capitalize'>
									{project.name}
								</span>
							</button>
						);
					})}
				</div>
			) : (
				<div className='flex flex-col gap-1 items-center'>
					<button
						className='flex items-center justify-center w-10 h-10 cursor-pointer rounded-md transition-colors text-neutral-400 hover:bg-neutral-800 hover:text-neutral-0'
						onClick={onHomeClick}
						title='Inicio'
					>
						<Home size={20} color='text-current' />
					</button>
					{projects.map((project) => {
						const isActive = currentProject?.id === project.id;
						return (
							<button
								key={project.id}
								type='button'
								className={`flex items-center justify-center w-10 h-10 cursor-pointer rounded-md transition-colors ${
									isActive
										? 'bg-neutral-700 text-neutral-0'
										: 'text-neutral-400 hover:bg-neutral-800 hover:text-neutral-0'
								}`}
								onClick={() => onProjectClick(project)}
								title={project.name}
							>
								<span className='text-sm font-semibold'>
									{project.name.slice(0, 2).toUpperCase()}
								</span>
							</button>
						);
					})}
				</div>
			)}
		</div>
	);
}
