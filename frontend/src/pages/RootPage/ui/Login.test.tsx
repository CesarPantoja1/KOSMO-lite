import { act, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '@/shared/model/auth-store';
import {
	HttpResponse,
	apiUrl,
	crearUsuario,
	delay,
	http,
	mockRouter,
	renderWithProviders,
	server,
} from '@/test';
import { Login } from './Login';

const campoCorreo = () => screen.getByPlaceholderText('tu@email.com');
const campoClave = () => screen.getByPlaceholderText('Tu contraseña');
const botonEntrar = () => screen.getByRole('button', { name: 'Entrar' });

function renderizar(props: Partial<Parameters<typeof Login>[0]> = {}, opciones = {}) {
	const onClose = vi.fn();
	const onSwitchToRegister = vi.fn();
	const utils = renderWithProviders(
		<Login onClose={onClose} onSwitchToRegister={onSwitchToRegister} {...props} />,
		opciones,
	);
	return { ...utils, onClose, onSwitchToRegister };
}

async function iniciarSesion(
	user: ReturnType<typeof renderizar>['user'],
	correo = 'ada@kosmo.dev',
) {
	await user.type(campoCorreo(), correo);
	await user.type(campoClave(), 'clave-secreta');
	await user.click(botonEntrar());
}

function fallarAutorizacion(
	status: number,
	body: object = {},
	headers: Record<string, string> = {},
) {
	server.use(
		http.post(apiUrl('/api/v1/auth/authorize'), () =>
			HttpResponse.json(body, { status, headers }),
		),
	);
}

describe('Login', () => {
	afterEach(() => {
		vi.useRealTimers();
	});

	it('exige correo y contraseña sin llamar al servidor', async () => {
		const peticiones: string[] = [];
		server.use(
			http.post(apiUrl('/api/v1/auth/authorize'), ({ request }) => {
				peticiones.push(request.url);
				return HttpResponse.json({});
			}),
		);
		const { user } = renderizar();

		await user.type(campoCorreo(), 'ada@kosmo.dev');
		await user.click(botonEntrar());

		expect(screen.getByText('Todos los campos son obligatorios')).toBeInTheDocument();
		expect(peticiones).toHaveLength(0);
	});

	it('con credenciales válidas inicia sesión, guarda el usuario y entra a los proyectos', async () => {
		const usuario = crearUsuario({ email: 'ada@kosmo.dev' });
		server.use(http.get(apiUrl('/api/v1/auth/me'), () => HttpResponse.json(usuario)));
		const { user, onClose } = renderizar();

		await iniciarSesion(user);

		expect(mockRouter.push).toHaveBeenCalledWith('/proyecto');
		expect(onClose).toHaveBeenCalledOnce();
		expect(useAuthStore.getState()).toMatchObject({
			accessToken: 'access-token-test',
			user: usuario,
		});
	});

	it('muestra el estado de carga y bloquea el formulario mientras inicia sesión', async () => {
		server.use(
			http.post(apiUrl('/api/v1/auth/authorize'), async () => {
				await delay('infinite');
				return HttpResponse.json({});
			}),
		);
		const { user } = renderizar();

		await iniciarSesion(user);

		expect(screen.getByRole('button', { name: 'Iniciando...' })).toBeDisabled();
		expect(campoCorreo()).toBeDisabled();
		expect(campoClave()).toBeDisabled();
	});

	it('informa de credenciales inválidas (401)', async () => {
		fallarAutorizacion(401, { error: 'invalid_grant' });
		const { user, onClose } = renderizar();

		await iniciarSesion(user);

		expect(await screen.findByText('Credenciales inválidas')).toBeInTheDocument();
		expect(mockRouter.push).not.toHaveBeenCalled();
		expect(onClose).not.toHaveBeenCalled();
		expect(botonEntrar()).toBeEnabled();
	});

	describe('bloqueo por demasiados intentos (429)', () => {
		it('bloquea el formulario con una cuenta regresiva y lo libera al terminar', async () => {
			vi.useFakeTimers({ shouldAdvanceTime: true });
			fallarAutorizacion(429, {}, { 'Retry-After': '3' });
			const { user } = renderizar(
				{},
				{ userEventOptions: { advanceTimers: vi.advanceTimersByTime } },
			);

			await iniciarSesion(user);

			expect(
				await screen.findByText('Cuenta bloqueada. Intente de nuevo en 3 segundos.'),
			).toBeInTheDocument();
			expect(screen.getByRole('button', { name: 'Espera 3s' })).toBeDisabled();

			await act(() => vi.advanceTimersByTimeAsync(1_000));
			expect(screen.getByRole('button', { name: 'Espera 2s' })).toBeDisabled();

			await act(() => vi.advanceTimersByTimeAsync(2_000));
			expect(botonEntrar()).toBeEnabled();
			expect(screen.queryByText(/Cuenta bloqueada/)).not.toBeInTheDocument();
		});

		it('usa los segundos restantes del cuerpo si no hay cabecera Retry-After', async () => {
			fallarAutorizacion(429, { seconds_remaining: 42 });
			const { user } = renderizar();

			await iniciarSesion(user);

			expect(
				await screen.findByText('Cuenta bloqueada. Intente de nuevo en 42 segundos.'),
			).toBeInTheDocument();
		});

		it('aplica 300 segundos por defecto si el servidor no indica el tiempo', async () => {
			fallarAutorizacion(429);
			const { user } = renderizar();

			await iniciarSesion(user);

			expect(
				await screen.findByText('Cuenta bloqueada. Intente de nuevo en 300 segundos.'),
			).toBeInTheDocument();
		});
	});

	it('muestra el mensaje del servidor ante otros errores', async () => {
		fallarAutorizacion(503, { detail: 'Servicio de autenticación no disponible' });
		const { user } = renderizar();

		await iniciarSesion(user);

		expect(
			await screen.findByText('Servicio de autenticación no disponible'),
		).toBeInTheDocument();
	});

	it('avisa cuando la sesión anterior expiró', () => {
		renderizar({ sessionExpired: true });

		expect(screen.getByText(/Tu sesión ha expirado/)).toBeInTheDocument();
	});

	it('permite cambiar al registro', async () => {
		const { user, onSwitchToRegister } = renderizar();

		await user.click(
			screen.getByRole('button', { name: '¿No tienes cuenta? Regístrate' }),
		);

		expect(onSwitchToRegister).toHaveBeenCalledOnce();
	});

	it('el botón de cierre (solo ícono) cierra el modal', async () => {
		const { user, onClose, container } = renderizar();

		await user.click(container.querySelector('button[type="button"]')!);

		expect(onClose).toHaveBeenCalledOnce();
	});

	it('los campos usan el tipo y autocompletado correctos', () => {
		renderizar();

		expect(campoCorreo()).toHaveAttribute('type', 'email');
		expect(campoCorreo()).toHaveAttribute('autocomplete', 'email');
		expect(campoClave()).toHaveAttribute('type', 'password');
		expect(campoClave()).toHaveAttribute('autocomplete', 'current-password');
	});
});
