'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { getIntegrationStatus } from '@/entities/integration';
import type { IntegrationStatus } from '@/entities/integration';
import {
	getProjectGitHubStatus,
	pushProjectToGitHub,
	useProjectStore,
} from '@/entities/project';
import type { ProjectGitHubStatus, PushGitHubRequest } from '@/entities/project';
import { formatApiError } from '@/shared/api';

export type ProjectGithubViewState =
	| 'loading'
	| 'not-linked'
	| 'no-code'
	| 'create'
	| 'syncing'
	| 'synced'
	| 'failed';

interface ProjectGithubRepoState {
	viewState: ProjectGithubViewState;
	integration: IntegrationStatus | null;
	status: ProjectGitHubStatus | null;
	loading: boolean;
	error: string | null;
	refresh: () => Promise<void>;
	createRepo: (input: { repo_name: string; is_public: boolean }) => Promise<void>;
	sync: () => Promise<void>;
}

const NO_CODE_MARKER = 'no tiene funcionalidades implementadas';

const isNoCodeError = (err: unknown): boolean => {
	const message = (err instanceof Error ? err.message : String(err)).toLowerCase();
	return message.includes(NO_CODE_MARKER) || (err as { status?: number })?.status === 409;
};

/**
 * Orquesta las entidades `project` e `integration` para gestionar el estado
 * de sincronización de un proyecto con GitHub. Vive en `features` (y no en
 * `entities/project`) precisamente porque necesita conocer dos entidades a
 * la vez, algo que FSD no permite hacer a una entidad sobre otra.
 */
export function useProjectGithubRepo(projectId: string | null): ProjectGithubRepoState {
	const githubSyncingProjectId = useProjectStore((s) => s.githubSyncingProjectId);
	const setGithubSyncing = useProjectStore((s) => s.setGithubSyncing);
	const isLocalSyncing = Boolean(projectId && githubSyncingProjectId === projectId);

	const [integration, setIntegration] = useState<IntegrationStatus | null>(null);
	const [status, setStatus] = useState<ProjectGitHubStatus | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [noCode, setNoCode] = useState(false);

	const isSyncing = isLocalSyncing || status?.sync_status === 'syncing';

	const refresh = useCallback(async () => {
		if (!projectId) return;
		const [integrationRes, statusRes] = await Promise.all([
			getIntegrationStatus('github'),
			getProjectGitHubStatus(projectId),
		]);
		setIntegration(integrationRes);
		setStatus(statusRes);
		if (statusRes.sync_status === 'synced' || statusRes.sync_status === 'failed') {
			setGithubSyncing(projectId, false);
		}
		setNoCode(false);
		setError(null);
	}, [projectId, setGithubSyncing]);

	useEffect(() => {
		let cancelled = false;

		async function load() {
			if (!projectId) {
				setLoading(false);
				return;
			}
			setLoading(true);
			try {
				await refresh();
			} catch (err) {
				if (!cancelled) {
					setError(formatApiError(err, 'Error al consultar el estado de GitHub'));
				}
			} finally {
				if (!cancelled) setLoading(false);
			}
		}

		void load();
		return () => {
			cancelled = true;
		};
	}, [projectId, refresh]);

	useEffect(() => {
		if (!isSyncing || !projectId) return;

		const interval = setInterval(() => {
			void refresh();
		}, 3000);

		return () => {
			clearInterval(interval);
		};
	}, [isSyncing, projectId, refresh]);

	const push = useCallback(
		async (body: PushGitHubRequest) => {
			if (!projectId) return;
			setLoading(true);
			setError(null);
			try {
				const result = await pushProjectToGitHub(projectId, body);
				setStatus(result);
				setNoCode(false);
			} catch (err) {
				if (isNoCodeError(err)) {
					setNoCode(true);
				} else {
					setError(formatApiError(err, 'Error al sincronizar con GitHub'));
				}
				throw err;
			} finally {
				setLoading(false);
			}
		},
		[projectId],
	);

	const createRepo = useCallback(
		async (input: { repo_name: string; is_public: boolean }) => {
			await push({ repo_name: input.repo_name, is_public: input.is_public });
		},
		[push],
	);

	const sync = useCallback(async () => {
		await push({});
	}, [push]);

	const viewState = useMemo<ProjectGithubViewState>(() => {
		if (isSyncing) return 'syncing';
		if (loading) return 'loading';
		if (noCode) return 'no-code';
		if (!integration?.is_connected) return 'not-linked';
		if (!status) return 'failed';
		if (status.sync_status === 'failed') return 'failed';
		if (status.has_repository) return 'synced';
		return 'create';
	}, [isSyncing, loading, noCode, integration, status]);

	return { viewState, integration, status, loading, error, refresh, createRepo, sync };
}
