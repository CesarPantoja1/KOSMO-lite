'use client';

import type { PanZoomState } from '@/features/plantuml-viewer';
import type { ReviewCard } from '@/entities/consistency';
import { PlantUmlViewer } from '@/features/plantuml-viewer';
import { wrapPlantUmlSource } from '@/features/plantuml-viewer';
import { MarkdownText } from '@/shared/ui/markdown-text';
import { useCallback, useEffect, useRef, useState } from 'react';

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

function SyncedDiagramDiff({
	beforeSource,
	afterSource,
	isDeletion,
}: {
	beforeSource: string;
	afterSource: string;
	isDeletion: boolean;
}) {
	const [panZoom, setPanZoom] = useState<PanZoomState>({ zoom: 1, tx: 0, ty: 0 });

	const handlePanZoomChange = useCallback((state: PanZoomState) => {
		setPanZoom(state);
	}, []);

	const zoomReset = useCallback(() => {
		setPanZoom({ zoom: 1, tx: 0, ty: 0 });
	}, []);

	return (
		<div className='flex flex-col gap-1.5 overflow-hidden rounded-md border border-neutral-200 text-xs'>
			<div className='flex items-center justify-between bg-neutral-100 px-2 py-1.5'>
				<span className='font-mono text-[10px] font-semibold text-neutral-500 uppercase tracking-wider'>
					{isDeletion ? 'Eliminar' : 'Comparación de diagramas'}
				</span>
				<div className='flex items-center gap-1'>
					<button
						type='button'
						onClick={zoomReset}
						className='cursor-pointer px-2 h-6 flex items-center justify-center rounded-md text-xs font-medium text-neutral-500 hover:text-neutral-800 hover:bg-neutral-200 transition-colors'
						title='Restablecer zoom'
					>
						{Math.round(panZoom.zoom * 100)}%
					</button>
				</div>
			</div>

			<div className='flex min-h-60 max-h-[66.67vh]'>
				<div
					className={`flex flex-col ${isDeletion ? 'w-full' : 'w-1/2 border-r border-neutral-200'}`}
				>
					<div className='px-2.5 py-1 bg-error-50 font-mono text-[10px] font-semibold text-error-500 uppercase tracking-wider'>
						- Anterior
					</div>
					<div className='flex-1 min-h-0'>
						<DiagramPane
							source={beforeSource}
							panZoom={panZoom}
							onPanZoomChange={handlePanZoomChange}
						/>
					</div>
				</div>
				{!isDeletion && afterSource && (
					<div className='flex flex-col w-1/2'>
						<div className='px-2.5 py-1 bg-primary-50 font-mono text-[10px] font-semibold text-primary-500 uppercase tracking-wider'>
							+ Propuesto
						</div>
						<div className='flex-1 min-h-0'>
							<DiagramPane
								source={afterSource}
								panZoom={panZoom}
								onPanZoomChange={handlePanZoomChange}
							/>
						</div>
					</div>
				)}
			</div>
		</div>
	);
}

function DiagramPane({
	source,
	panZoom,
	onPanZoomChange,
}: {
	source: string;
	panZoom: PanZoomState;
	onPanZoomChange: (state: PanZoomState) => void;
}) {
	const containerRef = useRef<HTMLDivElement>(null);
	const [visible, setVisible] = useState(
		() => typeof IntersectionObserver === 'undefined',
	);

	useEffect(() => {
		if (visible) return;
		const el = containerRef.current;
		if (!el) return;
		const observer = new IntersectionObserver(
			(entries) => {
				for (const entry of entries) {
					if (entry.isIntersecting) {
						setVisible(true);
						observer.disconnect();
					}
				}
			},
			{ rootMargin: '200px' },
		);
		observer.observe(el);
		return () => observer.disconnect();
	}, [visible]);

	if (!visible) {
		return (
			<div ref={containerRef} className='py-3 text-center text-[11px] text-neutral-400'>
				Preparando diagrama…
			</div>
		);
	}

	return (
		<PlantUmlViewer
			source={source}
			showControls={false}
			controlledPanZoom={panZoom}
			onPanZoomChange={onPanZoomChange}
		/>
	);
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
	const beforeDiagram = card.diff?.before_diagram ?? '';
	const afterDiagram = card.diff?.after_diagram ?? '';
	const hasDiff = before !== '' || after !== '';
	const isDeletion = after === '' && before !== '';
	const isDiagram = card.artifact_type === 'ActivityDiagram';

	const renderDiffContent = (fragment: string, fullDiagram: string) => {
		if (!isDiagram) {
			return <MarkdownText content={fragment} />;
		}
		const source = fullDiagram.trim() ? fullDiagram : wrapPlantUmlSource(fragment);
		return source;
	};

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

			{hasDiff && isDiagram && (
				<SyncedDiagramDiff
					beforeSource={(() => {
						const src = beforeDiagram.trim() ? beforeDiagram : wrapPlantUmlSource(before);
						return src;
					})()}
					afterSource={(() => {
						const src = afterDiagram.trim() ? afterDiagram : wrapPlantUmlSource(after);
						return src;
					})()}
					isDeletion={isDeletion}
				/>
			)}

			{hasDiff && !isDiagram && (
				<div className='flex flex-col gap-1.5 overflow-hidden rounded-md border border-neutral-200 text-xs'>
					{isDeletion && (
						<div className='border-l-2 border-error-500 bg-error-50 p-2.5 text-error-700 [&_pre]:!bg-error-50 [&_code]:!bg-transparent [&_pre]:my-1 [&_p]:my-0.5'>
							<div className='mb-1 font-mono text-[10px] font-semibold text-error-500 uppercase tracking-wider'>
								- Eliminar
							</div>
							{renderDiffContent(before, beforeDiagram)}
						</div>
					)}
					{before !== '' && !isDeletion && (
						<div className='border-l-2 border-error-500 bg-error-50 p-2.5 text-error-700 [&_pre]:!bg-error-50 [&_code]:!bg-transparent [&_pre]:my-1 [&_p]:my-0.5'>
							<div className='mb-1 font-mono text-[10px] font-semibold text-error-500 uppercase tracking-wider'>
								- Anterior
							</div>
							{renderDiffContent(before, beforeDiagram)}
						</div>
					)}
					{!isDeletion && after !== '' && (
						<div className='border-l-2 border-primary-500 bg-primary-50 p-2.5 text-primary-900 [&_pre]:!bg-primary-100 [&_code]:!bg-transparent [&_pre]:my-1 [&_p]:my-0.5'>
							<div className='mb-1 font-mono text-[10px] font-semibold text-primary-500 uppercase tracking-wider'>
								+ Propuesto
							</div>
							{renderDiffContent(after, afterDiagram)}
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
