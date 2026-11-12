import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { generateCodeChallenge, generateCodeVerifier } from './pkce';

/** Oráculo independiente: SHA-256 + base64url calculado con el módulo crypto de Node. */
const challengeEsperado = (verifier: string) =>
	createHash('sha256').update(verifier).digest('base64url');

describe('pkce', () => {
	describe('generateCodeVerifier', () => {
		it('genera un verifier de 56 caracteres hexadecimales', () => {
			const verifier = generateCodeVerifier();

			expect(verifier).toMatch(/^[0-9a-f]{56}$/);
		});

		it('cumple la longitud permitida por RFC 7636 (43 a 128 caracteres)', () => {
			const { length } = generateCodeVerifier();

			expect(length).toBeGreaterThanOrEqual(43);
			expect(length).toBeLessThanOrEqual(128);
		});

		it('genera un valor distinto en cada invocación', () => {
			const verifiers = new Set(Array.from({ length: 50 }, generateCodeVerifier));

			expect(verifiers.size).toBe(50);
		});
	});

	describe('generateCodeChallenge', () => {
		it.each([
			['verifier generado', generateCodeVerifier()],
			['cadena ASCII simple', 'kosmo-verifier-de-prueba'],
			['cadena con caracteres UTF-8', 'contraseña-ñandú-ü'],
		])('calcula el challenge S256 correcto para un %s', async (_caso, verifier) => {
			const challenge = await generateCodeChallenge(verifier);

			expect(challenge).toBe(challengeEsperado(verifier));
		});

		it('produce base64url sin padding ni caracteres "+", "/" o "="', async () => {
			// SHA-256 = 32 bytes → 43 caracteres base64url sin padding.
			const challenge = await generateCodeChallenge(generateCodeVerifier());

			expect(challenge).toMatch(/^[A-Za-z0-9_-]{43}$/);
		});

		it('es determinista: el mismo verifier produce el mismo challenge', async () => {
			const verifier = generateCodeVerifier();

			const [a, b] = await Promise.all([
				generateCodeChallenge(verifier),
				generateCodeChallenge(verifier),
			]);

			expect(a).toBe(b);
		});

		it('verifiers distintos producen challenges distintos', async () => {
			const a = await generateCodeChallenge('verifier-a');
			const b = await generateCodeChallenge('verifier-b');

			expect(a).not.toBe(b);
		});
	});
});
