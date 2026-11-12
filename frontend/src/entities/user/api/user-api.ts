import { apiClient } from '@/shared/api';
import type { User } from '@/shared/model/auth-store';

export const getUser = () => {
	return apiClient<User>('/api/v1/auth/me');
};
