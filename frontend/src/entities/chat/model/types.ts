export type ChatPhase = 'discovery' | 'features' | 'requirements';

export interface ChatSessionSummary {
	id: string;
	phase: ChatPhase;
	context_id: string | null;
	created_at: string;
	message_count: number;
	last_message_at: string | null;
	title: string;
}

export interface CreateChatSessionResponse extends ChatSessionSummary {
	session_id: string;
}

export interface ChatSessionListResponse {
	sessions: ChatSessionSummary[];
}
