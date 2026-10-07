import { apiClient } from '@/shared/api';
import { API_BASE_URL, USE_MOCKS } from '@/shared/api/config';
import { parseApiError } from '@/shared/api/errors';
import { authHeaders } from '@/shared/api';
import { consumeSse } from '@/shared/lib';
import type { SseEventHandler } from '@/shared/lib';
import type { ImplementationLog, ImplementationSummary } from '../model/types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const mockSummary: ImplementationSummary = {
	featureId: '',
	featureTitle: '',
	featureDisplayId: '',
	status: 'completed',
	metrics: [
		{
			value: '5',
			label: 'Pantallas',
			icon: 'screens',
			iconBg: 'bg-ai-50',
			iconColor: 'text-ai-600',
		},
		{
			value: '3',
			label: 'Entidades',
			icon: 'entities',
			iconBg: 'bg-primary-50',
			iconColor: 'text-primary-600',
		},
		{
			value: '8',
			label: 'Reglas',
			icon: 'rules',
			iconBg: 'bg-warning-50',
			iconColor: 'text-warning-600',
		},
		{
			value: '4',
			label: 'Integraciones',
			icon: 'integrations',
			iconBg: 'bg-primary-50',
			iconColor: 'text-primary-600',
		},
		{
			value: '6',
			label: 'Validaciones',
			icon: 'validations',
			iconBg: 'bg-info-50',
			iconColor: 'text-info-700',
		},
		{
			value: '12',
			label: 'Acciones',
			icon: 'actions',
			iconBg: 'bg-ai-50',
			iconColor: 'text-ai-600',
		},
	],
	technologies: ['Next.js', 'TypeScript', 'Tailwind CSS', 'PostgreSQL', 'Node.js'],
	nextSteps: [
		'Descarga el proyecto generado',
		'Continúa personalizando tu aplicación',
		'Comparte o publica tu aplicación cuando esté lista',
	],
	generatedAt: null,
	generatedFiles: [
		'src/app/page.tsx',
		'src/app/layout.tsx',
		'src/db/schema.ts',
		'src/components/button.tsx',
		'tests/app.test.tsx',
		'package.json',
	],
};

const PROGRESS_MESSAGES: Record<string, string> = {
	session_created: 'Sesión iniciada',
	plan_progress: 'Planificando la implementación...',
	plan_complete: 'Plan aprobado, preparando generación...',
	build_progress: 'Generando código...',
	build_complete: 'Código generado, ejecutando validaciones...',
};

export function buildSummary(
	featureId: string,
	featureTitle: string,
	featureDisplayId: string,
	data: Record<string, unknown>,
	timestamp: string,
): ImplementationSummary {
	const files = Array.isArray(data.generated_files) ? data.generated_files : [];
	const filesCount = files.length;
	const featuresCount =
		typeof data.features_count === 'number'
			? data.features_count
			: typeof data.featuresCount === 'number'
				? data.featuresCount
				: 1;

	const reqsCount =
		typeof data.requirements_count === 'number'
			? data.requirements_count
			: typeof data.requirementsCount === 'number'
				? data.requirementsCount
				: 1;

	const edges =
		typeof data.traceability_edges === 'number'
			? data.traceability_edges
			: typeof data.traceability_edges_count === 'number'
				? data.traceability_edges_count
				: typeof data.traceabilityEdgesCount === 'number'
					? data.traceabilityEdgesCount
					: Math.max(1, reqsCount + filesCount);

	const validationsPassed =
		typeof data.validations_passed === 'number'
			? data.validations_passed
			: typeof data.validationsPassed === 'number'
				? data.validationsPassed
				: 4;
	const validationsTotal =
		typeof data.validations_total === 'number'
			? data.validations_total
			: typeof data.validationsTotal === 'number'
				? data.validationsTotal
				: 4;

	const validationsLabel =
		validationsTotal > 0 && validationsPassed === validationsTotal
			? '100%'
			: `${validationsPassed}/${validationsTotal}`;

	const technologies =
		Array.isArray(data.technologies) && data.technologies.length > 0
			? (data.technologies as string[])
			: ['Next.js', 'TypeScript', 'Bootstrap 5', 'Vitest'];

	return {
		featureId,
		featureTitle,
		featureDisplayId,
		status: 'completed',
		metrics: [
			{
				value: String(featuresCount),
				label: 'Funcionalidades implementadas',
				icon: 'features',
				iconBg: 'bg-ai-50',
				iconColor: 'text-ai-600',
			},
			{
				value: String(reqsCount),
				label: 'Requisitos de negocio',
				icon: 'rules',
				iconBg: 'bg-warning-50',
				iconColor: 'text-warning-600',
			},
			{
				value: String(edges),
				label: 'Enlaces de trazabilidad',
				icon: 'integrations',
				iconBg: 'bg-primary-50',
				iconColor: 'text-primary-600',
			},
			{
				value: validationsLabel,
				label: 'Calidad verificada',
				icon: 'validations',
				iconBg: 'bg-info-50',
				iconColor: 'text-info-700',
			},
		],
		technologies,
		nextSteps: [
			'Explora la vista previa interactiva de tu aplicación',
			'Sincroniza y respalda tu código en tu repositorio de GitHub',
			'Continúa con la siguiente funcionalidad de tu proyecto',
		],
		generatedAt: timestamp || new Date().toISOString(),
		generatedFiles: files.map(String).slice().sort((a, b) => a.localeCompare(b)),
	};
}

export const fetchImplementationFile = async (
	implementationId: string,
	path: string,
): Promise<string> => {
	const data = await apiClient<{ content: string }>(
		`/api/v1/implementations/${implementationId}/files/content?path=${encodeURIComponent(path)}`,
	);
	return data.content;
};

export interface ImplementationRecord {
	implementationId: string;
	featureId: string;
	projectId: string;
	status: string;
	generatedFiles: string[];
	featuresCount?: number;
	screensCount?: number;
	requirementsCount?: number;
	validationsPassed?: number;
	validationsTotal?: number;
	traceabilityEdgesCount?: number;
	technologies?: string[];
	updatedAt: string;
}

const toRecord = (data: {
	implementation_id: string;
	feature_id: string;
	project_id: string;
	status: string;
	generated_files?: string[];
	features_count?: number;
	screens_count?: number;
	requirements_count?: number;
	validations_passed?: number;
	validations_total?: number;
	traceability_edges_count?: number;
	technologies?: string[];
	updated_at?: string;
}): ImplementationRecord => ({
	implementationId: data.implementation_id,
	featureId: data.feature_id,
	projectId: data.project_id,
	status: data.status,
	generatedFiles: Array.isArray(data.generated_files) ? data.generated_files : [],
	featuresCount: typeof data.features_count === 'number' ? data.features_count : undefined,
	screensCount: typeof data.screens_count === 'number' ? data.screens_count : undefined,
	requirementsCount: typeof data.requirements_count === 'number' ? data.requirements_count : undefined,
	validationsPassed: typeof data.validations_passed === 'number' ? data.validations_passed : undefined,
	validationsTotal: typeof data.validations_total === 'number' ? data.validations_total : undefined,
	traceabilityEdgesCount:
		typeof data.traceability_edges_count === 'number' ? data.traceability_edges_count : undefined,
	technologies: Array.isArray(data.technologies) ? data.technologies : undefined,
	updatedAt: data.updated_at ?? new Date().toISOString(),
});

export const fetchImplementation = async (
	featureId: string,
): Promise<ImplementationRecord | null> => {
	try {
		const data = await apiClient<Parameters<typeof toRecord>[0]>(
			`/api/v1/implementations?feature_id=${encodeURIComponent(featureId)}`,
		);
		return toRecord(data);
	} catch (err: unknown) {
		if (
			typeof err === 'object' &&
			err !== null &&
			'status' in err &&
			(err as { status: number }).status === 404
		) {
			return null;
		}
		throw err;
	}
};

export const generateImplementation = async (
	featureId: string,
	featureTitle: string,
	featureDisplayId: string,
	onProgress?: (message: string, log?: ImplementationLog) => void,
): Promise<ImplementationSummary> => {
	if (USE_MOCKS) {
		await delay(2000);
		return {
			...mockSummary,
			featureId,
			featureTitle,
			featureDisplayId,
			generatedAt: new Date().toISOString(),
		};
	}

	const { implementation_id } = await apiClient<{ implementation_id: string }>(
		'/api/v1/implementations',
		{
			method: 'POST',
			body: JSON.stringify({ feature_id: featureId, max_retries: 3 }),
		},
	);
	onProgress?.('Implementación iniciada', {
		id: `log_${Date.now()}_init`,
		type: 'info',
		message: 'Implementación iniciada',
		timestamp: new Date().toISOString(),
	});

	const res = await fetch(
		`${API_BASE_URL}/api/v1/implementations/${implementation_id}/events`,
		{
			headers: authHeaders(),
			cache: 'no-store',
		},
	);
	if (!res.ok) {
		throw parseApiError(res, await res.json().catch(() => null));
	}

	let done: ImplementationSummary | null = null;
	let logCounter = 0;

	const onEvent: SseEventHandler = (raw) => {
		const eventType = String(raw.event_type ?? '');
		const data = (raw.data ?? {}) as Record<string, unknown>;
		const eventTimestamp = String(raw.timestamp ?? new Date().toISOString());
		logCounter += 1;
		const logId = `log_${Date.now()}_${logCounter}`;

		if (eventType === 'retry') {
			const attempt = String(data.attempt ?? '?');
			const max = String(data.max_retries ?? '?');
			const msg = `Corrigiendo errores de validación (intento ${attempt}/${max})`;
			onProgress?.(msg, {
				id: logId,
				type: 'retry',
				message: msg,
				timestamp: eventTimestamp,
			});
		} else if (eventType === 'file_edit') {
			const filePath = typeof data.path === 'string' && data.path ? data.path : '';
			const msg = filePath ? `Se generó \`${filePath}\`` : 'Generando archivo...';
			onProgress?.(msg, {
				id: logId,
				type: 'file',
				message: msg,
				timestamp: eventTimestamp,
				detail: typeof data.content === 'string' ? data.content : undefined,
			});
		} else if (eventType === 'done' && data.status === 'implemented') {
			done = buildSummary(
				featureId,
				featureTitle,
				featureDisplayId,
				data,
				eventTimestamp,
			);
			onProgress?.('Implementación completada con éxito', {
				id: logId,
				type: 'success',
				message: 'Implementación completada con éxito',
				timestamp: eventTimestamp,
			});
		} else if (eventType === 'error') {
			const detail =
				typeof data.error === 'string' && data.error
					? data.error
					: data.status === 'requires_review'
						? 'La validación falló tras agotar los reintentos. Revisa los errores y reintenta.'
						: 'Ocurrió un error durante la generación.';
			onProgress?.(detail, {
				id: logId,
				type: 'error',
				message: detail,
				timestamp: eventTimestamp,
			});
			throw new Error(detail);
		} else {
			const thought = typeof data.thought === 'string' ? data.thought : null;
			const tool = typeof data.tool === 'string' ? data.tool : null;
			const delta = typeof data.delta === 'string' ? data.delta : null;
			const stage = typeof data.stage === 'string' ? data.stage : '';

			if (tool) {
				const msg = `Se llamó a \`${tool}\``;
				onProgress?.(msg, {
					id: logId,
					type: 'tool',
					message: msg,
					timestamp: eventTimestamp,
					detail: typeof data.detail === 'string' ? data.detail : undefined,
				});
			} else if (thought || stage === 'thinking') {
				onProgress?.('Pensando', {
					id: logId,
					type: 'thought',
					message: thought || 'Pensando',
					timestamp: eventTimestamp,
				});
			} else if (delta) {
				const logType =
					stage === 'validating' || stage === 'validation_passed' ? 'validation' : 'code';
				onProgress?.(delta, {
					id: logId,
					type: logType,
					message: delta,
					timestamp: eventTimestamp,
					detail: typeof data.detail === 'string' ? data.detail : undefined,
				});
			} else {
				const message = PROGRESS_MESSAGES[eventType] ?? 'Procesando...';
				onProgress?.(message, {
					id: logId,
					type: 'info',
					message,
					timestamp: eventTimestamp,
				});
			}
		}
	};
	await consumeSse(res, onEvent);

	if (!done) {
		throw new Error('La generación no se completó. Puedes volver a intentarlo.');
	}
	return done;
};

export interface ImplementationEventHandlers {
	onDelta?: (delta: string) => void;
	onDone?: (delta: string) => void;
	onError?: (error: string) => void;
}

export async function subscribeImplementationEvents(
	implementationId: string,
	handlers: ImplementationEventHandlers,
): Promise<void> {
	const res = await fetch(
		`${API_BASE_URL}/api/v1/implementations/${implementationId}/events`,
		{
			headers: authHeaders(),
			cache: 'no-store',
		},
	);
	if (!res.ok) {
		throw parseApiError(res, await res.json().catch(() => null));
	}

	const onEvent: SseEventHandler = (raw) => {
		const eventType = String(raw.event_type ?? '');
		const data = (raw.data ?? {}) as Record<string, unknown>;
		if (eventType === 'done') {
			const delta =
				typeof data.delta === 'string' && data.delta ? data.delta : 'Proceso completado.';
			handlers.onDone?.(delta);
		} else if (eventType === 'error') {
			const detail =
				typeof data.error === 'string' && data.error
					? data.error
					: 'Ocurrió un error durante el proceso.';
			handlers.onError?.(detail);
		} else {
			const delta = typeof data.delta === 'string' ? data.delta : null;
			if (delta) handlers.onDelta?.(delta);
		}
	};
	await consumeSse(res, onEvent);
}
