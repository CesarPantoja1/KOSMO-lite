import { describe, expect, it } from 'vitest';
import { characteristicSchema, type CharacteristicFormData } from './types';

const MSG_TITULO = 'Solo se permiten letras y espacios';
const MSG_DESCRIPCION = 'Solo se permiten letras, números y signos de puntuación básicos';

const datos = (
	overrides: Partial<CharacteristicFormData> = {},
): CharacteristicFormData => ({
	title: 'Inicio de sesión',
	description: 'El usuario puede autenticarse con correo y contraseña.',
	...overrides,
});

const erroresDe = (data: unknown, campo: keyof CharacteristicFormData) => {
	const result = characteristicSchema.safeParse(data);
	if (result.success) return [];
	return result.error.issues.filter((i) => i.path[0] === campo).map((i) => i.message);
};

describe('characteristicSchema', () => {
	it('acepta una característica válida', () => {
		expect(characteristicSchema.safeParse(datos()).success).toBe(true);
	});

	describe('campo title', () => {
		it.each([
			['vacío', ''],
			['con tildes y eñes', 'Gestión de añadidos'],
			['con diéresis', 'Pingüino'],
			['de 50 caracteres (máximo)', 'a'.repeat(50)],
		])('acepta un título %s', (_caso, title) => {
			expect(erroresDe(datos({ title }), 'title')).toEqual([]);
		});

		it.each([
			['de 51 caracteres', 'a'.repeat(51), 'Máximo 50 caracteres'],
			['con números', 'Login 2', MSG_TITULO],
			['con signos de puntuación', 'Login, registro', MSG_TITULO],
			['con emojis', 'Login 🔐', MSG_TITULO],
		])('rechaza un título %s', (_caso, title, mensaje) => {
			expect(erroresDe(datos({ title }), 'title')).toContain(mensaje);
		});
	});

	describe('campo description', () => {
		it.each([
			['vacía', ''],
			['con números', 'Permite hasta 3 intentos por minuto.'],
			[
				'con todos los signos permitidos',
				'¿Qué hace? Valida: correo; clave (8-16), y avisa ¡ya!',
			],
			['de 500 caracteres (máximo)', 'a'.repeat(500)],
		])('acepta una descripción %s', (_caso, description) => {
			expect(erroresDe(datos({ description }), 'description')).toEqual([]);
		});

		it.each([
			['de 501 caracteres', 'a'.repeat(501), 'Máximo 500 caracteres'],
			['con arroba', 'Escribe a soporte@kosmo.dev', MSG_DESCRIPCION],
			['con comillas', 'El botón "Guardar"', MSG_DESCRIPCION],
			['con etiquetas HTML', '<script>alert(1)</script>', MSG_DESCRIPCION],
			['con emojis', 'Funciona bien ✅', MSG_DESCRIPCION],
		])('rechaza una descripción %s', (_caso, description, mensaje) => {
			expect(erroresDe(datos({ description }), 'description')).toContain(mensaje);
		});
	});

	it('reporta errores en ambos campos a la vez', () => {
		const result = characteristicSchema.safeParse({ title: 'T1', description: '<b>' });

		expect(result.success).toBe(false);
		expect(result.error?.issues.map((i) => i.path[0]).sort()).toEqual([
			'description',
			'title',
		]);
	});

	it('rechaza campos que no son texto', () => {
		const result = characteristicSchema.safeParse({ title: 123, description: null });

		expect(result.success).toBe(false);
		expect(result.error?.issues).toHaveLength(2);
	});
});
