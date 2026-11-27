'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';

import { useAuthStore } from '@/shared/model';
import { Logo } from '@/shared/ui';

interface RootNavbarProps {
	onComenzar?: () => void;
}

export function RootNavbar({ onComenzar }: RootNavbarProps) {
	const router = useRouter();
	const pathname = usePathname();
	const user = useAuthStore((s) => s.user);
	const isLanding = pathname === '/';

	const handleComenzar = () => {
		if (onComenzar) {
			onComenzar();
		} else {
			router.push('/proyecto');
		}
	};

	return (
		<header className='sticky top-0 z-50 border-b border-neutral-200 bg-neutral-0/90 backdrop-blur-xl'>
			<div className='mx-auto flex h-20 max-w-7xl items-center justify-between px-6'>
				<div className='flex items-center gap-3'>
					<button onClick={() => router.push('/')} className='flex items-center gap-3'>
						<Logo size={36} />
						<span className='text-xl font-bold tracking-tight text-neutral-800'>
							KOSMO
						</span>
					</button>
				</div>

				{isLanding && (
					<nav className='hidden items-center gap-8 text-sm text-neutral-500 md:flex'>
						<a href='#caracteristicas' className='transition hover:text-neutral-800'>
							Características
						</a>
						<a href='#como-funciona' className='transition hover:text-neutral-800'>
							Cómo funciona
						</a>
						<a href='#metodologia' className='transition hover:text-neutral-800'>
							Metodología
						</a>
					</nav>
				)}

				{user ? (
					<Link href='/perfil' className='btn btn-primary btn-sm'>
						Mi Cuenta
					</Link>
				) : (
					<button
						type='button'
						onClick={handleComenzar}
						className='btn btn-primary btn-sm'
					>
						Comenzar
					</button>
				)}
			</div>
		</header>
	);
}
