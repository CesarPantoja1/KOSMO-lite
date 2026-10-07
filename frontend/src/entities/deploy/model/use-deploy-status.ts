'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ProjectDeployStatusResponse, DeployRailwayRequest } from './types';
import { getDeployStatus, startDeployRailway } from '../api/api';
import { formatApiError } from '@/shared/api';

const TERMINAL_STATUSES = new Set(['ready', 'failed', 'idle']);

function getPollInterval(startTime: number, isHidden: boolean): number {
	if (isHidden) return 25_000;
	const elapsed = Date.now() - startTime;
	if (elapsed < 30_000) return 5_000;
	if (elapsed < 240_000) return 10_000;
	return 5_000;
}

export interface UseDeployStatusReturn {
	status: ProjectDeployStatusResponse | null;
	loading: boolean;
	deploying: boolean;
	error: string | null;
	deploy: (body?: DeployRailwayRequest) => Promise<void>;
	refresh: () => Promise<void>;
}

export function useDeployStatus(projectId: string | null): UseDeployStatusReturn {
	const [status, setStatus] = useState<ProjectDeployStatusResponse | null>(null);
	const [loading, setLoading] = useState(true);
	const [deploying, setDeploying] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
	const mountedRef = useRef(true);
	const statusRef = useRef<ProjectDeployStatusResponse | null>(null);
	const startTimeRef = useRef<number>(0);
	const scheduleNextPollRef = useRef<() => void>(() => {});

	useEffect(() => {
		statusRef.current = status;
	}, [status]);

	const clearPollTimer = useCallback(() => {
		if (timerRef.current) {
			clearTimeout(timerRef.current);
			timerRef.current = null;
		}
	}, []);

	const fetchStatus = useCallback(async () => {
		if (!projectId) return;
		try {
			const data = await getDeployStatus(projectId);
			if (mountedRef.current) {
				statusRef.current = data;
				setStatus(data);
				setError(null);
			}
		} catch (err) {
			if (mountedRef.current) {
				setError(formatApiError(err, 'No se pudo obtener el estado del despliegue'));
			}
		} finally {
			if (mountedRef.current) setLoading(false);
		}
	}, [projectId]);

	const scheduleNextPoll = useCallback(() => {
		clearPollTimer();
		if (!mountedRef.current) return;
		const current = statusRef.current;
		if (!current || TERMINAL_STATUSES.has(current.status)) return;

		const isHidden = typeof document !== 'undefined' && document.hidden;
		const interval = getPollInterval(startTimeRef.current, isHidden);

		timerRef.current = setTimeout(() => {
			void fetchStatus().then(() => {
				scheduleNextPollRef.current();
			});
		}, interval);
	}, [clearPollTimer, fetchStatus]);

	useEffect(() => {
		scheduleNextPollRef.current = scheduleNextPoll;
	}, [scheduleNextPoll]);

	useEffect(() => {
		mountedRef.current = true;
		let cancelled = false;

		async function init() {
			if (!projectId) {
				setLoading(false);
				return;
			}
			try {
				const data = await getDeployStatus(projectId);
				if (!cancelled && mountedRef.current) {
					statusRef.current = data;
					setStatus(data);
					setError(null);
				}
			} catch (err) {
				if (!cancelled && mountedRef.current) {
					setError(formatApiError(err, 'No se pudo obtener el estado del despliegue'));
				}
			} finally {
				if (!cancelled && mountedRef.current) setLoading(false);
			}
		}

		void init();

		return () => {
			cancelled = true;
			mountedRef.current = false;
			clearPollTimer();
		};
	}, [projectId, clearPollTimer]);

	const currentStatus = status?.status;

	useEffect(() => {
		if (!currentStatus || TERMINAL_STATUSES.has(currentStatus)) {
			clearPollTimer();
			startTimeRef.current = 0;
			return;
		}

		if (startTimeRef.current === 0) {
			startTimeRef.current = Date.now();
		}

		scheduleNextPoll();

		const handleVisibilityChange = () => {
			if (typeof document !== 'undefined' && !document.hidden) {
				void fetchStatus().then(() => {
					scheduleNextPoll();
				});
			}
		};

		const handleFocus = () => {
			void fetchStatus().then(() => {
				scheduleNextPoll();
			});
		};

		if (typeof document !== 'undefined') {
			document.addEventListener('visibilitychange', handleVisibilityChange);
		}
		if (typeof window !== 'undefined') {
			window.addEventListener('focus', handleFocus);
		}

		return () => {
			clearPollTimer();
			if (typeof document !== 'undefined') {
				document.removeEventListener('visibilitychange', handleVisibilityChange);
			}
			if (typeof window !== 'undefined') {
				window.removeEventListener('focus', handleFocus);
			}
		};
	}, [currentStatus, clearPollTimer, fetchStatus, scheduleNextPoll]);

	const deploy = useCallback(
		async (body?: DeployRailwayRequest) => {
			if (!projectId) return;
			setDeploying(true);
			setError(null);
			try {
				const data = await startDeployRailway(projectId, body);
				if (mountedRef.current) {
					startTimeRef.current = Date.now();
					setStatus(data);
				}
			} catch (err) {
				if (mountedRef.current) {
					setError(formatApiError(err, 'No se pudo iniciar el despliegue'));
				}
			} finally {
				if (mountedRef.current) setDeploying(false);
			}
		},
		[projectId],
	);

	const refresh = useCallback(async () => {
		setLoading(true);
		await fetchStatus();
		scheduleNextPoll();
	}, [fetchStatus, scheduleNextPoll]);

	return { status, loading, deploying, error, deploy, refresh };
}
