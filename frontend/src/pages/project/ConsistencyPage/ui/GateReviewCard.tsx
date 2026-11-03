'use client';

import type { ReviewCard } from '@/entities/consistency';
import { MarkdownText } from '@/shared/ui/markdown-text';
import { useEffect, useRef, useState } from 'react';

const ACTION_LABELS: Record<string, string> = {
	update: 'Actualizar',
	create: 'Crear',
	delete: 'Eliminar',
	new: 'Nuevo',
};

const ACTION_STYLES: Record<string, string> = {
	update: 'bg-primary-50 text-primary-600',
	create: 'bg-neutral-100 text-neutral-600',
	delete: 'bg-error-50 text-error-600',
	new: 'bg-neutral-100 text-neutral-600',
};

interface GateReviewCardProps {
	card: ReviewCard;
	busy: boolean;
	onApply: () => void;
	onDiscard: () => void;
}

export const GateReviewCard = ({
	card,
	busy,
	onApply,
	onDiscard,
}: GateReviewCardProps) => {
	const [showFullRationale, setShowFullRationale] = useState(false);
	const [isClamped, setIsClamped] = useState(true);
	const rationaleRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		const el = rationaleRef.current;
		if (!el) return;
		const savedMH = el.style.maxHeight;
		const savedOF = el.style.overflow;
		el.style.maxHeight = 'none';
		el.style.overflow = 'visible';
		const lh = parseFloat(getComputedStyle(el).lineHeight) || 24;
		const needs = el.scrollHeight > lh * 2 + 1;
		el.style.maxHeight = savedMH;
		el.style.overflow = savedOF;
		setIsClamped(needs);
	}, [card.rationale]);

	const actionLabel = ACTION_LABELS[card.action] ?? card.action;
	const actionStyles = ACTION_STYLES[card.action] ?? ACTION_STYLES.update;

	const before = card.diff?.before ?? '';
	const after = card.diff?.after ?? '';
	const hasDiff = before !== '' || after !== '';
	const isDeletion = after === '' && before !== '';

	return (
		<article className='flex flex-col gap-3 rounded-lg border border-neutral-200 bg-neutral-0 p-4 shadow-sm'>
			<header className='sticky top-0 z-10 -mx-4 -mt-4 mb-1 flex flex-wrap items-center justify-between gap-3 rounded-t-lg border-b border-neutral-200 bg-neutral-50/95 px-4 py-3 backdrop-blur-xs'>
				<div className='flex items-center gap-2 min-w-0 flex-1'>
					<span className='rounded-md bg-neutral-200 px-2 py-0.5 font-mono text-xs font-semibold text-neutral-700 shrink-0'>
						{card.target_display_id || card.target_artifact_id}
					</span>
					<h3 className='truncate text-sm font-semibold text-neutral-800' title={card.target_title}>
						{card.target_title}
					</h3>
					<span
						className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${actionStyles}`}
					>
						{actionLabel}
					</span>
				</div>
				<div className='flex items-center gap-2 shrink-0'>
					<button
						type='button'
						onClick={onDiscard}
						disabled={busy}
						className='btn btn-secondary btn-sm disabled:opacity-60'
					>
						Descartar
					</button>
					<button
						type='button'
						onClick={onApply}
						disabled={busy}
						className='btn btn-primary btn-sm disabled:opacity-60'
					>
						{busy ? 'Aplicando…' : 'Aplicar'}
					</button>
				</div>
			</header>

			{card.rationale && (
				<div>
					<div
						ref={rationaleRef}
						className='text-sm leading-6 text-neutral-600'
						style={
							isClamped && !showFullRationale
								? { maxHeight: '3rem', overflow: 'hidden' }
								: undefined
						}
					>
						{card.rationale}
					</div>
					{isClamped && (
						<button
							type='button'
							onClick={() => setShowFullRationale((v) => !v)}
							className='mt-1 cursor-pointer text-xs font-medium text-ai-600 hover:underline'
						>
							{showFullRationale ? 'Ver menos' : 'Ver más'}
						</button>
					)}
				</div>
			)}

			{hasDiff && (
				<div className='flex flex-col gap-1.5 overflow-hidden rounded-md border border-neutral-200 text-xs'>
					{isDeletion && (
						<div className='border-l-2 border-error-500 bg-error-50 p-2.5 text-error-700 [&_pre]:!bg-error-50 [&_code]:!bg-transparent [&_pre]:my-1 [&_p]:my-0.5'>
							<div className='mb-1 font-mono text-[10px] font-semibold text-error-500 uppercase tracking-wider'>
								- Eliminar
							</div>
							<MarkdownText content={before} />
						</div>
					)}
					{before !== '' && !isDeletion && (
						<div className='border-l-2 border-error-500 bg-error-50 p-2.5 text-error-700 [&_pre]:!bg-error-50 [&_code]:!bg-transparent [&_pre]:my-1 [&_p]:my-0.5'>
							<div className='mb-1 font-mono text-[10px] font-semibold text-error-500 uppercase tracking-wider'>
								- Anterior
							</div>
							<MarkdownText content={before} />
						</div>
					)}
					{!isDeletion && after !== '' && (
						<div className='border-l-2 border-primary-500 bg-primary-50 p-2.5 text-primary-900 [&_pre]:!bg-primary-100 [&_code]:!bg-transparent [&_pre]:my-1 [&_p]:my-0.5'>
							<div className='mb-1 font-mono text-[10px] font-semibold text-primary-500 uppercase tracking-wider'>
								+ Propuesto
							</div>
							<MarkdownText content={after} />
						</div>
					)}
				</div>
			)}

			{card.status === 'failed' && card.failure_reason && (
				<p className='rounded-md bg-error-50 px-3 py-2 text-xs text-error-700'>
					{card.failure_reason}
				</p>
			)}
		</article>
	);
};
