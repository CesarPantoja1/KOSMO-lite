'use client';

import { useRef } from 'react';

interface VideoIntroProps {
	src: string;
	onEnded?: () => void;
	overlay?: boolean;
	className?: string;
}

const VideoIntro = ({ src, onEnded, overlay = false, className }: VideoIntroProps) => {
	const videoRef = useRef<HTMLVideoElement>(null);

	const handleLoadedData = () => {
		if (videoRef.current) {
			videoRef.current.playbackRate = 0.7;
		}
	};

	const handleTimeUpdate = () => {
		const video = videoRef.current;
		if (!video) return;

		const remaining = video.duration - video.currentTime;
		if (remaining <= 3 && video.volume > 0) {
			video.volume = Math.max(0, video.volume - 0.02);
		}
	};

	const handleEnded = () => {
		if (onEnded) {
			setTimeout(onEnded, 1500);
		}
	};

	const defaultClassName = overlay
		? 'fixed inset-0 z-200 bg-black flex items-center justify-center w-full h-full'
		: 'fixed inset-0 w-full h-full object-cover z-50';

	return (
		<video
			ref={videoRef}
			src={src}
			autoPlay
			playsInline
			onLoadedData={handleLoadedData}
			onTimeUpdate={handleTimeUpdate}
			onEnded={handleEnded}
			className={className ?? defaultClassName}
		/>
	);
};

export { VideoIntro };
