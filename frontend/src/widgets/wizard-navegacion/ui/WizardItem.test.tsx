import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test';
import WizardItem from './WizardItem';

function renderizar(onClick?: (e: React.MouseEvent) => void) {
	return renderWithProviders(
		<WizardItem
			href='/proyecto/requisitos'
			icon={<svg aria-hidden='true' />}
			iconContainerStyles='border-wizard-active'
			label='Requisitos'
			subtitle='Fase 3'
			labelStyles='text-wizard-label-active'
			onClick={onClick}
		/>,
	);
}

describe('WizardItem', () => {
	it('es un enlace a la fase con su etiqueta y subtítulo', () => {
		renderizar();

		const enlace = screen.getByRole('link', { name: /Requisitos/ });
		expect(enlace).toHaveAttribute('href', '/proyecto/requisitos');
		expect(enlace).toHaveTextContent('Fase 3');
	});

	it('permite interceptar el clic (p. ej. para avisar de cambios sin guardar)', async () => {
		const onClick = vi.fn((e: React.MouseEvent) => e.preventDefault());
		const { user } = renderizar(onClick);

		await user.click(screen.getByRole('link'));

		expect(onClick).toHaveBeenCalledOnce();
	});
});
