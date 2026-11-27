import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HttpResponse, apiUrl, crearEstadoConsistencia, delay, http, server } from '@/test';
import { useConsistencyPolling } from './useConsistencyPolling';

const URL_STATUS = '/api/v1/projects/:projectId/consistency/status';

/** Avanza el reloj simulado dejando que React y MSW procesen las promesas pendientes. */
const avanzar = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

function simularVisibilidad(estado: DocumentVisibilityState) {
	Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => estado });
}

/** Cuenta las peticiones de estado por proyecto y responde con `pending` = nº de petición. */
function contarPeticiones() {
	const peticiones: string[] = [];
	server.use(
		http.get(apiUrl(URL_STATUS), ({ params }) => {
			peticiones.push(String(params.projectId));
			return HttpResponse.json(
				crearEstadoConsistencia({
					features: { pending: peticiones.length, evaluating: 0, failed: 0 },
				}),
			);
		}),
	);
	return peticiones;
}

describe('useConsistencyPolling', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		simularVisibilidad('visible');
	});

	afterEach(() => {
		vi.useRealTimers();
		simularVisibilidad('visible');
	});

	it('carga el estado inmediatamente al montar', async () => {
		const peticiones = contarPeticiones();
		const { result } = renderHook(() => useConsistencyPolling('prj_1'));

		await avanzar(0);

		expect(peticiones).toEqual(['prj_1']);
		expect(result.current.status?.phases.features.pending).toBe(1);
		expect(result.current.error).toBeNull();
	});

	it('vuelve a consultar en cada intervalo (10 s por defecto)', async () => {
		const peticiones = contarPeticiones();
		renderHook(() => useConsistencyPolling('prj_1'));

		await avanzar(0);
		await avanzar(10_000);
		await avanzar(10_000);

		expect(peticiones).toHaveLength(3);
	});

	it('respeta un intervalo personalizado', async () => {
		const peticiones = contarPeticiones();
		renderHook(() => useConsistencyPolling('prj_1', { intervalMs: 2_000 }));

		await avanzar(0);
		await avanzar(6_000);

		expect(peticiones).toHaveLength(4);
	});

	it.each([
		['sin proyecto seleccionado', null, true],
		['deshabilitado', 'prj_1', false],
	])('no consulta nada cuando está %s', async (_caso, projectId, enabled) => {
		const peticiones = contarPeticiones();
		const { result } = renderHook(() => useConsistencyPolling(projectId, { enabled }));

		await avanzar(30_000);

		expect(peticiones).toHaveLength(0);
		expect(result.current.status).toBeNull();
		expect(result.current.isLoading).toBe(false);
	});

	it('no consulta en el intervalo si la pestaña está oculta', async () => {
		const peticiones = contarPeticiones();
		renderHook(() => useConsistencyPolling('prj_1'));
		await avanzar(0);

		simularVisibilidad('hidden');
		await avanzar(30_000);

		expect(peticiones).toHaveLength(1);
	});

	it('refresca al volver a la pestaña (visibilitychange) y al recuperar el foco', async () => {
		const peticiones = contarPeticiones();
		renderHook(() => useConsistencyPolling('prj_1'));
		await avanzar(0);

		await act(async () => {
			document.dispatchEvent(new Event('visibilitychange'));
		});
		await avanzar(0);
		await act(async () => {
			window.dispatchEvent(new Event('focus'));
		});
		await avanzar(0);

		expect(peticiones).toHaveLength(3);
	});

	it('expone el error y conserva el último estado válido', async () => {
		contarPeticiones();
		const { result } = renderHook(() => useConsistencyPolling('prj_1'));
		await avanzar(0);
		const estadoPrevio = result.current.status;

		server.use(
			http.get(apiUrl(URL_STATUS), () => HttpResponse.json({ detail: 'caído' }, { status: 503 })),
		);
		await avanzar(10_000);

		expect(result.current.error).toMatchObject({ status: 503 });
		expect(result.current.status).toEqual(estadoPrevio);
	});

	it('limpia el error tras una consulta exitosa', async () => {
		server.use(
			http.get(apiUrl(URL_STATUS), () => HttpResponse.json({}, { status: 500 }), { once: true }),
		);
		const { result } = renderHook(() => useConsistencyPolling('prj_1'));
		await avanzar(0);
		expect(result.current.error).not.toBeNull();

		await avanzar(10_000);

		expect(result.current.error).toBeNull();
		expect(result.current.status).not.toBeNull();
	});

	it('marca isLoading mientras la petición está en curso', async () => {
		server.use(
			http.get(apiUrl(URL_STATUS), async () => {
				await delay(500);
				return HttpResponse.json(crearEstadoConsistencia());
			}),
		);
		const { result } = renderHook(() => useConsistencyPolling('prj_1'));

		await avanzar(0);
		expect(result.current.isLoading).toBe(true);

		await avanzar(500);
		expect(result.current.isLoading).toBe(false);
	});

	it('no lanza peticiones concurrentes si ya hay una en curso', async () => {
		const peticiones: number[] = [];
		server.use(
			http.get(apiUrl(URL_STATUS), async () => {
				peticiones.push(Date.now());
				await delay(1_000);
				return HttpResponse.json(crearEstadoConsistencia());
			}),
		);
		const { result } = renderHook(() => useConsistencyPolling('prj_1'));
		await avanzar(0);

		await act(async () => {
			void result.current.refresh();
			void result.current.refresh();
		});
		await avanzar(1_000);

		expect(peticiones).toHaveLength(1);
	});

	it('deja de consultar al desmontarse', async () => {
		const peticiones = contarPeticiones();
		const { unmount } = renderHook(() => useConsistencyPolling('prj_1'));
		await avanzar(0);

		unmount();
		await avanzar(60_000);
		window.dispatchEvent(new Event('focus'));

		expect(peticiones).toHaveLength(1);
	});

	it('reinicia el polling al cambiar de proyecto', async () => {
		const peticiones = contarPeticiones();
		const { rerender } = renderHook(({ id }) => useConsistencyPolling(id), {
			initialProps: { id: 'prj_1' },
		});
		await avanzar(0);

		rerender({ id: 'prj_2' });
		await avanzar(0);
		await avanzar(10_000);

		expect(peticiones).toEqual(['prj_1', 'prj_2', 'prj_2']);
	});
});
