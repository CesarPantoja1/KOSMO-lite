import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ModificationResult } from '@/shared/model/chat-message';
import { crearCambioSugerido, crearMensaje, renderWithProviders } from '@/test';
import { ChatbotMessage } from './chatbot-message';

const modificacion = (overrides: Partial<ModificationResult> = {}): ModificationResult => ({
	applied: false,
	modified_section: null,
	change_description: null,
	modified_document: null,
	before: null,
	after: null,
	undo_version_id: null,
	clarification_message: null,
	...overrides,
});

describe('ChatbotMessage', () => {
	it('muestra el mensaje del usuario como texto literal, alineado a la derecha', () => {
		const { container } = renderWithProviders(
			<ChatbotMessage message={crearMensaje({ role: 'user', content: '**sin formato**' })} />,
		);

		expect(screen.getByText('**sin formato**')).toBeInTheDocument();
		expect(container.firstElementChild).toHaveClass('items-end');
	});

	it('renderiza la respuesta del asistente como markdown, alineada a la izquierda', () => {
		const { container } = renderWithProviders(
			<ChatbotMessage message={crearMensaje({ role: 'assistant', content: 'Usa **PKCE**' })} />,
		);

		expect(screen.getByText('PKCE').tagName).toBe('STRONG');
		expect(container.firstElementChild).toHaveClass('items-start');
	});

	it('muestra la pregunta de aclaración cuando la IA no pudo aplicar el cambio', () => {
		renderWithProviders(
			<ChatbotMessage
				message={crearMensaje({
					modification: modificacion({
						applied: false,
						clarification_message: '¿A qué sección te refieres?',
					}),
				})}
			/>,
		);

		expect(screen.getByText('¿A qué sección te refieres?')).toBeInTheDocument();
	});

	it('no muestra la aclaración si el cambio se aplicó', () => {
		renderWithProviders(
			<ChatbotMessage
				message={crearMensaje({
					modification: modificacion({ applied: true, clarification_message: 'Texto oculto' }),
				})}
			/>,
		);

		expect(screen.queryByText('Texto oculto')).not.toBeInTheDocument();
	});

	it('muestra una tarjeta por cada cambio sugerido', () => {
		renderWithProviders(
			<ChatbotMessage
				message={crearMensaje({
					change_suggestions: [
						crearCambioSugerido({ description: 'Cambio A' }),
						crearCambioSugerido({ description: 'Cambio B' }),
					],
				})}
			/>,
		);

		expect(screen.getByRole('heading', { name: 'Cambio A' })).toBeInTheDocument();
		expect(screen.getByRole('heading', { name: 'Cambio B' })).toBeInTheDocument();
	});

	it('no muestra tarjetas con una lista de cambios vacía', () => {
		renderWithProviders(<ChatbotMessage message={crearMensaje({ change_suggestions: [] })} />);

		expect(screen.queryByRole('heading')).not.toBeInTheDocument();
	});
});
