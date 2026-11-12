import { describe, expect, it } from 'vitest';
import { crearUsuario } from '@/test';
import { clearAuthStore, useAuthStore } from './auth-store';

const STORAGE_KEY = 'kosmo-auth-store';
const leerPersistido = () => JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null');

describe('useAuthStore', () => {
	it('inicia sin sesión', () => {
		expect(useAuthStore.getState()).toMatchObject({
			accessToken: null,
			refreshToken: null,
			user: null,
			mockUserId: null,
		});
	});

	it('setTokens guarda el access y el refresh token', () => {
		useAuthStore.getState().setTokens('access-1', 'refresh-1');

		expect(useAuthStore.getState()).toMatchObject({
			accessToken: 'access-1',
			refreshToken: 'refresh-1',
		});
	});

	it('setUser guarda el usuario autenticado', () => {
		const usuario = crearUsuario({ name: 'Ada' });

		useAuthStore.getState().setUser(usuario);

		expect(useAuthStore.getState().user).toEqual(usuario);
	});

	it('clearAuth elimina tokens y usuario pero conserva el mockUserId', () => {
		const store = useAuthStore.getState();
		store.setTokens('a', 'r');
		store.setUser(crearUsuario());
		store.initMockUser();
		const mockUserId = useAuthStore.getState().mockUserId;

		useAuthStore.getState().clearAuth();

		expect(useAuthStore.getState()).toMatchObject({
			accessToken: null,
			refreshToken: null,
			user: null,
			mockUserId,
		});
	});

	describe('initMockUser', () => {
		it('genera un id de usuario simulado con prefijo "usr_"', () => {
			useAuthStore.getState().initMockUser();

			expect(useAuthStore.getState().mockUserId).toMatch(/^usr_[a-z0-9]{1,8}$/);
		});

		it('es idempotente: no reemplaza un id ya generado', () => {
			useAuthStore.getState().initMockUser();
			const primero = useAuthStore.getState().mockUserId;

			useAuthStore.getState().initMockUser();

			expect(useAuthStore.getState().mockUserId).toBe(primero);
		});
	});

	describe('persistencia', () => {
		it('persiste los tokens en localStorage', () => {
			useAuthStore.getState().setTokens('access-p', 'refresh-p');

			expect(leerPersistido().state).toMatchObject({
				accessToken: 'access-p',
				refreshToken: 'refresh-p',
			});
		});

		it('clearAuthStore borra el almacenamiento y reinicia todo el estado', () => {
			const store = useAuthStore.getState();
			store.setTokens('a', 'r');
			store.setUser(crearUsuario());
			store.initMockUser();

			clearAuthStore();

			expect(useAuthStore.getState()).toMatchObject({
				accessToken: null,
				refreshToken: null,
				user: null,
				mockUserId: null,
			});
			// Tras limpiar, persist vuelve a escribir solo el estado vacío.
			expect(leerPersistido()?.state?.accessToken ?? null).toBeNull();
		});
	});
});
