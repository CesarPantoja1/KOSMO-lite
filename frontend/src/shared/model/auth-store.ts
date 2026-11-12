import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface User {
	subject: string;
	name?: string | null;
	email?: string | null;
	avatar_url?: string | null;
	scopes: string[];
}

export interface AuthState {
	accessToken: string | null;
	refreshToken: string | null;
	user: User | null;
	mockUserId: string | null;
	setTokens: (accessToken: string, refreshToken: string) => void;
	setUser: (user: User) => void;
	clearAuth: () => void;
	initMockUser: () => void;
}

export const useAuthStore = create<AuthState>()(
	persist(
		(set, get) => ({
			accessToken: null,
			refreshToken: null,
			user: null,
			mockUserId: null,
			setTokens: (accessToken, refreshToken) => set({ accessToken, refreshToken }),
			setUser: (user) => set({ user }),
			clearAuth: () => set({ accessToken: null, refreshToken: null, user: null }),
			initMockUser: () => {
				const { mockUserId } = get();
				if (!mockUserId) {
					const newId = 'usr_' + Math.random().toString(36).substring(2, 10);
					set({ mockUserId: newId });
				}
			}
		}),
		{
			name: 'kosmo-auth-store',
		},
	),
);

export const clearAuthStore = () => {
	useAuthStore.persist.clearStorage();
	useAuthStore.setState({ accessToken: null, refreshToken: null, user: null, mockUserId: null });
};
