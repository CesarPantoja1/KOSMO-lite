import { describe, expect, it } from 'vitest';
import { renderWithProviders } from '@/test';
import { MarkdownEditorSkeleton } from './markdown-editor-skeleton';

describe('MarkdownEditorSkeleton', () => {
	it('reproduce la estructura del editor: índice lateral y área de contenido', () => {
		const { container } = renderWithProviders(<MarkdownEditorSkeleton />);

		expect(container.querySelector('aside nav')).toBeInTheDocument();
		expect(container.querySelector('section')).toBeInTheDocument();
	});

	it('usa placeholders animados en lugar de contenido real', () => {
		const { container } = renderWithProviders(<MarkdownEditorSkeleton />);

		expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(10);
		expect(container.textContent).toBe('');
	});

	it('mantiene la estructura visual estable entre renders (snapshot)', () => {
		const { container } = renderWithProviders(<MarkdownEditorSkeleton />);

		expect(container.firstChild).toMatchSnapshot();
	});
});
