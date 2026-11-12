/**
 * Render personalizado: monta el componente con los providers globales de la app
 * y devuelve una instancia de `userEvent` lista para simular interacciones.
 *
 * @example
 *   const { user } = renderWithProviders(<ModalConfirm ... />);
 *   await user.click(screen.getByRole('button', { name: /confirmar/i }));
 */
import { render, type RenderOptions } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement, ReactNode } from 'react';
import { ToasterProvider } from '@/shared/ui/toast/ToasterProvider';
import { setMockNavigation } from './mocks/next-navigation';

type ProviderOptions = Omit<RenderOptions, 'wrapper'> & {
	/** Ruta simulada para `usePathname` / `useSearchParams` / `useParams`. */
	route?: Parameters<typeof setMockNavigation>[0];
	/**
	 * Opciones de `userEvent.setup()`. Con temporizadores simulados usar
	 * `{ advanceTimers: vi.advanceTimersByTime }` para que las interacciones no se bloqueen.
	 */
	userEventOptions?: Parameters<typeof userEvent.setup>[0];
};

function AppProviders({ children }: { children: ReactNode }) {
	return (
		<>
			{children}
			<ToasterProvider />
		</>
	);
}

export function renderWithProviders(ui: ReactElement, options: ProviderOptions = {}) {
	const { route, userEventOptions, ...renderOptions } = options;
	if (route) setMockNavigation(route);

	const user = userEvent.setup(userEventOptions);
	return {
		user,
		...render(ui, { wrapper: AppProviders, ...renderOptions }),
	};
}
