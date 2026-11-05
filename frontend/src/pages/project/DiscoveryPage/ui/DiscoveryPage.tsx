'use client';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

import { formatApiError } from '@/shared/api';
import { Ai, ArrowRight, Loading, ModalConfirm, toast } from '@/shared/ui';

import type { ChatMessage } from '@/entities/chat';
import { createAssistantError } from '@/entities/chat';
import { useDiscoveryStore } from '@/entities/discovery';
import { useProjectStore } from '@/entities/project';

import { useAppStore, useUnsavedChanges } from '@/features/app-state';
import { ChatStreamPanel } from '@/features/chatbot';
import {
	MarkdownEditor,
	type MarkdownEditorHandle,
	type SaveStatus,
} from '@/features/markdown-editor';

const generatingDiscoveryMessages = [
	'Analizando información del proyecto...',
	'Identificando problemas y oportunidades...',
	'Generando documento de descubrimiento...',
];

const DiscoveryPage = () => {
	const editorRef = useRef<MarkdownEditorHandle>(null);
	const currentProject = useProjectStore((s) => s.currentProject);
	const [isGeneratingDiscovery, setIsGeneratingDiscovery] = useState(false);
	const router = useRouter();
	const isSavingRef = useRef(false);

	const pendingNavigationPath = useAppStore((s) => s.pendingNavigationPath);
	const setPendingNavigationPath = useAppStore((s) => s.setPendingNavigationPath);
	const setHasUnsavedChanges = useAppStore((s) => s.setHasUnsavedChanges);
	const isEditorMaximized = useAppStore((s) => s.isEditorMaximized);
	const setEditorMaximized = useAppStore((s) => s.setEditorMaximized);

	const [isChatbotOpen, setIsChatbotOpen] = useState(false);
	const [loadingMore, setLoadingMore] = useState(false);
	const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');

	const chatHistory = useDiscoveryStore((s) => s.chatHistory);
	const appendUserMessage = useDiscoveryStore((s) => s.appendUserMessage);
	const appendAssistantMessage = useDiscoveryStore((s) => s.appendAssistantMessage);
	const loadChatHistory = useDiscoveryStore((s) => s.loadChatHistory);
	const loadOlderChatHistory = useDiscoveryStore((s) => s.loadOlderChatHistory);
	const historyHasMore = useDiscoveryStore((s) => s.historyHasMore);
	const getDiscovery = useDiscoveryStore((s) => s.getDiscovery);
	const saveDiscovery = useDiscoveryStore((s) => s.saveDiscovery);
	const generateDiscovery = useDiscoveryStore((s) => s.generateDiscovery);
	const currentDiscovery = useDiscoveryStore((s) => s.currentDiscovery);
	const hasDiscovery = !!currentDiscovery?.content;
	const [markdown, setMarkdown] = useState(currentDiscovery?.content ?? '');
	const [savedContent, setSavedContent] = useState(currentDiscovery?.content ?? '');

	// Sync markdown with store after Zustand persist hydration.
	useEffect(() => {
		if (!currentDiscovery?.content || currentDiscovery.content === savedContent) return;
		const timer = window.setTimeout(() => {
			setMarkdown(currentDiscovery.content);
			setSavedContent(currentDiscovery.content);
		}, 0);
		return () => window.clearTimeout(timer);
	}, [currentDiscovery, savedContent]);

	const doSave = async (): Promise<boolean> => {
		if (!currentProject) return false;

		setSaveStatus('saving');

		try {
			isSavingRef.current = true;
			await saveDiscovery(currentProject.id, markdown);
			setSavedContent(markdown);
			setSaveStatus('saved');
			return true;
		} catch {
			setSaveStatus('error');
			return false;
		} finally {
			isSavingRef.current = false;
		}
	};

	useUnsavedChanges({
		isDirty: markdown !== savedContent,
		onAutosave: doSave,
	});

	const handleNextLink = async () => {
		const { hasUnsavedChanges, setPendingNavigationPath } = useAppStore.getState();
		if (hasUnsavedChanges) {
			setPendingNavigationPath('caracteristicas');
			return;
		}
		router.push('caracteristicas');
	};

	const handleGenerateDiscovery = async () => {
		if (!currentProject) return;

		setIsGeneratingDiscovery(true);
		try {
			const data = await generateDiscovery(currentProject.id);
			setMarkdown(data.content);
			setSavedContent(data.content);
		} catch (err) {
			toast.error(formatApiError(err, 'Error al generar el descubrimiento'));
		} finally {
			setIsGeneratingDiscovery(false);
		}
	};

	const confirmLeave = async () => {
		const path = pendingNavigationPath;
		setPendingNavigationPath(null);
		if (!path) return;
		if (path === 'caracteristicas') {
			const saved = await doSave();
			setHasUnsavedChanges(false);
			if (saved) {
				router.push('caracteristicas');
			}
		} else {
			setHasUnsavedChanges(false);
			router.push(path);
		}
	};

	const cancelLeave = () => {
		setPendingNavigationPath(null);
	};

	const handleSendChat = async (content: string) => {
		if (!currentProject) return;
		appendUserMessage(content);
	};

	const handleChatMessage = async (message: ChatMessage) => {
		appendAssistantMessage(message);
		if (message.modification?.applied && currentProject) {
			const updated = await getDiscovery(currentProject.id);
			setMarkdown(updated.content);
			setSavedContent(updated.content);
		}
	};

	const handleChatRedirect = (redirectMessage: string) => {
		appendAssistantMessage(createAssistantError(redirectMessage));
	};

	const handleLoadHistory = useCallback(
		(sessionId: string | null) => {
			if (!currentProject) return;
			void loadChatHistory(currentProject.id, sessionId);
		},
		[currentProject, loadChatHistory],
	);

	const handleLoadMore = useCallback(
		async (sessionId: string | null) => {
			if (!currentProject) return;
			setLoadingMore(true);
			try {
				await loadOlderChatHistory(currentProject.id, sessionId);
			} catch (err) {
				toast.error(formatApiError(err, 'Error al cargar el historial.'));
			} finally {
				setLoadingMore(false);
			}
		},
		[currentProject, loadOlderChatHistory],
	);

	return (
		<>
			{isGeneratingDiscovery && (
				<Loading
					title='Analizando tu proyecto'
					description='El asistente está procesando la información y generando el documento de descubrimiento.'
					messages={generatingDiscoveryMessages}
				/>
			)}

			{pendingNavigationPath && (
				<ModalConfirm onCancel={cancelLeave} onConfirm={confirmLeave} />
			)}

			<div className={`page-container ${isEditorMaximized ? 'px-8' : 'px-0'}`}>
				<div className='page-header'>
					<div className='flex items-start justify-between gap-4'>
						<div className='flex flex-col gap-1'>
							<h1 className='text-neutral-800 text-lg md:text-xl font-bold'>
								Descubrimiento del proyecto
							</h1>
							<p className='text-neutral-500 text-sm md:text-base'>
								Identifica y documenta el problema de negocio, el contexto y el alcance de
								tu proyecto.
							</p>
						</div>

						{!isEditorMaximized && hasDiscovery && (
							<div className='flex items-center gap-3 shrink-0'>
								<button
									onClick={() => setIsChatbotOpen(true)}
									className='btn btn-ai'
									title={
										!hasDiscovery ? 'Primero genera el documento de descubrimiento' : ''
									}
								>
									<Ai size={18} color='' />
									Mejorar con IA
								</button>
								<button onClick={handleNextLink} className='btn btn-primary'>
									Continuar
									<ArrowRight size={18} color='' />
								</button>
							</div>
						)}
					</div>

					<div className='flex-1 flex flex-col min-h-0'>
						{/* Empty state */}
						{!isGeneratingDiscovery && !hasDiscovery && (
							<div className='w-full my-auto min-h-105 flex flex-col items-center justify-center'>
								<div className='flex flex-col items-center gap-5 text-center px-6 max-w-lg'>
									<div className='flex h-20 w-20 items-center justify-center rounded-2xl bg-ai-50'>
										<Ai color='text-ai-500' size={48} />
									</div>
									<div className='flex flex-col gap-2'>
										<h3 className='text-xl font-semibold text-neutral-800'>
											Aún no hay análisis del problema
										</h3>
										<p className='text-neutral-500 text-base'>
											El asistente analizará tu proyecto y generará un documento que
											describe el problema de negocio, el contexto y los objetivos.
										</p>
									</div>
									<button onClick={handleGenerateDiscovery} className='btn btn-ai btn-lg'>
										<Ai size={18} color='' />
										Analizar mi proyecto
									</button>
								</div>
							</div>
						)}

						{/* Editor with content */}
						{hasDiscovery && (
							<div className='w-full h-full relative'>
								<MarkdownEditor
									ref={editorRef}
									markdown={markdown}
									onChange={setMarkdown}
									isMaximized={isEditorMaximized}
									onMaximize={() => setEditorMaximized(true)}
									onMinimize={() => setEditorMaximized(false)}
									saveStatus={saveStatus}
								/>
							</div>
						)}
					</div>
				</div>

				{/* Chatbot panel */}
				{isChatbotOpen && (
					<ChatStreamPanel
						placeholder='ej., ¿Qué alcance tiene el módulo de pagos?'
						onClose={() => setIsChatbotOpen(false)}
						messages={chatHistory}
						streamUrl={
							currentProject
								? `/api/v1/projects/${currentProject.id}/discovery/chat/stream`
								: null
						}
						projectId={currentProject?.id ?? null}
						phase='discovery'
						onLoadHistory={handleLoadHistory}
						hasMore={historyHasMore}
						loadingMore={loadingMore}
						onLoadMore={handleLoadMore}
						onUserMessage={handleSendChat}
						onMessage={handleChatMessage}
						onRedirect={handleChatRedirect}
						onError={(error) =>
							toast.error(formatApiError(error, 'Error al enviar el mensaje.'))
						}
					/>
				)}
			</div>
		</>
	);
};

export { DiscoveryPage };
