/**
 * Servidor MSW para Node (Vitest + jsdom). Intercepta `fetch` a nivel de red,
 * así los tests ejercitan el `apiClient` real sin mockear módulos.
 * El ciclo de vida (listen / resetHandlers / close) se gestiona en `vitest.setup.ts`.
 */
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
