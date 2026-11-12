// Re-export from shared (auth moved to shared layer)
export { useAuthStore, clearAuthStore } from '@/shared/model/auth-store';
export type { AuthState, User } from '@/shared/model/auth-store';

export { authApi } from '@/shared/api/auth';
export { authHeaders } from '@/shared/api/headers';
export type {
	RegisterRequest,
	AuthorizeRequest,
	TokenExchangeRequest,
	TokenRefreshRequest,
	LogoutRequest,
	UserPublic,
	AuthorizationCodeResponse,
	TokenView,
	TokenPairResponse,
	PrincipalView,
	OAuthErrorResponse,
} from '@/shared/model/auth-types';

// User-specific API (stays in entity)
export { getUser } from './api/user-api';
