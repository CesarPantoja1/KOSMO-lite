'use client';

import { Suspense, useState } from 'react';

import { VideoIntro } from '@/shared/ui/VideoIntro';
import { RootNavbar } from '@/widgets/root-navbar';

import { ApiKeySection } from './ApiKeySection';
import { AuthModal } from './AuthModal';
import { CtaSection } from './CtaSection';
import { Features } from './Features';
import { FlowSteps } from './FlowSteps';
import { Hero } from './Hero';
import { SddSection } from './SddSection';
import { SessionExpiredWatcher } from './SessionExpiredWatcher';

export function RootPage() {
	const [showAuthModal, setShowAuthModal] = useState(false);
	const [showVideo, setShowVideo] = useState(false);
	const [sessionExpired, setSessionExpired] = useState(false);

	const handleSessionExpired = () => {
		setSessionExpired(true);
		setShowAuthModal(true);
	};

	const handleComenzar = () => {
		setShowAuthModal(true);
	};

	return (
		<div className='min-h-screen bg-neutral-0 text-neutral-800'>
			<RootNavbar onComenzar={handleComenzar} />
			<Hero onComenzar={handleComenzar} onVerVideo={() => setShowVideo(true)} />
			<Features />
			<FlowSteps />
			<SddSection />
			<ApiKeySection />
			<CtaSection onComenzar={handleComenzar} />
			<AuthModal
				isOpen={showAuthModal}
				onClose={() => setShowAuthModal(false)}
				sessionExpired={sessionExpired && showAuthModal}
			/>
			<Suspense fallback={null}>
				<SessionExpiredWatcher onDetected={handleSessionExpired} />
			</Suspense>
			{showVideo && (
				<VideoIntro
					overlay
					src='/kosmo_intruduction.mp4'
					onEnded={() => setShowVideo(false)}
				/>
			)}
		</div>
	);
}
