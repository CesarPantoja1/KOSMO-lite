import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ReviewCard } from '@/entities/consistency';

import { GateReviewCard } from './GateReviewCard';

function makeCard(overrides: Partial<ReviewCard> = {}): ReviewCard {
	return {
		evaluation_id: 'cev_01',
		source_phase: 'descubrimiento',
		target_phase: 'requisitos',
		target_artifact_id: 'feat_01',
		artifact_type: 'EARSRequirement',
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
	it('renderiza el diff textual de un artefacto', () => {
		render(
			<GateReviewCard
				card={makeCard()}
				busy={false}
				onApply={() => {}}
				onDiscard={() => {}}
			/>,
		);

		expect(screen.getByText('antes')).toBeInTheDocument();
		expect(screen.getByText('después')).toBeInTheDocument();
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
