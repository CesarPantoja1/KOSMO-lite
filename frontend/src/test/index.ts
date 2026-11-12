/**
 * Punto de entrada de las utilidades de testing.
 *
 * @example
 *   import { renderWithProviders, server, http, HttpResponse, apiUrl, crearProyecto } from '@/test';
 */
export { renderWithProviders } from './render';
export { server } from './msw/server';
export { apiUrl, handlers } from './msw/handlers';
export { respuestaSse, streamControlado } from './msw/sse';
export { http, HttpResponse, delay } from 'msw';
export { mockRouter, setMockNavigation } from './mocks/next-navigation';
export * from './factories';
