'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import { ModalConfirm, UserCircle } from '@/shared/ui';

import { User, authApi } from '@/entities/user';

import { clearAllStores, useAppStore } from '@/features/app-state';

interface UserSectionProps {
	user: User | null;
	isSidebarExpanded: boolean;
}

export function UserSection({ user, isSidebarExpanded }: UserSectionProps) {
	const router = useRouter();
	const [showUserMenu, setShowUserMenu] = useState(false);
	const [menuPos, setMenuPos] = useState({ x: 0, y: 0 });
	const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
	const userMenuRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		const handleClickOutside = (e: MouseEvent) => {
			if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
				setShowUserMenu(false);
			}
		};
		if (showUserMenu) {
			document.addEventListener('mousedown', handleClickOutside);
		}
		return () => document.removeEventListener('mousedown', handleClickOutside);
	}, [showUserMenu]);

	const handleLogout = async () => {
		const { hasUnsavedChanges } = useAppStore.getState();
		if (hasUnsavedChanges) {
			setShowLogoutConfirm(true);
			return;
		}
		await executeLogout();
	};

	const executeLogout = async () => {
		await authApi.logout();
		clearAllStores();
		router.push('/');
	};

	return (
		<>
			<div
				className={`border-t border-neutral-700 inline-flex items-center gap-3 overflow-hidden mt-auto ${
					isSidebarExpanded ? 'px-3 py-4 justify-start' : 'p-2 py-4 justify-center'
				}`}
			>
				{isSidebarExpanded ? (
					<>
						{user?.avatar_url ? (
							// eslint-disable-next-line @next/next/no-img-element
							<img
								src={user.avatar_url}
								alt={user.name || 'Avatar'}
								className='w-9 h-9 rounded-full object-cover shrink-0 border border-neutral-600'
							/>
						) : (
							<UserCircle size={36} color='text-neutral-400' className='shrink-0' />
						)}
						<div className='flex-1 min-w-0 flex flex-col justify-center'>
							<h4 className='text-neutral-0 text-sm font-semibold truncate'>
								{user?.name || user?.email || 'Usuario'}
							</h4>
							<button
								onClick={() => router.push('/perfil')}
								className='text-left text-neutral-500 text-xs font-normal hover:text-neutral-300 transition-colors'
							>
								Perfil
							</button>
							<button
								onClick={handleLogout}
								className='text-left text-neutral-500 text-xs font-normal hover:text-neutral-300 transition-colors'
							>
								Cerrar sesión
							</button>
						</div>
					</>
				) : (
					<div className='relative' ref={userMenuRef}>
						<button
							onClick={(e) => {
								const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
								setMenuPos({ x: rect.right + 8, y: rect.bottom - 80 });
								setShowUserMenu(!showUserMenu);
							}}
							className='flex items-center justify-center'
						>
							{user?.avatar_url ? (
								// eslint-disable-next-line @next/next/no-img-element
								<img
									src={user.avatar_url}
									alt={user.name || 'Avatar'}
									className='w-9 h-9 cursor-pointer rounded-full object-cover shrink-0 border border-neutral-600'
								/>
							) : (
								<UserCircle size={36} color='text-neutral-400' className='shrink-0' />
							)}
						</button>
						{showUserMenu && (
							<div
								className='fixed w-40 bg-neutral-800 border border-neutral-700 rounded-lg shadow-lg z-50'
								style={{ left: menuPos.x, bottom: window.innerHeight - menuPos.y }}
							>
								<button
									onClick={() => {
										router.push('/perfil');
										setShowUserMenu(false);
									}}
									className='w-full cursor-pointer text-left px-3 py-2 text-sm text-neutral-300 hover:bg-neutral-700 hover:text-neutral-0 rounded-t-lg transition-colors'
								>
									Perfil
								</button>
								<button
									onClick={() => {
										handleLogout();
										setShowUserMenu(false);
									}}
									className='w-full cursor-pointer text-left px-3 py-2 text-sm text-neutral-300 hover:bg-neutral-700 hover:text-neutral-0 rounded-b-lg transition-colors'
								>
									Cerrar sesión
								</button>
							</div>
						)}
					</div>
				)}
			</div>
			{showLogoutConfirm && (
				<ModalConfirm
					title='Cerrar sesión'
					description='Tiene cambios sin guardar. ¿Desea cerrar sesión de todos modos? Se perderán los cambios no guardados.'
					cancelText='Cancelar'
					confirmText='Cerrar sesión'
					onCancel={() => setShowLogoutConfirm(false)}
					onConfirm={() => {
						setShowLogoutConfirm(false);
						executeLogout();
					}}
				/>
			)}
		</>
	);
}
