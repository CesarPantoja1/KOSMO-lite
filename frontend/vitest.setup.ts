import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, vi } from 'vitest';
import { server } from './src/test/msw/server';
import { resetFactories } from './src/test/factories';
import { resetMockNavigation } from './src/test/mocks/next-navigation';

// --- APIs del navegador que jsdom no implementa ---
// scrollIntoView: el chat hace scroll automático al último mensaje.
if (!Element.prototype.scrollIntoView) {
	Element.prototype.scrollIntoView = function scrollIntoView() {};
}

// --- Zustand: reinicia todos los stores tras cada test (ver __mocks__/zustand.ts) ---
vi.mock('zustand');

// --- Next.js App Router: navegación simulada (ver src/test/mocks/next-navigation.ts) ---
vi.mock('next/navigation', async () => {
	const mod = await import('./src/test/mocks/next-navigation');
	return mod.nextNavigationMock;
});

// --- MSW: API simulada a nivel de red ---
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterAll(() => server.close());

afterEach(async () => {
	cleanup();
	// Restaura los vi.spyOn (p. ej. sobre toast o console) para que no acumulen llamadas.
	vi.restoreAllMocks();
	server.resetHandlers();
	resetMockNavigation();
	resetFactories();
	localStorage.clear();
	sessionStorage.clear();

	// La cola de toasts es global (react-aria): se vacía para no filtrar entre tests.
	try {
		const { queue } = await import('./src/shared/ui/toast/toast');
		queue.visibleToasts.forEach((t) => queue.close(t.key));
	} catch {
		/* módulo de toast mockeado por el test */
	}
});
