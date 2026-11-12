export interface RegisterRequest {
	name: string;
	email: string;
	password: string;
}

export interface AuthorizeRequest {
	email: string;
	password: string;
	code_challenge: string;
	code_challenge_method?: 'S256';
	scopes?: string[];
}

export interface TokenExchangeRequest {
	grant_type: 'authorization_code';
	code: string;
	code_verifier: string;
}

export interface TokenRefreshRequest {
	grant_type: 'refresh_token';
	refresh_token: string;
}

export interface LogoutRequest {
	refresh_token?: string | null;
}

export interface UserPublic {
	id: string;
	name: string;
	email: string;
	avatar_url?: string | null;
	created_at: string;
}

export interface RegisterResponse {
	email: string;
	message: string;
}

export interface AuthorizationCodeResponse {
	authorization_code: string;
	expires_in: number;
}

export interface TokenView {
	token: string;
	jti: string;
	expires_at: string;
}

export interface TokenPairResponse {
	access: TokenView;
	refresh: TokenView;
	token_type: 'Bearer';
}

export interface PrincipalView {
	subject: string;
	name?: string | null;
	email?: string | null;
	avatar_url?: string | null;
	scopes: string[];
}

export interface OAuthErrorResponse {
	error: string;
	error_description: string;
}
