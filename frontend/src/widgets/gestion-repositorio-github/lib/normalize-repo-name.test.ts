import { describe, expect, it } from 'vitest';
import { normalizeRepoName } from './normalize-repo-name';

describe('normalizeRepoName', () => {
	it('convierte a minúsculas y reemplaza espacios por guiones', () => {
		expect(normalizeRepoName('Mi Proyecto')).toBe('mi-proyecto');
	});

	it('elimina caracteres inválidos', () => {
		expect(normalizeRepoName('Repo //Backend!')).toBe('repo-backend');
	});

	it('colapsa guiones consecutivos', () => {
		expect(normalizeRepoName('a--b   c')).toBe('a-b-c');
	});

	it('recorta guiones al inicio y al final', () => {
		expect(normalizeRepoName('--repo-')).toBe('repo');
	});

	it('limita la longitud a 100 caracteres', () => {
		const input = 'a'.repeat(120);
		expect(normalizeRepoName(input)).toHaveLength(100);
	});
});
