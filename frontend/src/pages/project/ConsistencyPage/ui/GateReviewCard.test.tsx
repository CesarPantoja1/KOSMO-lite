import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ReviewCard } from '@/entities/consistency';

vi.mock('@/features/plantuml-viewer', async (importOriginal) => {
	const actual = await importOriginal<typeof import('@/features/plantuml-viewer')>();
	return {
		...actual,
		PlantUmlViewer: ({
			source,
			showControls,
			fallbackContent,
		}: {
			source: string;
			showControls?: boolean;
			fallbackContent?: string;
		}) => (
			<div
				data-testid='plantuml-viewer'
				data-source={source}
				data-controls={String(showControls ?? true)}
				data-fallback={fallbackContent ?? ''}
			/>
		),
	};
});

import { GateReviewCard } from './GateReviewCard';

function makeCard(overrides: Partial<ReviewCard> = {}): ReviewCard {
	return {
		evaluation_id: 'cev_01',
		source_phase: 'descubrimiento',
		target_phase: 'modelo',
		target_artifact_id: 'feat_01',
		artifact_type: 'Feature',
		target_display_id: 'C01',
		target_title: 'Consultar catálogo',
		section: 'description',
		rationale: 'Cambio detectado',
		action: 'update',
		diff: { field: 'description', before: 'antes', after: 'después' },
		status: 'completed',
		failure_reason: null,
		...overrides,
	};
}

describe('GateReviewCard', () => {
	it('renderiza fragmentos de diagrama envueltos sin controles', () => {
		const card = makeCard({
			artifact_type: 'ActivityDiagram',
			diff: {
				field: 'estructura UML',
				before: '|#lightgray|Sistema|\n:Paso;',
				after: '|#lightgray|Sistema|\n:Paso nuevo;',
			},
		});

		render(
			<GateReviewCard card={card} busy={false} onApply={() => {}} onDiscard={() => {}} />,
		);

		const viewers = screen.getAllByTestId('plantuml-viewer');
		expect(viewers).toHaveLength(2);
		expect(viewers[0]).toHaveAttribute(
			'data-source',
			'@startuml\n|#lightgray|Sistema|\n:Paso;\n@enduml',
		);
		expect(viewers[0]).toHaveAttribute('data-controls', 'false');
		expect(viewers[1]).toHaveAttribute(
			'data-source',
			'@startuml\n|#lightgray|Sistema|\n:Paso nuevo;\n@enduml',
		);
	});

	it('renderiza diagramas completos sin envoltura y con controles', () => {
		const fullBefore = '@startuml\nstart\n|#pink|Colaborador|\n:Paso;\nstop\n@enduml';
		const fullAfter = '@startuml\nstart\n|#pink|Dueno|\n:Paso;\nstop\n@enduml';
		const card = makeCard({
			artifact_type: 'ActivityDiagram',
			diff: {
				field: 'estructura UML',
				before: '|#pink|Colaborador|',
				after: '|#pink|Dueno|',
				before_diagram: fullBefore,
				after_diagram: fullAfter,
			},
		});

		render(
			<GateReviewCard card={card} busy={false} onApply={() => {}} onDiscard={() => {}} />,
		);

		const viewers = screen.getAllByTestId('plantuml-viewer');
		expect(viewers).toHaveLength(2);
		expect(viewers[0]).toHaveAttribute('data-source', fullBefore);
		expect(viewers[0]).toHaveAttribute('data-controls', 'false');
		expect(viewers[1]).toHaveAttribute('data-source', fullAfter);
	});

	it('sigue usando texto para otros tipos de artefacto', () => {
		render(
			<GateReviewCard
				card={makeCard()}
				busy={false}
				onApply={() => {}}
				onDiscard={() => {}}
			/>,
		);

		expect(screen.queryAllByTestId('plantuml-viewer')).toHaveLength(0);
		expect(screen.getByText('antes')).toBeInTheDocument();
	});

	it('renderiza los botones Descartar y Aplicar arriba y llama a los callbacks al pulsarlos', () => {
		const handleApply = vi.fn();
		const handleDiscard = vi.fn();

		render(
			<GateReviewCard
				card={makeCard()}
				busy={false}
				onApply={handleApply}
				onDiscard={handleDiscard}
			/>,
		);

		const applyBtn = screen.getByRole('button', { name: 'Aplicar' });
		const discardBtn = screen.getByRole('button', { name: 'Descartar' });

		expect(applyBtn).toBeInTheDocument();
		expect(discardBtn).toBeInTheDocument();

		applyBtn.click();
		expect(handleApply).toHaveBeenCalledTimes(1);

		discardBtn.click();
		expect(handleDiscard).toHaveBeenCalledTimes(1);
	});
});
