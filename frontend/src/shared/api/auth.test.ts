import { createHash } from 'node:crypto';
import { describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '@/shared/model/auth-store';
import { HttpResponse, apiUrl, crearTokens, crearUsuario, http, server } from '@/test';
import { authApi } from './auth';
import { ApiError } from './errors';

/** Registra los cuerpos JSON recibidos por un endpoint POST para inspeccionarlos. */
function capturarPost(path: string, respuesta: () => Response) {
	const cuerpos: Record<string, unknown>[] = [];
	server.use(
		http.post(apiUrl(path), async ({ request }) => {
			cuerpos.push((await request.json()) as Record<string, unknown>);
			return respuesta();
		}),
	);
	return cuerpos;
}

describe('authApi', () => {
	describe('register', () => {
		it('envía nombre, correo y contraseña y devuelve la respuesta del servidor', async () => {
			const cuerpos = capturarPost('/api/v1/auth/register', () =>
				HttpResponse.json({ email: 'ada@kosmo.dev', message: 'ok' }, { status: 201 }),
			);

			const res = await authApi.register('Ada', 'ada@kosmo.dev', 'secreta123');

			expect(res).toEqual({ email: 'ada@kosmo.dev', message: 'ok' });
			expect(cuerpos).toEqual([
				{ name: 'Ada', email: 'ada@kosmo.dev', password: 'secreta123' },
			]);
		});

		it('propaga las violaciones de validación (422) como ApiError', async () => {
			server.use(
				http.post(apiUrl('/api/v1/auth/register'), () =>
					HttpResponse.json(
						{ detail: [{ loc: ['body', 'email'], msg: 'Correo inválido' }] },
						{ status: 422 },
					),
				),
			);

			const error = await authApi.register('Ada', 'no-es-correo', 'x').catch((e) => e);

			expect(error).toBeInstanceOf(ApiError);
			expect(error).toMatchObject({ status: 422, detail: 'Correo inválido' });
		});
	});

	describe('authorize', () => {
		it('envía un code_challenge S256 derivado del verifier que devuelve', async () => {
			const cuerpos = capturarPost('/api/v1/auth/authorize', () =>
				HttpResponse.json({ authorization_code: 'code-123', expires_in: 60 }),
			);

			const { code, verifier } = await authApi.authorize('ada@kosmo.dev', 'clave');

			expect(code).toBe('code-123');
			expect(cuerpos[0]).toMatchObject({
				email: 'ada@kosmo.dev',
				password: 'clave',
				code_challenge_method: 'S256',
				code_challenge: createHash('sha256').update(verifier).digest('base64url'),
				scopes: ['profile:read', 'agent:run'],
			});
		});

		it('rechaza con el error OAuth cuando las credenciales son inválidas', async () => {
			server.use(
				http.post(apiUrl('/api/v1/auth/authorize'), () =>
					HttpResponse.json(
						{ error: 'invalid_grant', error_description: 'Credenciales inválidas' },
						{ status: 401 },
					),
				),
			);

			await expect(authApi.authorize('ada@kosmo.dev', 'mala')).rejects.toMatchObject({
				status: 401,
				errorCode: 'invalid_grant',
				detail: 'Credenciales inválidas',
			});
		});
	});

	describe('exchangeToken', () => {
		it('canjea el código por tokens usando grant authorization_code', async () => {
			const tokens = crearTokens();
			const cuerpos = capturarPost('/api/v1/auth/token', () => HttpResponse.json(tokens));

			const res = await authApi.exchangeToken('code-123', 'verifier-abc');

			expect(res).toEqual(tokens);
			expect(cuerpos).toEqual([
				{
					grant_type: 'authorization_code',
					code: 'code-123',
					code_verifier: 'verifier-abc',
				},
			]);
		});
	});

	describe('getMe', () => {
		it('envía el access token y devuelve el usuario autenticado', async () => {
			useAuthStore.getState().setTokens('access-xyz', 'refresh-xyz');
			let authorization: string | null = null;
			server.use(
				http.get(apiUrl('/api/v1/auth/me'), ({ request }) => {
					authorization = request.headers.get('Authorization');
					return HttpResponse.json(crearUsuario({ name: 'Ada' }));
				}),
			);

			const usuario = await authApi.getMe();

			expect(usuario.name).toBe('Ada');
			expect(authorization).toBe('Bearer access-xyz');
		});
	});

	describe('login', () => {
		it('ejecuta el flujo PKCE completo y guarda tokens y usuario en el store', async () => {
			const usuario = crearUsuario({ email: 'ada@kosmo.dev' });
			server.use(http.get(apiUrl('/api/v1/auth/me'), () => HttpResponse.json(usuario)));

			await authApi.login('ada@kosmo.dev', 'clave');

			expect(useAuthStore.getState()).toMatchObject({
				accessToken: 'access-token-test',
				refreshToken: 'refresh-token-test',
				user: usuario,
			});
		});
	});

	describe('logout', () => {
		it('revoca el refresh token en el servidor y limpia la sesión', async () => {
			useAuthStore.getState().setTokens('access', 'refresh-a-revocar');
			useAuthStore.getState().setUser(crearUsuario());
			const cuerpos = capturarPost(
				'/api/v1/auth/logout',
				() => new HttpResponse(null, { status: 204 }),
			);

			await authApi.logout();

			expect(cuerpos).toEqual([{ refresh_token: 'refresh-a-revocar' }]);
			expect(useAuthStore.getState()).toMatchObject({
				accessToken: null,
				refreshToken: null,
				user: null,
			});
		});

		it('limpia la sesión local aunque el servidor falle', async () => {
			const consola = vi.spyOn(console, 'error').mockImplementation(() => {});
			useAuthStore.getState().setTokens('access', 'refresh');
			server.use(
				http.post(apiUrl('/api/v1/auth/logout'), () =>
					HttpResponse.json({ detail: 'caído' }, { status: 503 }),
				),
			);

			await expect(authApi.logout()).resolves.toBeUndefined();

			expect(useAuthStore.getState().accessToken).toBeNull();
			expect(consola).toHaveBeenCalledWith('Error on logout', expect.any(ApiError));
			consola.mockRestore();
		});
	});
});
