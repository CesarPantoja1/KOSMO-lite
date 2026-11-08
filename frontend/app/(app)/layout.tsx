'use client';

import { AuthGuard } from '@/shared/ui/AuthGuard';
import { MainNavbar } from '@/widgets/main-navbar';

export default function AppLayout({ children }: { children: React.ReactNode }) {
	return (
		<AuthGuard>
			<div className='min-h-screen min-w-full max-h-screen relative'>
				<MainNavbar>{children}</MainNavbar>
			</div>
		</AuthGuard>
	);
}
