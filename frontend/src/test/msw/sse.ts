/**
 * Utilidades para simular respuestas Server-Sent Events (SSE) con MSW.
 *
 * @example
 *   // Stream que emite eventos y se cierra:
 *   server.use(http.post(apiUrl(url), () => respuestaSse([{ type: 'chunk', content: 'Hola' }])));
 *
 *   // Stream controlado manualmente desde el test:
 *   const stream = streamControlado();
 *   server.use(http.post(apiUrl(url), () => stream.respuesta));
 *   stream.emitir({ type: 'chunk', content: 'Ho' });
 *   stream.cerrar();
 */
import { HttpResponse } from 'msw';

const encoder = new TextEncoder();
const linea = (evento: Record<string, unknown>) =>
	encoder.encode(`data: ${JSON.stringify(evento)}\n\n`);
const CABECERAS = { 'Content-Type': 'text/event-stream' };

/** Respuesta SSE que emite todos los eventos indicados y cierra el stream. */
export function respuestaSse(eventos: Record<string, unknown>[]) {
	const stream = new ReadableStream({
		start(controller) {
			eventos.forEach((e) => controller.enqueue(linea(e)));
			controller.close();
		},
	});
	return new HttpResponse(stream, { headers: CABECERAS });
}

/** Stream SSE cuyo contenido y cierre controla el test paso a paso. */
export function streamControlado() {
	let controller!: ReadableStreamDefaultController<Uint8Array>;
	const stream = new ReadableStream<Uint8Array>({
		start(c) {
			controller = c;
		},
	});
	return {
		/** Crear la respuesta dentro del handler (una sola vez por stream). */
		get respuesta() {
			return new HttpResponse(stream, { headers: CABECERAS });
		},
		emitir: (evento: Record<string, unknown>) => controller.enqueue(linea(evento)),
		cerrar: () => controller.close(),
	};
}
