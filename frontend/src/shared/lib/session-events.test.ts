import { afterEach, describe, expect, it, vi } from 'vitest';
import { emitSessionExpired, onSessionExpired } from './session-events';

describe('session-events', () => {
	// El registro de listeners es global al módulo: cada test cancela sus suscripciones.
	const cancelaciones: Array<() => void> = [];
	const suscribir = (listener: () => void) => {
		const cancelar = onSessionExpired(listener);
		cancelaciones.push(cancelar);
		return cancelar;
	};

	afterEach(() => {
		cancelaciones.splice(0).forEach((cancelar) => cancelar());
	});

	it('notifica al listener suscrito cuando se emite el evento', () => {
		const listener = vi.fn();
		suscribir(listener);

		emitSessionExpired();

		expect(listener).toHaveBeenCalledOnce();
	});

	it('notifica a todos los listeners suscritos', () => {
		const a = vi.fn();
		const b = vi.fn();
		suscribir(a);
		suscribir(b);

		emitSessionExpired();

		expect(a).toHaveBeenCalledOnce();
		expect(b).toHaveBeenCalledOnce();
	});

	it('deja de notificar al listener tras cancelar la suscripción', () => {
		const listener = vi.fn();
		const cancelar = suscribir(listener);

		cancelar();
		emitSessionExpired();

		expect(listener).not.toHaveBeenCalled();
	});

	it('cancelar una suscripción no afecta a las demás', () => {
		const cancelado = vi.fn();
		const activo = vi.fn();
		const cancelar = suscribir(cancelado);
		suscribir(activo);

		cancelar();
		emitSessionExpired();

		expect(cancelado).not.toHaveBeenCalled();
		expect(activo).toHaveBeenCalledOnce();
	});

	it('registra una sola vez el mismo listener aunque se suscriba dos veces', () => {
		const listener = vi.fn();
		suscribir(listener);
		suscribir(listener);

		emitSessionExpired();

		expect(listener).toHaveBeenCalledOnce();
	});

	it('emitir sin listeners no lanza errores', () => {
		expect(() => emitSessionExpired()).not.toThrow();
	});
});
