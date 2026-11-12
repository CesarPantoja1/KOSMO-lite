import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '@/shared/model/auth-store';
import {
	HttpResponse,
	apiUrl,
	delay,
	http,
	mockRouter,
	renderWithProviders,
	server,
} from '@/test';
import { Register } from './Register';

const CLAVE_VALIDA = 'una-clave-larga-123';

// "Confirmar contraseña" no tiene su <label> asociado (sin htmlFor/id): se usa el placeholder.
const campos = () => ({
	nombre: screen.getByLabelText('Nombre completo'),
	correo: screen.getByLabelText('Correo electrónico'),
	clave: screen.getByLabelText('Contraseña'),
	confirmacion: screen.getByPlaceholderText('Repite tu contraseña'),
});
const botonRegistrarse = () => screen.getByRole('button', { name: 'Registrarse' });

function renderizar() {
	const onClose = vi.fn();
	const onSwitchToLogin = vi.fn();
	const utils = renderWithProviders(
		<Register onClose={onClose} onSwitchToLogin={onSwitchToLogin} />,
	);
	return { ...utils, onClose, onSwitchToLogin };
}

type Datos = { nombre: string; correo: string; clave: string; confirmacion: string };

async function completar(
	user: ReturnType<typeof renderizar>['user'],
	datos: Partial<Datos> = {},
) {
	const valores: Datos = {
		nombre: 'Ada Lovelace',
		correo: 'ada@kosmo.dev',
		clave: CLAVE_VALIDA,
		confirmacion: CLAVE_VALIDA,
		...datos,
	};
	const c = campos();
	for (const campo of Object.keys(valores) as (keyof Datos)[]) {
		if (valores[campo]) await user.type(c[campo], valores[campo]);
	}
	await user.click(botonRegistrarse());
}

function capturarRegistro(
	respuesta: () => Response = () =>
		HttpResponse.json({ email: 'ada@kosmo.dev', message: 'ok' }, { status: 201 }),
) {
	const cuerpos: unknown[] = [];
	server.use(
		http.post(apiUrl('/api/v1/auth/register'), async ({ request }) => {
			cuerpos.push(await request.json());
			return respuesta();
		}),
	);
	return cuerpos;
}

describe('Register', () => {
	describe('validación en el cliente', () => {
		it.each<[string, Partial<Datos>, string]>([
			['falta el nombre', { nombre: '' }, 'Todos los campos son obligatorios'],
			[
				'el nombre son solo espacios',
				{ nombre: '   ' },
				'Todos los campos son obligatorios',
			],
			[
				'falta la confirmación',
				{ confirmacion: '' },
				'Todos los campos son obligatorios',
			],
			[
				'las contraseñas no coinciden',
				{ confirmacion: 'otra-clave-larga' },
				'Las contraseñas no coinciden',
			],
			[
				'la contraseña tiene menos de 12 caracteres',
				{ clave: 'corta123', confirmacion: 'corta123' },
				'La contraseña debe tener al menos 12 caracteres',
			],
		])('rechaza el envío si %s', async (_caso, datos, mensaje) => {
			const cuerpos = capturarRegistro();
			const { user } = renderizar();

			await completar(user, datos);

			expect(screen.getByText(mensaje)).toBeInTheDocument();
			expect(cuerpos).toHaveLength(0);
		});

		it('acepta una contraseña de exactamente 12 caracteres', async () => {
			const cuerpos = capturarRegistro();
			const { user } = renderizar();

			await completar(user, { clave: '123456789012', confirmacion: '123456789012' });

			await waitFor(() => expect(mockRouter.push).toHaveBeenCalledWith('/onboarding'));
			expect(cuerpos).toHaveLength(1);
		});
	});

	it('registra al usuario, inicia sesión y lo lleva al onboarding', async () => {
		const cuerpos = capturarRegistro();
		const { user, onClose } = renderizar();

		await completar(user);

		expect(cuerpos).toEqual([
			{ name: 'Ada Lovelace', email: 'ada@kosmo.dev', password: CLAVE_VALIDA },
		]);
		expect(mockRouter.push).toHaveBeenCalledWith('/onboarding');
		expect(onClose).toHaveBeenCalledOnce();
		expect(useAuthStore.getState().accessToken).toBe('access-token-test');
	});

	it('bloquea el formulario mientras registra', async () => {
		server.use(
			http.post(apiUrl('/api/v1/auth/register'), async () => {
				await delay('infinite');
				return HttpResponse.json({});
			}),
		);
		const { user } = renderizar();

		await completar(user);

		expect(screen.getByRole('button', { name: 'Registrando...' })).toBeDisabled();
		Object.values(campos()).forEach((campo) => expect(campo).toBeDisabled());
	});

	describe('errores del servidor', () => {
		it.each([
			[409, {}, {}, 'Este correo ya está registrado'],
			[
				429,
				{},
				{ 'Retry-After': '60' },
				'Demasiadas solicitudes. Intente de nuevo en 60 segundos.',
			],
			[429, {}, {}, 'Demasiadas solicitudes. Intente de nuevo más tarde.'],
			[500, { detail: 'Error inesperado' }, {}, 'Error inesperado'],
		])('HTTP %i muestra el mensaje adecuado', async (status, body, headers, mensaje) => {
			capturarRegistro(() => HttpResponse.json(body, { status, headers }));
			const { user, onClose } = renderizar();

			await completar(user);

			expect(await screen.findByText(mensaje)).toBeInTheDocument();
			expect(mockRouter.push).not.toHaveBeenCalled();
			expect(onClose).not.toHaveBeenCalled();
			expect(botonRegistrarse()).toBeEnabled();
		});

		it('si el registro funciona pero el login falla, no navega', async () => {
			capturarRegistro();
			server.use(
				http.post(apiUrl('/api/v1/auth/authorize'), () =>
					HttpResponse.json(
						{ detail: 'Cuenta pendiente de activación' },
						{ status: 403 },
					),
				),
			);
			const { user } = renderizar();

			await completar(user);

			expect(
				await screen.findByText('Cuenta pendiente de activación'),
			).toBeInTheDocument();
			expect(mockRouter.push).not.toHaveBeenCalled();
		});
	});

	it('permite volver al inicio de sesión', async () => {
		const { user, onSwitchToLogin } = renderizar();

		await user.click(
			screen.getByRole('button', { name: '¿Ya tienes cuenta? Inicia sesión' }),
		);

		expect(onSwitchToLogin).toHaveBeenCalledOnce();
	});
});
