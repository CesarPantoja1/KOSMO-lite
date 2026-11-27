import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useProjectStore } from '@/entities/project';
import {
	HttpResponse,
	apiUrl,
	crearProyecto,
	crearSugerencia,
	http,
	server,
} from '@/test';
import { useCharacteristicModal } from './use-characteristic-modal';

const URL_SUGERENCIAS = '/api/v1/projects/:projectId/features/suggest';

function conSugerencias(
	sugerencias = [crearSugerencia(), crearSugerencia(), crearSugerencia()],
) {
	server.use(http.post(apiUrl(URL_SUGERENCIAS), () => HttpResponse.json(sugerencias)));
	return sugerencias;
}

const seleccionarProyecto = () =>
	useProjectStore.setState({ currentProject: crearProyecto({ id: 'prj_1' }) });

describe('useCharacteristicModal', () => {
	it('carga las sugerencias de la IA para el proyecto actual', async () => {
		seleccionarProyecto();
		const sugerencias = conSugerencias();
		const { result } = renderHook(() => useCharacteristicModal(vi.fn()));

		expect(result.current.isLoading).toBe(true);
		await waitFor(() => expect(result.current.isLoading).toBe(false));

		expect(result.current.alternatives).toEqual(sugerencias);
		expect(result.current.hasError).toBe(false);
	});

	it('marca hasError si la generación de sugerencias falla', async () => {
		seleccionarProyecto();
		server.use(
			http.post(apiUrl(URL_SUGERENCIAS), () => HttpResponse.json({}, { status: 500 })),
		);
		const { result } = renderHook(() => useCharacteristicModal(vi.fn()));

		await waitFor(() => expect(result.current.isLoading).toBe(false));

		expect(result.current.hasError).toBe(true);
		expect(result.current.alternatives).toEqual([]);
	});

	it('no solicita sugerencias si no hay proyecto seleccionado', async () => {
		const peticiones: string[] = [];
		server.use(
			http.post(apiUrl(URL_SUGERENCIAS), ({ request }) => {
				peticiones.push(request.url);
				return HttpResponse.json([]);
			}),
		);

		renderHook(() => useCharacteristicModal(vi.fn()));
		await new Promise((r) => setTimeout(r, 30));

		expect(peticiones).toHaveLength(0);
	});

	describe('selección', () => {
		it('selecciona una tarjeta y la deselecciona al pulsarla de nuevo', async () => {
			seleccionarProyecto();
			const [primera] = conSugerencias();
			const { result } = renderHook(() => useCharacteristicModal(vi.fn()));
			await waitFor(() => expect(result.current.isLoading).toBe(false));

			act(() => result.current.handleCardClick(primera.number));
			expect(result.current.selectedId).toBe(primera.number);

			act(() => result.current.handleCardClick(primera.number));
			expect(result.current.selectedId).toBeNull();
		});

		it('cambia la selección al pulsar otra tarjeta', async () => {
			seleccionarProyecto();
			const [primera, segunda] = conSugerencias();
			const { result } = renderHook(() => useCharacteristicModal(vi.fn()));
			await waitFor(() => expect(result.current.isLoading).toBe(false));

			act(() => result.current.handleCardClick(primera.number));
			act(() => result.current.handleCardClick(segunda.number));

			expect(result.current.selectedId).toBe(segunda.number);
		});
	});

	describe('handleApply', () => {
		it('entrega la sugerencia seleccionada a onApply', async () => {
			seleccionarProyecto();
			const [, segunda] = conSugerencias();
			const onApply = vi.fn();
			const { result } = renderHook(() => useCharacteristicModal(onApply));
			await waitFor(() => expect(result.current.isLoading).toBe(false));

			act(() => result.current.handleCardClick(segunda.number));
			act(() => result.current.handleApply());

			expect(onApply).toHaveBeenCalledExactlyOnceWith(segunda);
		});

		it('no hace nada si no hay ninguna sugerencia seleccionada', async () => {
			seleccionarProyecto();
			conSugerencias();
			const onApply = vi.fn();
			const { result } = renderHook(() => useCharacteristicModal(onApply));
			await waitFor(() => expect(result.current.isLoading).toBe(false));

			act(() => result.current.handleApply());

			expect(onApply).not.toHaveBeenCalled();
		});
	});
});
