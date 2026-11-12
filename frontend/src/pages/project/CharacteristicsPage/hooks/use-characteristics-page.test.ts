import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useCharacteristicStore } from '@/entities/characteristic';
import { useProjectStore } from '@/entities/project';
import { toast } from '@/shared/ui/toast/toast';
import {
	HttpResponse,
	apiUrl,
	crearCaracteristica,
	crearProyecto,
	http,
	mockRouter,
	server,
} from '@/test';
import { useCharacteristicsPage } from './use-characteristics-page';

const URL_FEATURES = '/api/v1/projects/:projectId/features';

function conCaracteristicas(titulos: string[]) {
	const lista = titulos.map((title) => crearCaracteristica({ title }));
	server.use(http.get(apiUrl(URL_FEATURES), () => HttpResponse.json(lista)));
	return lista;
}

const seleccionarProyecto = () =>
	useProjectStore.setState({ currentProject: crearProyecto({ id: 'prj_1' }) });

async function renderizarCargado() {
	const hook = renderHook(() => useCharacteristicsPage());
	await waitFor(() => expect(hook.result.current.isLoading).toBe(false));
	return hook;
}

describe('useCharacteristicsPage', () => {
	it('redirige a la lista de proyectos si no hay proyecto seleccionado', () => {
		renderHook(() => useCharacteristicsPage());

		expect(mockRouter.push).toHaveBeenCalledWith('/proyecto');
	});

	it('carga las características del proyecto y las guarda en el store', async () => {
		seleccionarProyecto();
		const lista = conCaracteristicas(['Login', 'Registro']);

		const { result } = await renderizarCargado();

		expect(result.current.characteristics).toEqual(lista);
		expect(result.current.hasCharacteristics).toBe(true);
		expect(useCharacteristicStore.getState().currentCharacteristics).toEqual(lista);
		expect(mockRouter.push).not.toHaveBeenCalled();
	});

	it('indica que no hay características cuando la lista está vacía', async () => {
		seleccionarProyecto();
		conCaracteristicas([]);

		const { result } = await renderizarCargado();

		expect(result.current.hasCharacteristics).toBe(false);
	});

	describe('búsqueda', () => {
		it.each([
			['coincidencia exacta', 'Login', ['Login']],
			['sin distinguir mayúsculas', 'LOGIN', ['Login']],
			['coincidencia parcial', 'reg', ['Registro', 'Registro de pagos']],
			['sin resultados', 'xyz', []],
		])('filtra por título: %s', async (_caso, consulta, esperados) => {
			seleccionarProyecto();
			conCaracteristicas(['Login', 'Registro', 'Registro de pagos']);
			const { result } = await renderizarCargado();

			act(() => result.current.setSearchQuery(consulta));

			expect(result.current.filtered.map((c) => c.title)).toEqual(esperados);
			expect(result.current.searchQuery).toBe(consulta);
		});

		it('una búsqueda con solo espacios muestra todas las características', async () => {
			seleccionarProyecto();
			conCaracteristicas(['Login', 'Registro']);
			const { result } = await renderizarCargado();

			act(() => result.current.setSearchQuery('   '));

			expect(result.current.filtered).toHaveLength(2);
		});
	});

	describe('errores', () => {
		it('trata un 404 como lista vacía sin mostrar error', async () => {
			seleccionarProyecto();
			useCharacteristicStore.setState({
				currentCharacteristics: [crearCaracteristica()],
			});
			const toastError = vi.spyOn(toast, 'error');
			server.use(
				http.get(apiUrl(URL_FEATURES), () =>
					HttpResponse.json(
						{ detail: 'El proyecto no tiene características' },
						{ status: 404 },
					),
				),
			);

			const { result } = await renderizarCargado();

			expect(result.current.characteristics).toEqual([]);
			expect(toastError).not.toHaveBeenCalled();
		});

		it('muestra un toast con el mensaje del servidor ante otros errores', async () => {
			seleccionarProyecto();
			const toastError = vi.spyOn(toast, 'error');
			server.use(
				http.get(apiUrl(URL_FEATURES), () =>
					HttpResponse.json({ detail: 'Base de datos no disponible' }, { status: 500 }),
				),
			);

			await renderizarCargado();

			expect(toastError).toHaveBeenCalledWith('Base de datos no disponible');
		});

		it('usa un mensaje genérico si el error no trae detalle', async () => {
			seleccionarProyecto();
			const toastError = vi.spyOn(toast, 'error');
			server.use(http.get(apiUrl(URL_FEATURES), () => HttpResponse.error()));

			await renderizarCargado();

			expect(toastError).toHaveBeenCalledOnce();
			expect(toastError.mock.calls[0][0]).not.toBe('');
		});
	});

	it('refetch() vuelve a consultar el backend', async () => {
		seleccionarProyecto();
		conCaracteristicas(['Login']);
		const { result } = await renderizarCargado();

		const nuevas = conCaracteristicas(['Login', 'Registro']);
		await act(() => result.current.refetch());

		expect(result.current.characteristics).toEqual(nuevas);
	});
});
