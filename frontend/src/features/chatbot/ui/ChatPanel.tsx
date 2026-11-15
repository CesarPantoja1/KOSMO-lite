'use client';

import { useEffect, useRef, useState } from 'react';
import type { ChatMessage, ChatPhase } from '@/entities/chat';
import { useChatSessions, useChatSessionsStore } from '@/entities/chat';
import { ApiError, formatApiError } from '@/shared/api';
import { useChatStream } from '../model/useChatStream';
import { ChatView } from './ChatView';
import { SessionSelector } from './SessionSelector';

interface ChatPanelProps {
	title?: string;
	greeting?: string;
	placeholder?: string;
	onClose?: () => void;
	messages: ChatMessage[];
	streamUrl: string | null;
	projectId?: string | null;
	phase?: ChatPhase | null;
	contextId?: string | null;
	onLoadHistory?: (sessionId: string | null) => Promise<void> | void;
	hasMore?: boolean;
	loadingMore?: boolean;
	onLoadMore?: (sessionId: string | null) => void;
	onUserMessage: (content: string) => void;
	onMessage: (message: ChatMessage) => void;
	onRedirect?: (message: string) => void;
	onError?: (error: unknown) => void;
}

export const ChatPanel = ({
	title,
	greeting,
	placeholder,
	onClose,
	messages,
	streamUrl,
	projectId = null,
	phase = null,
	contextId = null,
	onLoadHistory,
	hasMore = false,
	loadingMore = false,
	onLoadMore,
	onUserMessage,
	onMessage,
	onRedirect,
	onError,
}: ChatPanelProps) => {
	const [streamingContent, setStreamingContent] = useState<string | null>(null);
	const [errorMessage, setErrorMessage] = useState<string | null>(null);
	const lastContentRef = useRef<string | null>(null);

	// Un stream en curso o el efecto de historial deben llamar siempre a la versión
	// más reciente de los callbacks del padre, sin reiniciarse cuando cambian.
	const latest = useRef({ onMessage, onRedirect, onError, onLoadHistory });
	useEffect(() => {
		latest.current = { onMessage, onRedirect, onError, onLoadHistory };
	});

	const {
		phase: streamPhase,
		send,
		stop,
	} = useChatStream({
		onChunk: (content) => setStreamingContent((prev) => (prev ?? '') + content),
		onMessage: (message) => {
			setStreamingContent(null);
			latest.current.onMessage(message);
			// Re-lista las sesiones para refrescar el título derivado del primer prompt
			if (projectId && phase) {
				void useChatSessionsStore
					.getState()
					.listSessions(projectId, phase, contextId)
					.catch(() => undefined);
			}
		},
		onError: (err) => {
			setStreamingContent(null);
			const text = formatApiError(err, 'Error al enviar el mensaje.');
			// El endpoint de stream devuelve 400 cuando el cambio pertenece a otra fase
			if (err instanceof ApiError && err.status === 400) {
				latest.current.onRedirect?.(err.detail ?? text);
			} else {
				setErrorMessage(text);
				latest.current.onError?.(err);
			}
		},
	});

	const chatSessions = useChatSessions(projectId, phase, contextId);

	// Rehidrata el historial al cambiar de sesión o de contexto
	useEffect(() => {
		if (!projectId || !phase) return;
		const timer = window.setTimeout(() => {
			void latest.current.onLoadHistory?.(chatSessions.activeSessionId);
		}, 0);
		return () => window.clearTimeout(timer);
	}, [projectId, phase, contextId, chatSessions.activeSessionId]);

	const startStream = (url: string, content: string) => {
		setErrorMessage(null);
		setStreamingContent('');
		send(url, { content, session_id: chatSessions.activeSessionId });
	};

	const handleSend = (content: string) => {
		if (!streamUrl) return;
		lastContentRef.current = content;
		onUserMessage(content);
		startStream(streamUrl, content);
	};

	const handleRetry = () => {
		const last = lastContentRef.current;
		if (!last || !streamUrl) return;
		startStream(streamUrl, last);
	};

	const isStreaming = streamPhase === 'connecting' || streamPhase === 'streaming';

	const handleCreateSession = () => {
		void chatSessions.createNewSession().catch((err) => {
			setErrorMessage(formatApiError(err, 'No se pudo crear el chat.'));
		});
	};

	const handleDeleteSession = (sessionId: string) => {
		void chatSessions.deleteSession(sessionId).catch((err) => {
			setErrorMessage(formatApiError(err, 'No se pudo eliminar el chat.'));
		});
	};

	return (
		<ChatView
			title={title}
			greeting={greeting}
			placeholder={placeholder}
			onClose={onClose}
			messages={messages}
			onSendMessage={handleSend}
			isLoading={chatSessions.loading}
			streamingContent={streamingContent}
			isStreaming={isStreaming}
			onStop={stop}
			errorMessage={errorMessage}
			onRetry={handleRetry}
			hasMore={hasMore}
			loadingMore={loadingMore}
			onLoadMore={() => onLoadMore?.(chatSessions.activeSessionId)}
			sessionSelector={
				projectId && phase ? (
					<SessionSelector
						title={title}
						sessions={chatSessions.sessions}
						activeSessionId={chatSessions.activeSessionId}
						loading={chatSessions.loading}
						onSelect={chatSessions.selectSession}
						onCreate={handleCreateSession}
						onDelete={handleDeleteSession}
					/>
				) : null
			}
		/>
	);
};
