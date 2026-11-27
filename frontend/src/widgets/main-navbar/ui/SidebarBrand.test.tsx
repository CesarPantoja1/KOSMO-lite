import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { mockRouter, renderWithProviders } from '@/test';
import { SidebarBrand } from './SidebarBrand';

function renderizar(isSidebarExpanded: boolean) {
	const onToggle = vi.fn();
	const utils = renderWithProviders(
		<SidebarBrand isSidebarExpanded={isSidebarExpanded} onToggle={onToggle} />,
	);
	return { ...utils, onToggle };
}

describe('SidebarBrand', () => {
	describe('barra expandida', () => {
		it('muestra la marca KOSMO que lleva al inicio', async () => {
			const { user } = renderizar(true);

			await user.click(screen.getByRole('button', { name: 'KOSMO' }));

			expect(mockRouter.push).toHaveBeenCalledWith('/');
		});

		it('permite contraer la barra lateral', async () => {
			const { user, onToggle } = renderizar(true);
			const [, alternar] = screen.getAllByRole('button');

			await user.click(alternar);

			expect(onToggle).toHaveBeenCalledOnce();
		});
	});

	describe('barra contraída', () => {
		it('oculta el texto de la marca y permite expandir', async () => {
			const { user, onToggle } = renderizar(false);

			expect(screen.queryByText('KOSMO')).not.toBeInTheDocument();
			await user.click(screen.getByRole('button'));

			expect(onToggle).toHaveBeenCalledOnce();
		});
	});
});
