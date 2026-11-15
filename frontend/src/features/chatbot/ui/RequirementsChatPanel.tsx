'use client';

import { useRequirementsStore } from '@/entities/requirements';
import { createAssistantError } from '@/entities/chat';
import type { ChatMessage } from '@/entities/chat';
import { toast } from '@/shared/ui';
import { formatApiError } from '@/shared/api';
import { useCallback, useState } from 'react';
import { ChatPanel } from './ChatPanel';

interface RequirementsChatPanelProps {
	featureId: string | null;
	projectId?: string | null;
	onClose?: () => void;
	title?: string;
	placeholder?: string;
}

export const RequirementsChatPanel = ({
	featureId,
	projectId,
	onClose,
	title = 'Asistente de Requisitos EARS',
	placeholder = 'Ej., Agregar escenarios alternativos...',
}: RequirementsChatPanelProps) => {
	const chatHistories = useRequirementsStore((s) => s.chatHistories);
	const loadChatHistory = useRequirementsStore((s) => s.loadChatHistory);
	const loadOlderChatHistory = useRequirementsStore((s) => s.loadOlderChatHistory);
	const historyHasMore = useRequirementsStore((s) => s.historyHasMore);
	const appendUserMessage = useRequirementsStore((s) => s.appendUserMessage);
	const appendAssistantMessage = useRequirementsStore((s) => s.appendAssistantMessage);
	const getRequirements = useRequirementsStore((s) => s.getRequirements);
	const [loadingMore, setLoadingMore] = useState(false);

	const handleSend = (content: string) => {
		if (!featureId) return;
		appendUserMessage(featureId, content);
	};

	const handleMessage = async (message: ChatMessage) => {
		if (!featureId) return;
		appendAssistantMessage(featureId, message);
		if (message.modification?.applied && projectId && featureId) {
			await getRequirements(projectId, featureId);
		}
	};

	const handleRedirect = (redirectMessage: string) => {
		if (!featureId) return;
		appendAssistantMessage(featureId, createAssistantError(redirectMessage));
	};

	const handleLoadHistory = useCallback(
		(sessionId: string | null) => {
			if (!featureId) return;
			void loadChatHistory(featureId, sessionId);
		},
		[featureId, loadChatHistory],
	);

	const handleLoadMore = useCallback(
		async (sessionId: string | null) => {
			if (!featureId) return;
			setLoadingMore(true);
			try {
				await loadOlderChatHistory(featureId, sessionId);
			} catch (err) {
				toast.error(formatApiError(err, 'Error al cargar el historial.'));
			} finally {
				setLoadingMore(false);
			}
		},
		[featureId, loadOlderChatHistory],
	);

	const handleError = (error: unknown) => {
		const message = formatApiError(error, '');
		if (message.includes('inválido') || message.includes('format')) {
			toast.error(
				'El agente devolvió una respuesta con formato inválido. Por favor reformula tu mensaje.',
			);
		} else {
			toast.error(message || 'Error al enviar el mensaje al asistente de requisitos.');
		}
	};

	const messages = featureId ? (chatHistories[featureId] ?? []) : [];

	return (
		<ChatPanel
			key={featureId || 'empty'}
			title={title}
			greeting='Hola 👋. Soy tu asistente de Requisitos EARS. Puedo ayudarte a refinar los requisitos y generar sus criterios de aceptación (Dado-Cuando-Entonces).'
			placeholder={placeholder}
			onClose={onClose}
			messages={messages}
			streamUrl={
				featureId ? `/api/v1/features/${featureId}/requirements/chat/stream` : null
			}
			projectId={projectId ?? null}
			phase='requirements'
			contextId={featureId}
			onLoadHistory={handleLoadHistory}
			hasMore={historyHasMore}
			loadingMore={loadingMore}
			onLoadMore={handleLoadMore}
			onUserMessage={handleSend}
			onMessage={handleMessage}
			onRedirect={handleRedirect}
			onError={handleError}
		/>
	);
};
