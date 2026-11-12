import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test';
import { FormularioCreacionRepositorio } from './FormularioCreacionRepositorio';

function renderizar(
	props: Partial<Parameters<typeof FormularioCreacionRepositorio>[0]> = {},
) {
	const onSubmit = vi.fn();
	const utils = renderWithProviders(
		<FormularioCreacionRepositorio
			suggestedRepoName='kosmo-tienda'
			onSubmit={onSubmit}
			{...props}
		/>,
	);
	const campo = screen.getByLabelText('Nombre del repositorio');
	return { ...utils, onSubmit, campo };
}

const botonCrear = () => screen.getByRole('button', { name: /Crear repositorio/ });

describe('FormularioCreacionRepositorio', () => {
	describe('valores iniciales', () => {
		it('propone el nombre sugerido y visibilidad privada', () => {
			const { campo } = renderizar();

			expect(campo).toHaveValue('kosmo-tienda');
			expect(screen.getByRole('button', { name: /Privado/ })).toHaveClass(
				'border-primary-500',
			);
		});

		it('usa "kosmo-repositorio" si no hay sugerencia', () => {
			const { campo } = renderizar({ suggestedRepoName: null });

			expect(campo).toHaveValue('kosmo-repositorio');
			expect(screen.getByText('kosmo-{slug}')).toBeInTheDocument();
		});
	});

	describe('normalización del nombre', () => {
		it.each([
			['Mi Repo Nuevo', 'mi-repo-nuevo'],
			['Repo@#Ñandú!', 'repoand'],
			['  --inicio y fin--  ', 'inicio-y-fin'],
			['v1.2_beta', 'v1.2_beta'],
		])('al pegar "%s" lo convierte en "%s"', async (entrada, esperado) => {
			const { user, campo } = renderizar();

			await user.clear(campo);
			await user.click(campo);
			await user.paste(entrada);

			expect(campo).toHaveValue(esperado);
		});
	});

	describe('validación', () => {
		it('exige un nombre de repositorio', async () => {
			const { user, campo, onSubmit } = renderizar();

			await user.clear(campo);
			await user.click(botonCrear());

			expect(await screen.findByRole('alert')).toHaveTextContent(
				'Ingresa el nombre del repositorio',
			);
			expect(onSubmit).not.toHaveBeenCalled();
		});
	});

	describe('repositorio privado', () => {
		it('se crea directamente sin pedir confirmación', async () => {
			const { user, onSubmit } = renderizar();

			await user.click(botonCrear());

			expect(onSubmit).toHaveBeenCalledWith({
				repo_name: 'kosmo-tienda',
				is_public: false,
			});
			expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
		});
	});

	describe('repositorio público', () => {
		async function elegirPublicoYEnviar() {
			const utils = renderizar();
			await utils.user.click(screen.getByRole('button', { name: /Público/ }));
			await utils.user.click(botonCrear());
			return utils;
		}

		it('pide confirmación antes de crearlo', async () => {
			const { onSubmit } = await elegirPublicoYEnviar();

			const dialogo = screen.getByRole('dialog', { name: 'Crear repositorio público' });
			expect(within(dialogo).getByText('kosmo-tienda')).toBeInTheDocument();
			expect(onSubmit).not.toHaveBeenCalled();
		});

		it('al confirmar crea el repositorio público', async () => {
			const { user, onSubmit } = await elegirPublicoYEnviar();

			await user.click(
				within(screen.getByRole('dialog')).getByRole('button', {
					name: 'Crear repositorio público',
				}),
			);

			expect(onSubmit).toHaveBeenCalledWith({
				repo_name: 'kosmo-tienda',
				is_public: true,
			});
			expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
		});
	});

	it('mientras se crea bloquea el envío y muestra el progreso', async () => {
		const { user, onSubmit } = renderizar({ submitting: true });

		const boton = screen.getByRole('button', { name: /Creando repositorio/ });
		await user.click(boton);

		expect(boton).toBeDisabled();
		expect(onSubmit).not.toHaveBeenCalled();
	});
});
