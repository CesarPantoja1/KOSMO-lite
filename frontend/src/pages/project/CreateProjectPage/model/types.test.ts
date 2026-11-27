import { describe, expect, it } from 'vitest';
import { crearProyecto } from '@/test';
import { createProjectSchema, type ProjectFormData } from './types';

const DESCRIPCION_VALIDA =
	'Plataforma para gestionar requisitos de software con asistencia de IA en cada fase.';

const datosValidos = (overrides: Partial<ProjectFormData> = {}): ProjectFormData => ({
	name: 'Mi Proyecto',
	description: DESCRIPCION_VALIDA,
	repo_name: 'mi-proyecto',
	is_public: false,
	...overrides,
});

/** Mensajes de error de Zod para un campo concreto. */
const erroresDe = (data: unknown, campo: keyof ProjectFormData, existentes = []) => {
	const result = createProjectSchema(existentes).safeParse(data);
	if (result.success) return [];
	return result.error.issues.filter((i) => i.path[0] === campo).map((i) => i.message);
};

describe('createProjectSchema', () => {
	it('acepta un proyecto con todos los campos válidos', () => {
		const result = createProjectSchema([]).safeParse(datosValidos());

		expect(result.success).toBe(true);
	});

	describe('campo name', () => {
		it.each([
			['3 caracteres (mínimo)', 'Abc'],
			['25 caracteres (máximo)', 'A'.repeat(25)],
			['letras con espacios', 'Gestor De Tareas'],
		])('acepta %s', (_caso, name) => {
			expect(erroresDe(datosValidos({ name }), 'name')).toEqual([]);
		});

		it.each([
			['vacío', '', 'Mínimo 3 caracteres'],
			['de 2 caracteres', 'Ab', 'Mínimo 3 caracteres'],
			['de 26 caracteres', 'A'.repeat(26), 'Máximo 25 caracteres'],
			['con números', 'Proyecto 2', 'No se permiten caracteres especiales'],
			['con guiones', 'mi-proyecto', 'No se permiten caracteres especiales'],
			['con símbolos', 'Proyecto!', 'No se permiten caracteres especiales'],
			['con tildes', 'Gestión', 'No se permiten caracteres especiales'],
			['con emojis', 'Proyecto 🚀', 'No se permiten emojis'],
		])('rechaza un nombre %s', (_caso, name, mensaje) => {
			expect(erroresDe(datosValidos({ name }), 'name')).toContain(mensaje);
		});
	});

	describe('campo description', () => {
		it.each([
			['de 50 caracteres (mínimo)', 'a'.repeat(50)],
			['de 1000 caracteres (máximo)', 'a'.repeat(1000)],
			['con números y signos de puntuación', `${DESCRIPCION_VALIDA} Versión 2.0, ¡lista!`],
		])('acepta una descripción %s', (_caso, description) => {
			expect(erroresDe(datosValidos({ description }), 'description')).toEqual([]);
		});

		it.each([
			['vacía', '', 'Mínimo 50 caracteres'],
			['de 49 caracteres', 'a'.repeat(49), 'Mínimo 50 caracteres'],
			['de 1001 caracteres', 'a'.repeat(1001), 'Máximo 1000 caracteres'],
			['con emojis', `${DESCRIPCION_VALIDA} ✨`, 'No se permiten emojis'],
		])('rechaza una descripción %s', (_caso, description, mensaje) => {
			expect(erroresDe(datosValidos({ description }), 'description')).toContain(mensaje);
		});
	});

	describe('campos repo_name e is_public', () => {
		it('exige que is_public sea booleano', () => {
			const errores = erroresDe({ ...datosValidos(), is_public: 'si' }, 'is_public');

			expect(errores).toHaveLength(1);
		});

		it('exige repo_name como texto', () => {
			const errores = erroresDe({ ...datosValidos(), repo_name: undefined }, 'repo_name');

			expect(errores).toHaveLength(1);
		});
	});

	describe('nombre duplicado', () => {
		const existentes = [crearProyecto({ name: 'Mi Proyecto' })];

		it.each([
			['idéntico', 'Mi Proyecto'],
			['con distinta capitalización', 'MI PROYECTO'],
			['con espacios alrededor', '  mi proyecto  '],
		])('rechaza un nombre %s a uno existente', (_caso, name) => {
			const result = createProjectSchema(existentes).safeParse(datosValidos({ name }));

			expect(result.success).toBe(false);
			expect(result.error?.issues).toContainEqual(
				expect.objectContaining({
					path: ['name'],
					message: 'Ya existe un proyecto con ese nombre',
				}),
			);
		});

		it('acepta un nombre distinto a los existentes', () => {
			const result = createProjectSchema(existentes).safeParse(
				datosValidos({ name: 'Otro Proyecto' }),
			);

			expect(result.success).toBe(true);
		});

		it('sin proyectos existentes no hay conflicto de nombre', () => {
			expect(createProjectSchema([]).safeParse(datosValidos()).success).toBe(true);
		});
	});
});
