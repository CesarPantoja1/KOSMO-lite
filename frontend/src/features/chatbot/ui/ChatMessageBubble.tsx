'use client';

import { Ai } from '@/shared/ui';
import { MarkdownText } from '@/shared/ui/markdown-text';
import { TarjetaRecepcionPlan } from './TarjetaRecepcionPlan';
import { ChatMessage } from '@/entities/chat';

interface ChatMessageBubbleProps {
	message: ChatMessage;
}

export const ChatMessageBubble = ({ message }: ChatMessageBubbleProps) => {
	const isUser = message.role === 'user';

	return (
		<div className={`flex flex-col gap-1.5 ${isUser ? 'items-end' : 'items-start'}`}>
			<div
				className={`flex items-start gap-2 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
			>
				{!isUser && (
					<div className='flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ai-500'>
						<Ai size={12} color='text-neutral-0' />
					</div>
				)}
				<div
					className={`
						max-w-[85%] px-2.5 py-1.5 text-xs leading-5 wrap-break-word whitespace-pre-wrap
						md:px-3 md:py-2 md:text-sm
						${
							isUser
								? 'rounded-2xl rounded-br-sm bg-ai-500 text-neutral-0'
								: 'rounded-2xl rounded-tl-sm bg-neutral-0 border border-neutral-200 text-neutral-700 shadow-sm'
						}
					`}
				>
					{isUser ? message.content : <MarkdownText content={message.content} />}
				</div>
			</div>

			{message.modification &&
				!message.modification.applied &&
				message.modification.clarification_message && (
					<div className='w-full rounded-lg border border-ai-200 bg-ai-50 px-2.5 py-1.5 md:px-3 md:py-2'>
						<p className='text-xs leading-5 text-ai-700 md:text-sm md:leading-6'>
							{message.modification.clarification_message}
						</p>
					</div>
				)}

			{message.change_suggestions &&
				message.change_suggestions.length > 0 &&
				message.change_suggestions.map((suggestion) => (
					<div className='w-full' key={suggestion.id}>
						<TarjetaRecepcionPlan suggestion={suggestion} />
					</div>
				))}
		</div>
	);
};
