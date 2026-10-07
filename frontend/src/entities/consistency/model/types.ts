export type ConsistencyTargetPhase = 'features' | 'requirements' | 'model' | 'implementation';

export type ConsistencyEvaluationStatus =
	| 'evaluating'
	| 'completed'
	| 'failed'
	| 'applied'
	| 'discarded';

export interface PhaseConsistencyStatus {
	pending: number;
	evaluating: number;
	failed: number;
}

export interface ConsistencyStatusResponse {
	phases: Record<ConsistencyTargetPhase, PhaseConsistencyStatus>;
}

export interface ReviewCard {
	evaluation_id: string;
	source_phase: string;
	target_phase: string;
	target_artifact_id: string;
	artifact_type: string;
	target_display_id: string;
	target_title: string;
	section: string;
	rationale: string;
	action: string;
	diff: {
		field: string;
		before: string;
		after: string;
		before_diagram?: string;
		after_diagram?: string;
	} | null;
	status: string;
	failure_reason: string | null;
}

export interface ConsistencyReviewResponse {
	cards: ReviewCard[];
}

export interface EvaluationActionResult {
	evaluation_id: string;
	applied?: boolean;
	discarded?: boolean;
	target_id?: string;
	project_id?: string;
}

export interface BulkResolveRequest {
	action: 'apply' | 'discard';
	target_phase: string;
}

export interface BulkResolveResult {
	resolved: number;
	skipped: number;
}

export interface ConsistencyActivityItem {
	evaluation_id: string;
	status: string;
	source_phase: string;
	target_phase: string;
	target_artifact_id: string;
	target_title: string;
	failure_reason: string | null;
	updated_at: string;
}

export interface ConsistencyActivityResponse {
	items: ConsistencyActivityItem[];
}
