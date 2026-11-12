import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
	plugins: [react()],
	resolve: {
		alias: {
			'@': path.resolve(__dirname, './src'),
			app: path.resolve(__dirname, './app'),
		},
	},
	test: {
		environment: 'jsdom',
		globals: true,
		setupFiles: './vitest.setup.ts',
		coverage: {
			provider: 'v8',
			reporter: ['text', 'html', 'lcov'],
			include: ['src/**/*.{ts,tsx}'],
			exclude: [
				'**/*.test.*',
				'**/index.ts',
				'**/*.d.ts',
				'**/AGENTS.md',
				'src/test/**',
				'src/shared/ui/icons/**',
			],
			thresholds: {
				lines: 80,
				statements: 77,
				functions: 77,
				branches: 72,
			},
		},
	},
});
