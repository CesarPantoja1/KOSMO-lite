/**
 * Mock reutilizable de `next/navigation` (App Router).
 *
 * Se registra globalmente en `vitest.setup.ts`, por lo que cualquier componente
 * que use `useRouter`, `usePathname`, `useSearchParams` o `useParams` funciona
 * en jsdom sin configuración extra. Los tests pueden inspeccionar `mockRouter`
 * o cambiar la ruta con `setMockNavigation`.
 *
 * @example
 *   setMockNavigation({ pathname: '/proyecto', searchParams: { tab: 'ai' } });
 *   await user.click(boton);
 *   expect(mockRouter.push).toHaveBeenCalledWith('/perfil');
 */
import { vi } from 'vitest';

export const mockRouter = {
	push: vi.fn(),
	replace: vi.fn(),
	back: vi.fn(),
	forward: vi.fn(),
	refresh: vi.fn(),
	prefetch: vi.fn(),
};

type NavigationState = {
	pathname: string;
	searchParams: URLSearchParams;
	params: Record<string, string | string[]>;
};

const defaultState = (): NavigationState => ({
	pathname: '/',
	searchParams: new URLSearchParams(),
	params: {},
});

let state = defaultState();

export function setMockNavigation(options: {
	pathname?: string;
	searchParams?: Record<string, string> | URLSearchParams;
	params?: Record<string, string | string[]>;
}) {
	if (options.pathname !== undefined) state.pathname = options.pathname;
	if (options.searchParams !== undefined) {
		state.searchParams = new URLSearchParams(options.searchParams);
	}
	if (options.params !== undefined) state.params = options.params;
}

/** Restaura la ruta y limpia los spies del router. Se llama en `afterEach`. */
export function resetMockNavigation() {
	state = defaultState();
	Object.values(mockRouter).forEach((fn) => fn.mockReset());
}

export const nextNavigationMock = {
	useRouter: () => mockRouter,
	usePathname: () => state.pathname,
	useSearchParams: () => state.searchParams,
	useParams: () => state.params,
	useSelectedLayoutSegment: () => null,
	useSelectedLayoutSegments: () => [],
	redirect: vi.fn(),
	permanentRedirect: vi.fn(),
	notFound: vi.fn(),
};
