import { apiClient } from '@/shared/api';
import { USE_MOCKS } from '@/shared/api/config';
import type { ProjectDeployStatusResponse, DeployRailwayRequest } from '../model/types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

let mockDeployStatus: ProjectDeployStatusResponse = {
	service_id: null,
	service_name: null,
	deploy_url: null,
	status: 'idle',
	last_deploy_at: null,
	error_message: null,
	error_log_url: null,
};

const mockGetStatus = async (_projectId: string): Promise<ProjectDeployStatusResponse> => {
	await delay(300);
	return { ...mockDeployStatus };
};

const mockStartRailway = async (
	_projectId: string,
	_body?: DeployRailwayRequest,
): Promise<ProjectDeployStatusResponse> => {
	await delay(800);
	mockDeployStatus = {
		service_id: 'srv_mock_123',
		service_name: 'kosmo-app',
		deploy_url: null,
		status: 'building',
		last_deploy_at: new Date().toISOString(),
		error_message: null,
		error_log_url: null,
	};
	setTimeout(() => {
		mockDeployStatus = {
			...mockDeployStatus,
			status: 'ready',
			deploy_url: 'https://kosmo-app.up.railway.app',
		};
	}, 6_000);
	return { ...mockDeployStatus };
};

const realGetStatus = (projectId: string): Promise<ProjectDeployStatusResponse> =>
	apiClient<ProjectDeployStatusResponse>(`/api/v1/projects/${projectId}/deploy`, {
		method: 'GET',
	});

const realStartRailway = (
	projectId: string,
	body?: DeployRailwayRequest,
): Promise<ProjectDeployStatusResponse> =>
	apiClient<ProjectDeployStatusResponse>(`/api/v1/projects/${projectId}/deploy/railway`, {
		method: 'POST',
		body: body ? JSON.stringify(body) : undefined,
	});

export const getDeployStatus = (projectId: string): Promise<ProjectDeployStatusResponse> =>
	USE_MOCKS ? mockGetStatus(projectId) : realGetStatus(projectId);

export const startDeployRailway = (
	projectId: string,
	body?: DeployRailwayRequest,
): Promise<ProjectDeployStatusResponse> =>
	USE_MOCKS ? mockStartRailway(projectId, body) : realStartRailway(projectId, body);

export const deleteDeployment = async (projectId: string): Promise<void> => {
	await apiClient<void>(`/api/v1/projects/${projectId}/deploy`, {
		method: 'DELETE',
	});
};

