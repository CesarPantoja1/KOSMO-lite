'use client';

import { useState } from 'react';
import clsx from 'clsx';

import { HeadingItem } from '../model/heading';
import { CloseMarkdownContent, OpenMarkdownContent } from '@/shared/ui';

interface Props {
	headings: HeadingItem[];
	activeId?: string;
}

export function TocSidebar({ headings, activeId }: Props) {
	const [isOpen, setIsOpen] = useState(true);

	const handleScroll = (id: string) => {
		const element = document.getElementById(id);

		if (!element) return;

		element.scrollIntoView({
			behavior: 'smooth',
			block: 'start',
		});
	};

	return (
		<aside
			className='sticky top-0 h-full shrink-0 flex flex-col bg-neutral-50 border-r border-neutral-200 transition-all duration-300 pt-1'
			style={{ width: isOpen ? 260 : 44 }}
		>
			{isOpen ? (
				<>
					<div className='mb-4 flex items-center justify-between px-4 pt-2 shrink-0'>
						<h2 className='text-xs font-semibold uppercase tracking-wider text-neutral-500'>
							Contenido
						</h2>
						<button
							onClick={() => setIsOpen(false)}
							className='cursor-pointer text-neutral-400 hover:text-neutral-700 transition-colors'
						>
							<CloseMarkdownContent size={18} />
						</button>
					</div>

					<nav className='space-y-0.5 px-3 flex-1 overflow-y-auto pb-4'>
						{headings.length === 0 ? (
							<p className='text-xs text-neutral-400 px-1'>Sin secciones</p>
						) : (
							headings.map((heading, index) => (
								<button
									key={index}
									onClick={() => handleScroll(heading.id)}
									className={clsx(
										'block w-full px-2 py-1.5 text-left text-xs transition-colors cursor-pointer',
										activeId === heading.id
											? 'bg-neutral-200/75 text-base-950 font-medium'
											: 'text-neutral-500 hover:bg-neutral-100 hover:text-neutral-800',
									)}
									style={{
										paddingLeft: `${(heading.depth - 1) * 8 + 8}px`,
									}}
								>
									{heading.text}
								</button>
							))
						)}
					</nav>
				</>
			) : (
				<div className='flex justify-center pt-2'>
					<button
						onClick={() => setIsOpen(true)}
						className='cursor-pointer text-neutral-400 hover:text-neutral-700 transition-colors'
					>
						<OpenMarkdownContent size={18} />
					</button>
				</div>
			)}
		</aside>
	);
}
