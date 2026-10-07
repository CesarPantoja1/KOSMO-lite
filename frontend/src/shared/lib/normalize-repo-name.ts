const MAX_REPO_NAME_LENGTH = 100;

export function normalizeRepoName(input: string): string {
	return input
		.toLowerCase()
		.replace(/\s+/g, '-')
		.replace(/[^a-z0-9._-]/g, '')
		.replace(/-+/g, '-')
		.replace(/^-+/, '')
		.replace(/-+$/, '')
		.slice(0, MAX_REPO_NAME_LENGTH);
}