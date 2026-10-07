import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SseStartOptions } from '@/shared/lib/useSseStream';

vi.mock('@/shared/lib/useSseStream', () => ({
	useSseStream: vi.fn(),
}));

import { useSseStream } from '@/shared/lib/useSseStream';
import { useChatStream } from './useChatStream';

const startMock = vi.fn();
const stopMock = vi.fn();

vi.mocked(useSseStream).mockReturnValue({
	phase: 'idle',
	error: null,
	start: startMock,
	stop: stopMock,
});

describe('useChatStream', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		startMock.mockResolvedValue(undefined);
	});

	it('invoca start con la url y el body dados', () => {
		// Arrange
		const { result } = renderHook(() => useChatStream());

		// Act
		act(() => {
			result.current.send('/api/v1/chat', { content: 'Hola' });
		});

		// Assert
		expect(startMock).toHaveBeenCalledWith(
			expect.objectContaining({ url: '/api/v1/chat', body: { content: 'Hola' } }),
		);
	});

	it('propaga eventos "chunk" a onChunk', () => {
		// Arrange
		const onChunk = vi.fn();
		let capturedOnEvent: SseStartOptions['onEvent'] = () => {};
		startMock.mockImplementation((opts: SseStartOptions) => {
			capturedOnEvent = opts.onEvent;
			return Promise.resolve();
		});
		const { result } = renderHook(() => useChatStream({ onChunk }));

		// Act
		act(() => {
			result.current.send('/url', { content: 'x' });
		});
		act(() => {
			capturedOnEvent({ type: 'chunk', content: 'Hola ' });
		});

		// Assert
		expect(onChunk).toHaveBeenCalledWith('Hola ');
	});

	it('transforma un evento "message" a ChatMessage y lo pasa a onMessage', () => {
		// Arrange
		const onMessage = vi.fn();
		let capturedOnEvent: SseStartOptions['onEvent'] = () => {};
		startMock.mockImplementation((opts: SseStartOptions) => {
			capturedOnEvent = opts.onEvent;
			return Promise.resolve();
		});
		const { result } = renderHook(() => useChatStream({ onMessage }));

		// Act
		act(() => {
			result.current.send('/url', { content: 'x' });
		});
		act(() => {
			capturedOnEvent({
				type: 'message',
				id: 'm1',
				content: 'Respuesta completa',
				timestamp: '2026-01-01T00:00:00Z',
				suggestions: [
					{
						id: 's1',
						section: 'Sección',
						description: 'desc',
						diff_before: 'antes',
						diff_after: 'después',
						rationale: 'porque sí',
						applied: true,
						not_applied_reason: null,
					},
				],
				modification: {
					applied: true,
					modified_section: 'Sección',
					change_description: 'cambio',
				},
			});
		});

		// Assert
		expect(onMessage).toHaveBeenCalledWith(
			expect.objectContaining({
				id: 'm1',
				role: 'assistant',
				content: 'Respuesta completa',
				created_at: '2026-01-01T00:00:00Z',
			}),
		);
		const message = onMessage.mock.calls[0][0];
		expect(message.change_suggestions).toHaveLength(1);
		expect(message.change_suggestions[0].section).toBe('Sección');
		expect(message.modification?.applied).toBe(true);
	});

	it('usa valores por defecto cuando el evento "message" no trae sugerencias ni modificación', () => {
		// Arrange
		const onMessage = vi.fn();
		let capturedOnEvent: SseStartOptions['onEvent'] = () => {};
		startMock.mockImplementation((opts: SseStartOptions) => {
			capturedOnEvent = opts.onEvent;
			return Promise.resolve();
		});
		const { result } = renderHook(() => useChatStream({ onMessage }));

		// Act
		act(() => {
			result.current.send('/url', { content: 'x' });
		});
		act(() => {
			capturedOnEvent({ type: 'message', content: 'simple' });
		});

		// Assert
		const message = onMessage.mock.calls[0][0];
		expect(message.change_suggestions).toEqual([]);
		expect(message.modification).toBeNull();
	});

	it('propaga eventos "error" a onError con un mensaje por defecto', () => {
		// Arrange
		const onError = vi.fn();
		let capturedOnEvent: SseStartOptions['onEvent'] = () => {};
		startMock.mockImplementation((opts: SseStartOptions) => {
			capturedOnEvent = opts.onEvent;
			return Promise.resolve();
		});
		const { result } = renderHook(() => useChatStream({ onError }));

		// Act
		act(() => {
			result.current.send('/url', { content: 'x' });
		});
		act(() => {
			capturedOnEvent({ type: 'error' });
		});

		// Assert
		expect(onError).toHaveBeenCalledWith(expect.any(Error));
		expect(onError.mock.calls[0][0].message).toBe('Error al procesar el mensaje.');
	});

	it('ignora silenciosamente si start() rechaza la promesa', async () => {
		// Arrange
		startMock.mockRejectedValue(new Error('fallo de red'));
		const { result } = renderHook(() => useChatStream());

		// Act & Assert (no debe lanzar sin capturar)
		await act(async () => {
			result.current.send('/url', { content: 'x' });
			await Promise.resolve();
		});

		expect(startMock).toHaveBeenCalled();
	});

	it('expone stop del stream subyacente', () => {
		// Arrange
		const { result } = renderHook(() => useChatStream());

		// Act
		result.current.stop();

		// Assert
		expect(stopMock).toHaveBeenCalled();
	});
});
