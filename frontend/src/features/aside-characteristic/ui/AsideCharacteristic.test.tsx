import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import Requirements from '@/shared/ui/icons/Requirements';
import { crearCaracteristica, renderWithProviders } from '@/test';
import AsideCharacteristic from './AsideCharacteristic';

const LISTA = [
	crearCaracteristica({ id: 'feat_1', display_id: 'F-001', title: 'Inicio de sesión' }),
	crearCaracteristica({ id: 'feat_2', display_id: 'F-002', title: 'Pagos' }),
];

type Props = Parameters<typeof AsideCharacteristic>[0];

function renderizar(props: Partial<Props> = {}) {
	const onSelectCharacteristic = vi.fn();
	const utils = renderWithProviders(
		<AsideCharacteristic
			characteristics={LISTA}
			selectedId='feat_1'
			onSelectCharacteristic={onSelectCharacteristic}
			hasIcon={{}}
			icon={Requirements}
			{...props}
		/>,
	);
	return { ...utils, onSelectCharacteristic };
}

describe('AsideCharacteristic', () => {
	it('lista las funcionalidades con su identificador y resalta la seleccionada', () => {
		renderizar();

		expect(screen.getByRole('heading', { name: 'Funcionalidades' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /F-001.*Inicio de sesión/ })).toHaveClass(
			'bg-neutral-200/75',
		);
		expect(screen.getByRole('button', { name: /F-002.*Pagos/ })).not.toHaveClass(
			'bg-neutral-200/75',
		);
	});

	it('acepta un título personalizado', () => {
		renderizar({ title: 'Criterios' });

		expect(screen.getByRole('heading', { name: 'Criterios' })).toBeInTheDocument();
	});

	it('indica cuando no hay funcionalidades', () => {
		renderizar({ characteristics: [] });

		expect(screen.getByText('No hay funcionalidades disponibles.')).toBeInTheDocument();
	});

	it('notifica la funcionalidad elegida', async () => {
		const { user, onSelectCharacteristic } = renderizar();

		await user.click(screen.getByRole('button', { name: /Pagos/ }));

		expect(onSelectCharacteristic).toHaveBeenCalledWith('feat_2');
	});

	it('marca con advertencia las funcionalidades que requieren actualización', () => {
		renderizar({ hasIcon: { feat_2: true }, warningByFeature: { feat_2: true } });

		expect(
			screen.getByTitle('Requiere actualización por cambios en especificaciones'),
		).toBeInTheDocument();
	});

	it('elimina una funcionalidad sin seleccionarla', async () => {
		const onDeleteCharacteristic = vi.fn();
		const { user, onSelectCharacteristic } = renderizar({
			hasIcon: { feat_2: true },
			onDeleteCharacteristic,
		});

		await user.click(screen.getByTitle('Eliminar'));

		expect(onDeleteCharacteristic).toHaveBeenCalledWith('feat_2');
		expect(onSelectCharacteristic).not.toHaveBeenCalled();
	});

	describe('contraída', () => {
		it('muestra solo los identificadores, con el título como tooltip', () => {
			renderizar({ defaultExpanded: false });

			expect(
				screen.queryByRole('heading', { name: 'Funcionalidades' }),
			).not.toBeInTheDocument();
			expect(screen.getByTitle('Inicio de sesión')).toHaveTextContent('F-001');
		});

		it('se expande y contrae internamente', async () => {
			const { user, container } = renderizar();
			const aside = container.querySelector('aside')!;

			await user.click(screen.getAllByRole('button')[0]);
			expect(aside).toHaveStyle({ width: '52px' });

			await user.click(screen.getAllByRole('button')[0]);
			expect(aside).toHaveStyle({ width: '288px' });
		});

		it('en modo controlado delega el cambio al padre', async () => {
			const onToggleExpand = vi.fn();
			const { user } = renderizar({ isExpanded: true, onToggleExpand });

			await user.click(screen.getAllByRole('button')[0]);

			expect(onToggleExpand).toHaveBeenCalledWith(false);
			expect(
				screen.getByRole('heading', { name: 'Funcionalidades' }),
			).toBeInTheDocument();
		});
	});
});
