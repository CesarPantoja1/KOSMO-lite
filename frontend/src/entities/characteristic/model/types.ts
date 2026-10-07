export interface CharacteristicResponse {
	id: string;
	project_id: string;
	number: number;
	title: string;
	slug: string;
	description: string;
	origin: string;
	display_id: string;
	warnings?: string[];
}

export interface SuggestCharacteristic {
	number: number;
	title: string;
	description: string;
	origin: string;
}

export interface CharacteristicSave {
	title: string;
	description: string;
	rationale: string;
}

export interface CreateCharacteristicResponse {
	is_saved: boolean;
	feature?: CharacteristicResponse;
	origin: string;
	is_consistent: boolean;
	inconsistency_reason?: string;
	warnings?: string[];
}

export interface CreateCharacteristicParams {
	title: string;
	description: string;
	titleMaxLength: number;
	descriptionMaxLength: number;
	origin?: string;
}
