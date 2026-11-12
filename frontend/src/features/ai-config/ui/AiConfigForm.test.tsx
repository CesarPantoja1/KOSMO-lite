import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useAiConfigStore } from '@/entities/ai-config';
import type { AIConfigView } from '@/entities/ai-config/model/types';
import {
	HttpResponse,
	apiUrl,
	crearAiConfig,
	crearProveedoresIA,
	http,
	renderWithProviders,
	server,
} from '@/test';
import { AiConfigForm } from './AiConfigForm';

const selects = () => {
	const [proveedor, modelo] = screen.getAllByRole('combobox') as HTMLSelectElement[];
	return { proveedor, modelo };
};

function renderizar(
	config: AIConfigView | null,
	props: Parameters<typeof AiConfigForm>[0] = {},
) {
	useAiConfigStore.setState({ config });
	return renderWithProviders(<AiConfigForm {...props} />);
}

const SIN_CLAVE = () =>
	crearAiConfig({ has_api_key: false, masked_key: null, provider: null, model: null });

async function abrirEdicion(user: ReturnType<typeof renderizar>['user'], boton: RegExp) {
	await user.click(screen.getByRole('button', { name: boton }));
	// El catálogo de proveedores llega desde el servidor (MSW).
	await waitFor(() =>
		expect(within(selects().proveedor).getAllByRole('option')).toHaveLength(2),
	);
}

function capturarGuardado(respuesta?: () => Response) {
	const cuerpos: unknown[] = [];
	server.use(
		http.post(apiUrl('/api/v1/ai-config'), async ({ request }) => {
			const body = (await request.json()) as { provider: string; model: string };
			cuerpos.push(body);
			return (
				respuesta?.() ??
				HttpResponse.json(
					crearAiConfig({
						provider: body.provider as never,
						model: body.model,
						masked_key: '••••••••abcd',
					}),
				)
			);
		}),
	);
	return cuerpos;
}

describe('AiConfigForm', () => {
	describe('sin clave configurada', () => {
		it('indica que no hay clave y ofrece agregarla', () => {
			renderizar(SIN_CLAVE());

			expect(screen.getByText('No hay clave de API configurada')).toBeInTheDocument();
			expect(screen.getByRole('button', { name: 'Agregar API Key' })).toBeInTheDocument();
			expect(screen.queryByText('Configurado')).not.toBeInTheDocument();
		});

		it('al agregar muestra el proveedor y modelo por defecto', async () => {
			const { user } = renderizar(SIN_CLAVE());

			await abrirEdicion(user, /Agregar API Key/);

			expect(selects().proveedor).toHaveValue('google');
			expect(selects().modelo).toHaveValue('gemini-3.8-flash');
			expect(screen.getByPlaceholderText('sk-...')).toHaveValue('');
		});
	});

	describe('con clave configurada', () => {
		it('muestra la clave enmascarada y el estado "Configurado"', () => {
			renderizar(crearAiConfig({ masked_key: '••••••••9f2a' }));

			expect(screen.getByText('••••••••9f2a')).toBeInTheDocument();
			expect(screen.getByText('Configurado')).toBeInTheDocument();
			expect(screen.getByRole('button', { name: 'Reemplazar' })).toBeInTheDocument();
			expect(screen.getByRole('button', { name: 'Eliminar' })).toBeInTheDocument();
		});

		it('al reemplazar precarga el proveedor y modelo actuales', async () => {
			const { user } = renderizar(
				crearAiConfig({ provider: 'anthropic', model: 'claude-sonnet-5-5' }),
			);

			await abrirEdicion(user, /Reemplazar/);

			expect(selects().proveedor).toHaveValue('anthropic');
			expect(selects().modelo).toHaveValue('claude-sonnet-5-5');
			expect(screen.queryByText('Configurado')).not.toBeInTheDocument();
		});
	});

	describe('selección de modelo', () => {
		it('agrupa los modelos por nivel y marca los deprecados', async () => {
			const { user } = renderizar(SIN_CLAVE());
			await abrirEdicion(user, /Agregar API Key/);

			await user.selectOptions(selects().proveedor, 'anthropic');

			const grupos = selects().modelo.querySelectorAll('optgroup');
			expect(Array.from(grupos, (g) => g.label)).toEqual([
				'— Máxima capacidad',
				'— Equilibrado',
			]);
			expect(
				screen.getByRole('option', { name: 'Claude Legacy (Deprecado)' }),
			).toBeInTheDocument();
		});

		it('al cambiar de proveedor elige su primer modelo si el actual no existe', async () => {
			const { user } = renderizar(SIN_CLAVE());
			await abrirEdicion(user, /Agregar API Key/);

			await user.selectOptions(selects().proveedor, 'anthropic');

			expect(selects().modelo).toHaveValue(crearProveedoresIA()[1].models[0].id);
		});
	});

	describe('clave de API', () => {
		it('se oculta por defecto y puede mostrarse', async () => {
			const { user } = renderizar(SIN_CLAVE());
			await abrirEdicion(user, /Agregar API Key/);
			const campo = screen.getByPlaceholderText('sk-...');

			expect(campo).toHaveAttribute('type', 'password');
			await user.click(screen.getByRole('button', { name: 'Mostrar' }));
			expect(campo).toHaveAttribute('type', 'text');
			await user.click(screen.getByRole('button', { name: 'Ocultar' }));
			expect(campo).toHaveAttribute('type', 'password');
		});

		it.each([
			['vacía', ''],
			['con solo espacios', '   '],
		])('no permite guardar con una clave %s', async (_caso, clave) => {
			const { user } = renderizar(SIN_CLAVE());
			await abrirEdicion(user, /Agregar API Key/);

			if (clave) await user.type(screen.getByPlaceholderText('sk-...'), clave);

			expect(screen.getByRole('button', { name: 'Guardar' })).toBeDisabled();
		});
	});

	describe('guardar', () => {
		it('envía proveedor, modelo y clave sin espacios; luego vuelve a la vista', async () => {
			const cuerpos = capturarGuardado();
			const onSaved = vi.fn();
			const { user } = renderizar(SIN_CLAVE(), { onSaved });
			await abrirEdicion(user, /Agregar API Key/);

			await user.selectOptions(selects().proveedor, 'anthropic');
			await user.selectOptions(selects().modelo, 'claude-opus-5-5');
			await user.type(screen.getByPlaceholderText('sk-...'), '  sk-ant-secreta  ');
			await user.click(screen.getByRole('button', { name: 'Guardar' }));

			expect(
				await screen.findByText('Configuración de IA guardada correctamente'),
			).toBeInTheDocument();
			expect(cuerpos).toEqual([
				{ provider: 'anthropic', model: 'claude-opus-5-5', api_key: 'sk-ant-secreta' },
			]);
			expect(onSaved).toHaveBeenCalledOnce();
			expect(screen.getByText('••••••••abcd')).toBeInTheDocument();
			expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
		});

		it('si la clave es rechazada muestra el error y sigue en edición', async () => {
			capturarGuardado(() =>
				HttpResponse.json(
					{
						type: 'urn:kosmo:ai:invalid-key',
						detail: 'La clave no es válida para Anthropic',
					},
					{ status: 400 },
				),
			);
			const onSaved = vi.fn();
			const { user } = renderizar(SIN_CLAVE(), { onSaved });
			await abrirEdicion(user, /Agregar API Key/);

			await user.type(screen.getByPlaceholderText('sk-...'), 'sk-mala');
			await user.click(screen.getByRole('button', { name: 'Guardar' }));

			expect(
				await screen.findAllByText('La clave no es válida para Anthropic'),
			).not.toHaveLength(0);
			expect(onSaved).not.toHaveBeenCalled();
			expect(screen.getByPlaceholderText('sk-...')).toHaveValue('sk-mala');
		});
	});

	it('eliminar borra la clave y vuelve al estado sin configurar', async () => {
		const metodos: string[] = [];
		server.use(
			http.delete(apiUrl('/api/v1/ai-config'), ({ request }) => {
				metodos.push(request.method);
				return new HttpResponse(null, { status: 204 });
			}),
		);
		const onSaved = vi.fn();
		const { user } = renderizar(crearAiConfig(), { onSaved });

		await user.click(screen.getByRole('button', { name: 'Eliminar' }));

		expect(
			await screen.findByText('No hay clave de API configurada'),
		).toBeInTheDocument();
		expect(metodos).toEqual(['DELETE']);
		expect(onSaved).toHaveBeenCalledOnce();
		expect(screen.getByText(/Clave de API eliminada/)).toBeInTheDocument();
	});

	it('cancelar descarta los cambios y restaura la configuración guardada', async () => {
		const { user } = renderizar(
			crearAiConfig({ provider: 'google', model: 'gemini-3.8-pro' }),
		);
		await abrirEdicion(user, /Reemplazar/);
		await user.selectOptions(selects().proveedor, 'anthropic');
		await user.type(screen.getByPlaceholderText('••••••••****'), 'sk-temporal');

		await user.click(screen.getByRole('button', { name: 'Cancelar' }));
		await abrirEdicion(user, /Reemplazar/);

		expect(selects().proveedor).toHaveValue('google');
		expect(selects().modelo).toHaveValue('gemini-3.8-pro');
		expect(screen.getByPlaceholderText('••••••••****')).toHaveValue('');
	});

	it('muestra el error del store si lo hay', () => {
		useAiConfigStore.setState({ error: 'No se pudo cargar la configuración' });

		renderizar(SIN_CLAVE());

		expect(screen.getByText('No se pudo cargar la configuración')).toBeInTheDocument();
	});
});
