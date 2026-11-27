'use client';

import { useCallback } from 'react';
import { useRailwayOAuth } from '@/entities/integration';
import { Railway, OAuthIntegration } from '@/shared/ui';

interface RailwayStepProps {
	onStatusChange?: (connected: boolean) => void;
}

export function RailwayStep({ onStatusChange }: RailwayStepProps) {
	const handleStatusChange = useCallback(
		(status: { is_connected: boolean }) => {
			onStatusChange?.(status.is_connected);
		},
		[onStatusChange],
	);

	const railway = useRailwayOAuth({ onStatusChange: handleStatusChange });

	return (
		<div className='flex flex-col gap-4'>
			<div>
				<h3 className='text-lg font-semibold text-neutral-800'>
					Conecta tu cuenta de Railway
				</h3>
				<p className='text-neutral-500 text-sm mt-1'>
					Obligatorio. Necesitas conectar Railway para desplegar tus proyectos en la nube.
				</p>
			</div>
			<OAuthIntegration
				label='Railway'
				icon={<Railway size={24} color='text-neutral-800' />}
				loading={railway.loading}
				actionLoading={railway.actionLoading}
				isConnected={railway.isConnected}
				username={railway.username}
				onConnect={railway.handleConnect}
				onDisconnect={railway.handleDisconnect}
			/>
		</div>
	);
}
