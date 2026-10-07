'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getIntegrationStatus } from '@/entities/integration';
import { useAiConfigStore } from '@/entities/ai-config';

export function useIntegrationGate() {
	const router = useRouter();
	const [isReady, setIsReady] = useState(false);
	const [githubConnected, setGithubConnected] = useState(false);
	const [railwayConnected, setRailwayConnected] = useState(false);
	const fetchConfig = useAiConfigStore((s) => s.fetchConfig);

	useEffect(() => {
		let cancelled = false;

		async function check() {
			try {
				const [github, railway] = await Promise.all([
					getIntegrationStatus('github'),
					getIntegrationStatus('railway'),
					fetchConfig(),
				]);
				if (cancelled) return;

				const currentConfig = useAiConfigStore.getState().config;

				if (!currentConfig?.has_api_key || !github.is_connected || !railway.is_connected) {
					router.replace('/onboarding');
					return;
				}

				setGithubConnected(true);
				setRailwayConnected(true);
				setIsReady(true);
			} catch {
				if (!cancelled) {
					router.replace('/onboarding');
				}
			}
		}

		void check();
		return () => {
			cancelled = true;
		};
	}, [router, fetchConfig]);

	return { isReady, githubConnected, railwayConnected };
}
