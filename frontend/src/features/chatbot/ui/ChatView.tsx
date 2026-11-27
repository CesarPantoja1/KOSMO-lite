'use client';

import { Ai, Close, Logo, Send } from '@/shared/ui';
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ChatMessageBubble } from './ChatMessageBubble';
import { ChatMessage } from '@/entities/chat';

interface Props {
	title?: string;
	greeting?: string;
	placeholder?: string;
	onClose?: () => void;
	messages?: ChatMessage[];
	onSendMessage?: (content: string) => void;
	isLoading?: boolean;
	streamingContent?: string | null;
	isStreaming?: boolean;
	onStop?: () => void;
	errorMessage?: string | null;
	onRetry?: () => void;
	sessionSelector?: ReactNode;
	hasMore?: boolean;
	loadingMore?: boolean;
	onLoadMore?: () => void;
}

/** Avatar del asistente + burbuja: saludo, indicador de escritura y texto en streaming. */
const AssistantBubble = ({
	children,
	className = '',
}: {
	children: ReactNode;
	className?: string;
}) => (
	<div className='flex items-start gap-2'>
		<div className='flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ai-500'>
			<Ai size={12} color='text-neutral-0' />
		</div>
		<div
			className={`max-w-[85%] rounded-2xl rounded-tl-sm border border-neutral-200 bg-neutral-0 px-2.5 py-1.5 shadow-sm md:px-3 md:py-2 ${className}`}
		>
			{children}
		</div>
	</div>
);

export const ChatView = ({
	title = 'Agente IA',
	greeting = 'Hola 👋. ¿En qué puedo ayudarte?',
	placeholder = 'Escribe un mensaje...',
	onClose,
	messages = [],
	onSendMessage,
	isLoading = false,
	streamingContent = null,
	isStreaming = false,
	onStop,
	errorMessage = null,
	onRetry,
	sessionSelector = null,
	hasMore = false,
	loadingMore = false,
	onLoadMore,
}: Props) => {
	const [input, setInput] = useState('');
	const messagesEndRef = useRef<HTMLDivElement>(null);

	const busy = isLoading || isStreaming;
	const canSend = input.trim().length > 0 && !busy;

	useEffect(() => {
		messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
	}, [messages, isLoading, isStreaming, streamingContent, errorMessage]);

	const handleSend = () => {
		const trimmed = input.trim();
		if (!trimmed || !onSendMessage || busy) return;
		setInput('');
		onSendMessage(trimmed);
	};

	const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			handleSend();
		}
	};

	// Ajusta la altura del textarea al contenido (también al vaciarse tras enviar)
	const textareaRef = useRef<HTMLTextAreaElement>(null);
	useEffect(() => {
		const textarea = textareaRef.current;
		if (!textarea) return;

		textarea.style.height = '0px';
		textarea.style.height = `${textarea.scrollHeight}px`;
	}, [input]);

	return (
		<div className='chatbot relative flex h-full w-full flex-col overflow-hidden bg-neutral-0 border-l border-neutral-200 md:w-lg xl:w-xl'>
			{/* Header */}
			<header className='flex items-center justify-between border-b border-ai-600 bg-ai-500 px-2 py-1.5 md:px-2.5 md:py-2'>
				{sessionSelector || (
					<div className='flex items-center gap-1.5'>
						<Logo size={14} className='text-neutral-0' />
						<h3 className='font-semibold text-neutral-0 text-xs md:text-sm'>{title}</h3>
					</div>
				)}
				<button
					type='button'
					onClick={onClose}
					className='rounded-md cursor-pointer p-0.5 text-neutral-0 hover:bg-ai-600 transition-colors'
					aria-label='Cerrar chat'
				>
					<Close color='' size={14} />
				</button>
			</header>

			{/* Estado del agente (solo lectores de pantalla) */}
			<span role='status' className='sr-only'>
				{isStreaming && streamingContent === null && 'Generando respuesta…'}
				{isStreaming && streamingContent !== null && 'Escribiendo respuesta…'}
				{!isStreaming && errorMessage && 'Ocurrió un error en el chat.'}
			</span>

			{/* Mensajes */}
			<div className='flex-1 overflow-y-auto space-y-3 px-2 py-2 md:px-3 md:py-3 bg-neutral-50'>
				{hasMore && (
					<div className='flex justify-center'>
						<button
							type='button'
							onClick={onLoadMore}
							disabled={loadingMore}
							className='rounded-md border border-neutral-300 bg-neutral-0 px-2 py-1 text-[10px] font-medium text-neutral-600 cursor-pointer transition-colors hover:bg-neutral-100 disabled:opacity-60 md:px-2.5 md:py-1 md:text-[11px]'
						>
							{loadingMore ? 'Cargando…' : 'Cargar mensajes anteriores'}
						</button>
					</div>
				)}

				{messages.length === 0 && !busy && (
					<AssistantBubble>
						<p className='text-xs leading-5 text-neutral-700 md:text-sm'>{greeting}</p>
					</AssistantBubble>
				)}

				{messages.map((message) => (
					<ChatMessageBubble key={message.id} message={message} />
				))}

				{(isLoading || (isStreaming && streamingContent === null)) && (
					<AssistantBubble>
						<span className='flex items-center gap-1 text-xs text-neutral-400 md:text-sm'>
							<span className='animate-bounce [animation-delay:0ms]'>·</span>
							<span className='animate-bounce [animation-delay:150ms]'>·</span>
							<span className='animate-bounce [animation-delay:300ms]'>·</span>
						</span>
					</AssistantBubble>
				)}

				{isStreaming && streamingContent !== null && (
					<AssistantBubble className='text-xs leading-5 text-neutral-700 wrap-break-word whitespace-pre-wrap md:text-sm'>
						{streamingContent}
						<span className='ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-ai-500 align-text-bottom' />
					</AssistantBubble>
				)}

				<div ref={messagesEndRef} />
			</div>

			{/* Error + retry */}
			{errorMessage && (
				<div
					role='alert'
					className='border-t border-error-100 bg-error-50 px-2.5 py-1.5 md:px-3 md:py-2'
				>
					<p className='text-[10px] leading-4 text-error-700 wrap-break-word md:text-xs md:leading-5'>
						{errorMessage}
					</p>
					{onRetry && (
						<button
							type='button'
							onClick={onRetry}
							className='mt-1.5 rounded-md border border-error-300 bg-neutral-0 px-2 py-0.5 text-[10px] font-medium text-error-700 cursor-pointer hover:bg-error-50 transition-colors md:px-2.5 md:py-1 md:text-[11px]'
						>
							Reintentar
						</button>
					)}
				</div>
			)}

			{/* Input */}
			<div className='border-t border-neutral-200 bg-neutral-0 p-1.5 md:p-2'>
				<div className='flex items-end gap-1.5 rounded-xl border border-neutral-300 bg-neutral-50 px-2 py-1 transition-colors focus-within:border-ai-500 focus-within:ring-2 focus-within:ring-ai-500/15 md:px-2.5 md:py-1.5'>
					<textarea
						value={input}
						onChange={(e) => setInput(e.target.value)}
						ref={textareaRef}
						onKeyDown={handleKeyDown}
						placeholder={placeholder}
						rows={1}
						disabled={busy}
						aria-label='Mensaje para el asistente'
						className='max-h-32 min-h-5 flex-1 resize-none bg-transparent py-0.5 text-xs md:text-sm leading-5 outline-none text-neutral-800 placeholder:text-neutral-400'
					/>
					{isStreaming ? (
						<button
							type='button'
							onClick={onStop}
							className='btn btn-ai rounded-full px-2 py-1 text-[10px] font-medium md:px-2.5 md:py-1.5 md:text-[11px]'
							aria-label='Detener generación'
						>
							Detener
						</button>
					) : (
						<button
							type='button'
							onClick={handleSend}
							disabled={!canSend}
							aria-label='Enviar mensaje'
							className='btn btn-ai rounded-full p-1 md:p-1.5'
						>
							<Send size={14} color='' />
						</button>
					)}
				</div>
				<p className='mt-1 px-0.5 text-[9px] text-neutral-400 md:text-[10px]'>
					Enter para enviar • Shift + Enter para nueva línea
				</p>
			</div>
		</div>
	);
};
