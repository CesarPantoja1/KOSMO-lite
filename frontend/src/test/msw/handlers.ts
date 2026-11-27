/**
 * Handlers MSW por defecto: simulan las respuestas "felices" del backend.
 *
 * Cada test puede sobrescribir un endpoint puntual con `server.use(...)` para
 * probar errores, listas vacías, etc. Los cambios se revierten en `afterEach`.
 *
 * @example
 *   server.use(http.get(apiUrl('/api/v1/projects'), () => HttpResponse.json([], { status: 500 })));
 */
import { http, HttpResponse } from 'msw';
import { API_BASE_URL } from '@/shared/api/config';
import {
	crearAiConfig,
	crearCaracteristica,
	crearEstadoConsistencia,
	crearIntegracion,
	crearProveedoresIA,
	crearProyecto,
	crearTokens,
	crearUsuario,
} from '../factories';
import { respuestaSse } from './sse';

/** Construye la URL absoluta que usa `apiClient` para un path del backend. */
export const apiUrl = (path: string) => `${API_BASE_URL}${path}`;

export const handlers = [
	// --- Auth ---
	http.get(apiUrl('/api/v1/auth/me'), () => HttpResponse.json(crearUsuario())),
	http.post(apiUrl('/api/v1/auth/authorize'), () =>
		HttpResponse.json({ authorization_code: 'code-test', expires_in: 60 }),
	),
	http.post(apiUrl('/api/v1/auth/token'), () => HttpResponse.json(crearTokens())),
	http.post(apiUrl('/api/v1/auth/refresh'), () => HttpResponse.json(crearTokens())),
	http.post(apiUrl('/api/v1/auth/logout'), () => new HttpResponse(null, { status: 204 })),
	http.post(apiUrl('/api/v1/auth/register'), () =>
		HttpResponse.json(
			{ email: 'usuario@test.com', message: 'Usuario registrado' },
			{ status: 201 },
		),
	),

	// --- Proyectos ---
	http.get(apiUrl('/api/v1/projects'), () =>
		HttpResponse.json([crearProyecto({ id: 'prj_1' }), crearProyecto({ id: 'prj_2' })]),
	),
	http.get(apiUrl('/api/v1/projects/:projectId'), ({ params }) =>
		HttpResponse.json(crearProyecto({ id: String(params.projectId) })),
	),
	http.post(apiUrl('/api/v1/projects'), async ({ request }) => {
		const body = (await request.json()) as { name: string; description: string };
		return HttpResponse.json(crearProyecto({ id: 'prj_nuevo', ...body }), {
			status: 201,
		});
	}),
	http.post(apiUrl('/api/v1/projects/:projectId/github/push'), () =>
		HttpResponse.json({ has_repository: true, sync_status: 'synced' }),
	),

	// --- Descubrimiento (por defecto: aún no existe → 404, caso normal) ---
	http.get(apiUrl('/api/v1/projects/:projectId/discovery'), () =>
		HttpResponse.json({ detail: 'Descubrimiento no encontrado' }, { status: 404 }),
	),

	// --- Requisitos (por defecto: vacíos) ---
	http.get(apiUrl('/api/v1/features/:featureId/requirements'), () =>
		HttpResponse.json({ document_markdown: null }),
	),

	// --- Características ---
	http.get(apiUrl('/api/v1/projects/:projectId/features'), ({ params }) =>
		HttpResponse.json([
			crearCaracteristica({ project_id: String(params.projectId) }),
			crearCaracteristica({ project_id: String(params.projectId) }),
		]),
	),

	// --- Integraciones (por defecto: conectadas) ---
	http.get(apiUrl('/api/v1/integrations/:provider/status'), ({ params }) =>
		HttpResponse.json(
			crearIntegracion({ provider: params.provider as 'github' | 'railway' }),
		),
	),

	// --- Configuración de IA (por defecto: con API key) ---
	http.get(apiUrl('/api/v1/ai-config'), () => HttpResponse.json(crearAiConfig())),
	http.get(apiUrl('/api/v1/ai-config/providers'), () =>
		HttpResponse.json(crearProveedoresIA()),
	),

	// --- Sesiones de chat (por defecto: ninguna) ---
	http.get(apiUrl('/api/v1/projects/:projectId/chat-sessions'), () =>
		HttpResponse.json({ sessions: [] }),
	),

	// --- Historial de chat de una característica (por defecto: vacío) ---
	http.get(apiUrl('/api/v1/features/:featureId/chat/history'), () =>
		HttpResponse.json({
			phase: 'features',
			context: '',
			messages: [],
			has_more: false,
			next_cursor: null,
		}),
	),

	// --- Eventos de implementación (por defecto: stream vacío que se cierra) ---
	http.get(apiUrl('/api/v1/implementations/:implementationId/events'), () =>
		respuestaSse([]),
	),

	// --- Estado del repositorio en GitHub ---
	http.get(apiUrl('/api/v1/projects/:projectId/github'), () =>
		HttpResponse.json({ has_repository: false, sync_status: 'not_created' }),
	),

	// --- Consistencia ---
	http.get(apiUrl('/api/v1/projects/:projectId/consistency/status'), () =>
		HttpResponse.json(crearEstadoConsistencia()),
	),
];
