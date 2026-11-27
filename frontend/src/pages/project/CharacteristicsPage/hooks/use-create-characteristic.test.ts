import { act, renderHook } from '@testing-library/react';
import type { ChangeEvent, FormEvent } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { useCharacteristicStore } from '@/entities/characteristic';
import type { CreateCharacteristicResponse } from '@/entities/characteristic/model/types';
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
import { useCreateCharacteristic } from './use-create-characteristic';

const URL_MANUAL = '/api/v1/projects/:projectId/features/manual';

const cambioTitulo = (value: string) =>
	({ target: { value, name: 'title' } }) as ChangeEvent<HTMLInputElement>;
const cambioDescripcion = (value: string) =>
	({ target: { value, name: 'description' } }) as ChangeEvent<HTMLTextAreaElement>;
const eventoSubmit = () =>
	({
		preventDefault: vi.fn(),
		persist: vi.fn(),
	}) as unknown as FormEvent<HTMLFormElement>;

function respuestaGuardado(overrides: Partial<CreateCharacteristicResponse> = {}) {
	const cuerpos: unknown[] = [];
	server.use(
		http.post(apiUrl(URL_MANUAL), async ({ request }) => {
			cuerpos.push(await request.json());
			return HttpResponse.json<CreateCharacteristicResponse>({
				is_saved: true,
				feature: crearCaracteristica({ title: 'Inicio de sesion' }),
				origin: 'manual',
				is_consistent: true,
				...overrides,
			});
		}),
	);
	return cuerpos;
}

function renderizar({ conProyecto = true } = {}) {
	if (conProyecto)
		useProjectStore.setState({ currentProject: crearProyecto({ id: 'prj_1' }) });
	return renderHook(() => useCreateCharacteristic());
}

type Hook = ReturnType<typeof renderizar>['result'];

function escribir(result: Hook, titulo: string, descripcion: string) {
	act(() => result.current.handleTitleChange(cambioTitulo(titulo)));
	act(() => result.current.handleDescChange(cambioDescripcion(descripcion)));
}

const enviar = (result: Hook) =>
	act(async () => result.current.handleSubmit(eventoSubmit()));

describe('useCreateCharacteristic', () => {
	it('inicia con el formulario vacío y sin errores', () => {
		const { result } = renderizar();

		expect(result.current).toMatchObject({
			titleValue: '',
			descValue: '',
			titleCount: 0,
			descCount: 0,
			fieldErrors: { title: '', description: '' },
			showSuggestionsModal: false,
			showConsistencyModal: false,
			isValidating: false,
		});
	});

	describe('sanitización de la entrada', () => {
		it.each([
			['números y símbolos', 'Login 2.0!', 'Login '],
			['tildes y eñes (se conservan)', 'Gestión de añadidos', 'Gestión de añadidos'],
			['emojis', 'Pagos 💳', 'Pagos '],
		])('el título elimina %s', (_caso, entrada, esperado) => {
			const { result } = renderizar();

			act(() => result.current.handleTitleChange(cambioTitulo(entrada)));

			expect(result.current.titleValue).toBe(esperado);
			expect(result.current.titleCount).toBe(esperado.length);
		});

		it.each([
			[
				'signos permitidos (se conservan)',
				'¿Valida? Sí: 3 intentos (máx.)',
				'¿Valida? Sí: 3 intentos (máx.)',
			],
			['HTML', '<b>negrita</b>', 'bnegritab'],
			['arrobas y comillas', 'Escribe a "soporte@kosmo"', 'Escribe a soportekosmo'],
		])(
			'la descripción elimina caracteres no permitidos: %s',
			(_caso, entrada, esperado) => {
				const { result } = renderizar();

				act(() => result.current.handleDescChange(cambioDescripcion(entrada)));

				expect(result.current.descValue).toBe(esperado);
				expect(result.current.descCount).toBe(esperado.length);
			},
		);
	});

	describe('validación al enviar', () => {
		it('exige título y descripción', async () => {
			const cuerpos = respuestaGuardado();
			const { result } = renderizar();

			await enviar(result);

			expect(result.current.fieldErrors).toEqual({
				title: 'Este campo es obligatorio',
				description: 'Este campo es obligatorio',
			});
			expect(cuerpos).toHaveLength(0);
		});

		it('considera vacío un campo con solo espacios', async () => {
			const { result } = renderizar();
			escribir(result, '   ', 'Descripción válida');

			await enviar(result);

			expect(result.current.fieldErrors.title).toBe('Este campo es obligatorio');
			expect(result.current.fieldErrors.description).toBe('');
		});

		it('limpia el error de un campo cuando el usuario vuelve a escribir', async () => {
			const { result } = renderizar();
			await enviar(result);

			act(() => result.current.handleTitleChange(cambioTitulo('L')));

			expect(result.current.fieldErrors).toEqual({
				title: '',
				description: 'Este campo es obligatorio',
			});
		});

		it('no envía nada si no hay proyecto seleccionado', async () => {
			const cuerpos = respuestaGuardado();
			const { result } = renderizar({ conProyecto: false });
			escribir(result, 'Inicio de sesion', 'Permite autenticarse.');

			await enviar(result);

			expect(cuerpos).toHaveLength(0);
		});
	});

	describe('guardado', () => {
		it('guarda la característica, la añade al store y vuelve al listado', async () => {
			const cuerpos = respuestaGuardado();
			const { result } = renderizar();
			escribir(result, 'Inicio de sesion', 'Permite autenticarse con correo.');

			await enviar(result);

			expect(cuerpos).toEqual([
				{
					title: 'Inicio de sesion',
					description: 'Permite autenticarse con correo.',
					origin: '',
				},
			]);
			expect(useCharacteristicStore.getState().currentCharacteristics).toHaveLength(1);
			expect(mockRouter.push).toHaveBeenCalledWith('/proyecto/caracteristicas');
			expect(result.current.isValidating).toBe(false);
		});

		it('muestra una advertencia si la característica se solapa con otras', async () => {
			respuestaGuardado({ warnings: ['Se parece a F-001', 'Se parece a F-004'] });
			const toastWarning = vi.spyOn(toast, 'warning');
			const { result } = renderizar();
			escribir(result, 'Inicio de sesion', 'Permite autenticarse.');

			await enviar(result);

			expect(toastWarning).toHaveBeenCalledWith(
				'Se parece a F-001\nSe parece a F-004',
				undefined,
				'Advertencia de solapamiento',
			);
			expect(mockRouter.push).toHaveBeenCalledWith('/proyecto/caracteristicas');
		});

		it('abre el modal de consistencia si la IA rechaza la característica', async () => {
			respuestaGuardado({
				is_saved: false,
				feature: undefined,
				origin: 'Descubrimiento',
				is_consistent: false,
				inconsistency_reason: 'Contradice el alcance definido',
			});
			const { result } = renderizar();
			escribir(result, 'Juegos', 'Agrega un minijuego.');

			await enviar(result);

			expect(result.current.showConsistencyModal).toBe(true);
			expect(result.current.consistencyInfo).toEqual({
				origin: 'Descubrimiento',
				reason: 'Contradice el alcance definido',
			});
			expect(mockRouter.push).not.toHaveBeenCalled();
			expect(useCharacteristicStore.getState().currentCharacteristics).toHaveLength(0);

			act(() => result.current.closeConsistencyModal());
			expect(result.current.showConsistencyModal).toBe(false);
		});

		it('muestra un toast de error si el guardado falla', async () => {
			server.use(
				http.post(apiUrl(URL_MANUAL), () =>
					HttpResponse.json({ detail: 'Servicio de IA no disponible' }, { status: 503 }),
				),
			);
			const toastError = vi.spyOn(toast, 'error');
			const { result } = renderizar();
			escribir(result, 'Inicio de sesion', 'Permite autenticarse.');

			await enviar(result);

			expect(toastError).toHaveBeenCalledWith('Servicio de IA no disponible');
			expect(result.current.isValidating).toBe(false);
			expect(mockRouter.push).not.toHaveBeenCalled();
		});
	});

	describe('sugerencias y navegación', () => {
		it('abre y cierra el modal de sugerencias', () => {
			const { result } = renderizar();

			act(() => result.current.openSuggestionsModal());
			expect(result.current.showSuggestionsModal).toBe(true);

			act(() => result.current.closeSuggestionsModal());
			expect(result.current.showSuggestionsModal).toBe(false);
		});

		it('aplicar una sugerencia rellena el formulario y cierra el modal', () => {
			const { result } = renderizar();
			act(() => result.current.openSuggestionsModal());

			act(() => result.current.applySuggestion('Registro', 'Alta de nuevos usuarios.'));

			expect(result.current.titleValue).toBe('Registro');
			expect(result.current.descValue).toBe('Alta de nuevos usuarios.');
			expect(result.current.showSuggestionsModal).toBe(false);
		});

		it('cancelar vuelve al listado de características', () => {
			const { result } = renderizar();

			act(() => result.current.handleCancel());

			expect(mockRouter.push).toHaveBeenCalledWith('/proyecto/caracteristicas');
		});
	});
});
