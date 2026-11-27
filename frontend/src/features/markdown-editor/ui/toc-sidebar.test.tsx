import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test';
import type { HeadingItem } from '../model/heading';
import { TocSidebar } from './toc-sidebar';

const ENCABEZADOS: HeadingItem[] = [
	{ id: 'introduccion', text: 'Introducción', depth: 1 },
	{ id: 'alcance', text: 'Alcance', depth: 2 },
	{ id: 'fuera-de-alcance', text: 'Fuera de alcance', depth: 3 },
];

describe('TocSidebar', () => {
	it('lista los encabezados del documento', () => {
		renderWithProviders(<TocSidebar headings={ENCABEZADOS} />);

		expect(screen.getByRole('heading', { name: 'Contenido' })).toBeInTheDocument();
		ENCABEZADOS.forEach(({ text }) => {
			expect(screen.getByRole('button', { name: text })).toBeInTheDocument();
		});
	});

	it('indenta cada encabezado según su nivel', () => {
		renderWithProviders(<TocSidebar headings={ENCABEZADOS} />);

		expect(screen.getByRole('button', { name: 'Introducción' })).toHaveStyle({ paddingLeft: '8px' });
		expect(screen.getByRole('button', { name: 'Alcance' })).toHaveStyle({ paddingLeft: '16px' });
		expect(screen.getByRole('button', { name: 'Fuera de alcance' })).toHaveStyle({
			paddingLeft: '24px',
		});
	});

	it('resalta la sección activa', () => {
		renderWithProviders(<TocSidebar headings={ENCABEZADOS} activeId='alcance' />);

		expect(screen.getByRole('button', { name: 'Alcance' })).toHaveClass('font-medium');
		expect(screen.getByRole('button', { name: 'Introducción' })).not.toHaveClass('font-medium');
	});

	it('indica cuando el documento no tiene secciones', () => {
		renderWithProviders(<TocSidebar headings={[]} />);

		expect(screen.getByText('Sin secciones')).toBeInTheDocument();
	});

	it('al elegir un encabezado desplaza el documento hasta esa sección', async () => {
		const seccion = document.createElement('h2');
		seccion.id = 'alcance';
		seccion.scrollIntoView = vi.fn();
		document.body.appendChild(seccion);
		const { user } = renderWithProviders(<TocSidebar headings={ENCABEZADOS} />);

		await user.click(screen.getByRole('button', { name: 'Alcance' }));

		expect(seccion.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });
		seccion.remove();
	});

	it('ignora encabezados cuya sección no existe en el documento', async () => {
		const { user } = renderWithProviders(<TocSidebar headings={ENCABEZADOS} />);

		await expect(
			user.click(screen.getByRole('button', { name: 'Introducción' })),
		).resolves.not.toThrow();
	});

	it('se puede contraer y volver a expandir', async () => {
		const { user, container } = renderWithProviders(<TocSidebar headings={ENCABEZADOS} />);
		const aside = container.querySelector('aside')!;
		expect(aside).toHaveStyle({ width: '260px' });

		// El botón de contraer es el único sin texto (solo contiene un ícono).
		await user.click(screen.getAllByRole('button').find((b) => !b.textContent)!);
		expect(aside).toHaveStyle({ width: '44px' });
		expect(screen.queryByText('Introducción')).not.toBeInTheDocument();

		await user.click(screen.getByRole('button'));
		expect(aside).toHaveStyle({ width: '260px' });
		expect(screen.getByText('Introducción')).toBeInTheDocument();
	});
});
