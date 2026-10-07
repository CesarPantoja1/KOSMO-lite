'use client';

import {
	Ai,
	ArrowRight,
	Characteristics,
	Discovery,
	Folder,
	Implementation,
	Logo,
	Modeling,
	Requirements,
} from '@/shared/ui';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/shared/model';

interface HeroProps {
	onComenzar: () => void;
	onVerVideo: () => void;
}

const sidebarItems = [
	{ label: 'Idea', icon: <Folder size={12} color='text-neutral-500' /> },
	{ label: 'Descubrimiento', icon: <Discovery size={12} color='text-neutral-500' /> },
	{
		label: 'Funcionalidades',
		icon: <Characteristics size={12} color='text-neutral-500' />,
	},
	{
		label: 'Criterios (EARS)',
		icon: <Requirements size={12} color='text-neutral-500' />,
	},
	{ label: 'Diagramas', icon: <Modeling size={12} color='text-neutral-500' /> },
	{
		label: 'Implementación',
		icon: <Implementation size={12} color='text-neutral-500' />,
	},
	{ label: 'Aplicación', icon: <ArrowRight size={12} color='text-neutral-500' /> },
];

const ideaFullText =
	'Quiero crear un sistema de reservas de espacios de trabajo donde los usuarios puedan buscar espacios disponibles por fecha y hora, reservar salas de reuniones o escritorios, gestionar sus reservas activas y recibir notificaciones de confirmación.';

const discoveryCards = [
	['Alcance', 'Sistema web para gestionar reservas de espacios de trabajo.'],
	['Metas', 'Optimizar el proceso y mejorar la experiencia del usuario.'],
	['Actores', 'Usuario, Administrador y Recepcionista.'],
	['Objetivos', 'Gestionar reservas y disponibilidad en tiempo real.'],
];

const functionalities = [
	'Búsqueda de espacios disponibles',
	'Reserva de salas y escritorios',
	'Gestión de reservas activas',
	'Notificaciones y confirmaciones',
];

const earsCriteria = [
	'EL sistema DEBE permitir al usuario buscar espacios CUANDO seleccione fecha y hora.',
	'EL sistema DEBE confirmar la reserva CUANDO el usuario seleccione un espacio disponible.',
	'EL sistema DEBE enviar notificación CUANDO se confirme la reserva.',
];

const diagramNodes = [
	{ type: 'start', label: 'Inicio' },
	{ type: 'user', label: '[Usuario] Buscar espacio' },
	{ type: 'system', label: '[Sistema] Mostrar disponibles' },
	{ type: 'user', label: '[Usuario] Seleccionar espacio' },
	{ type: 'system', label: '[Sistema] Confirmar reserva' },
	{ type: 'end', label: 'Fin' },
];

const codeLines = [
	{
		indent: 0,
		tokens: [
			{ text: 'async function', color: 'text-primary-400' },
			{ text: ' createReservation', color: 'text-ai-400' },
			{ text: '(data) {', color: 'text-neutral-400' },
		],
	},
	{
		indent: 1,
		tokens: [
			{ text: 'const', color: 'text-primary-400' },
			{ text: ' space ', color: 'text-neutral-300' },
			{ text: '= ', color: 'text-neutral-500' },
			{ text: 'await', color: 'text-primary-400' },
			{ text: ' Space', color: 'text-neutral-300' },
			{ text: '.findById', color: 'text-ai-400' },
			{ text: '(data.spaceId);', color: 'text-neutral-400' },
		],
	},
	{
		indent: 1,
		tokens: [
			{ text: 'if', color: 'text-primary-400' },
			{ text: ' (!', color: 'text-neutral-400' },
			{ text: 'space.available', color: 'text-neutral-300' },
			{ text: ') {', color: 'text-neutral-400' },
		],
	},
	{
		indent: 2,
		tokens: [
			{ text: 'throw new', color: 'text-primary-400' },
			{ text: ' Error', color: 'text-neutral-300' },
			{ text: '(', color: 'text-neutral-400' },
			{ text: "'No disponible'", color: 'text-primary-400' },
			{ text: ');', color: 'text-neutral-400' },
		],
	},
	{ indent: 1, tokens: [{ text: '}', color: 'text-neutral-400' }] },
	{
		indent: 1,
		tokens: [
			{ text: 'return', color: 'text-primary-400' },
			{ text: ' await', color: 'text-primary-400' },
			{ text: ' Reservation', color: 'text-neutral-300' },
			{ text: '.create', color: 'text-ai-400' },
			{ text: '(data);', color: 'text-neutral-400' },
		],
	},
	{ indent: 0, tokens: [{ text: '}', color: 'text-neutral-400' }] },
];

const appReservations = [
	{ sala: 'Sala A - Piso 3', fecha: '15 Mar, 10:00', estado: 'Confirmada' },
	{ sala: 'Escritorio 12', fecha: '16 Mar, 14:00', estado: 'Pendiente' },
	{ sala: 'Sala B - Piso 2', fecha: '18 Mar, 09:00', estado: 'Confirmada' },
];

export function Hero({ onComenzar, onVerVideo }: HeroProps) {
	const router = useRouter();
	const user = useAuthStore((s) => s.user);
	const [activeStep, setActiveStep] = useState(0);
	const [typedText, setTypedText] = useState('');
	const [visibleDiagramNodes, setVisibleDiagramNodes] = useState(0);
	const [visibleCodeLines, setVisibleCodeLines] = useState(0);
	const [visibleAppRows, setVisibleAppRows] = useState(0);

	const goToStep = (step: number) => {
		setActiveStep(step);
		setTypedText('');
		setVisibleDiagramNodes(0);
		setVisibleCodeLines(0);
		setVisibleAppRows(0);
	};

	useEffect(() => {
		if (activeStep !== 0) return;
		let i = 0;
		const interval = setInterval(() => {
			if (i < ideaFullText.length) {
				setTypedText(ideaFullText.slice(0, i + 1));
				i++;
			} else {
				clearInterval(interval);
			}
		}, 20);
		return () => clearInterval(interval);
	}, [activeStep]);

	useEffect(() => {
		if (activeStep !== 4) return;
		let count = 0;
		const interval = setInterval(() => {
			count++;
			setVisibleDiagramNodes(count);
			if (count >= diagramNodes.length) clearInterval(interval);
		}, 200);
		return () => clearInterval(interval);
	}, [activeStep]);

	useEffect(() => {
		if (activeStep !== 5) return;
		let count = 0;
		const interval = setInterval(() => {
			count++;
			setVisibleCodeLines(count);
			if (count >= codeLines.length) clearInterval(interval);
		}, 250);
		return () => clearInterval(interval);
	}, [activeStep]);

	useEffect(() => {
		if (activeStep !== 6) return;
		let count = 0;
		const interval = setInterval(() => {
			count++;
			setVisibleAppRows(count);
			if (count >= appReservations.length) clearInterval(interval);
		}, 300);
		return () => clearInterval(interval);
	}, [activeStep]);

	return (
		<section className='relative overflow-hidden min-h-11/12'>
			<div className='absolute inset-0 bg-linear-to-br from-neutral-0 via-primary-50/30 to-neutral-0 pointer-events-none' />

			<div className='relative mx-auto grid max-w-7xl items-center gap-14 px-6 py-24 lg:grid-cols-2 lg:py-28'>
				<div>
					<div className='mb-6 inline-flex items-center gap-2 rounded-full border border-neutral-200 bg-neutral-0 px-4 py-2 text-xs font-medium uppercase tracking-widest text-neutral-500'>
						<Ai size={14} color='text-neutral-400' />
						Spec Driven Development
					</div>

					<h1 className='max-w-2xl text-5xl font-bold leading-[1.05] tracking-tight text-neutral-800 md:text-6xl'>
						Convierte tu idea
						<br />
						en software
						<br />
						de calidad, <span className='text-primary-600'>guiado por IA.</span>
					</h1>

					<p className='mt-7 max-w-xl text-lg leading-8 text-neutral-500'>
						KOSMO toma tu idea de negocio y la transforma paso a paso en especificaciones
						claras, diagramas y código listo para construir una aplicación real.
					</p>

					<div className='mt-8 flex flex-wrap gap-4'>
						{user ? (
							<button
								type='button'
								onClick={() => router.push('/proyecto')}
								className='btn btn-primary btn-lg'
							>
								Mis Proyectos
								<ArrowRight size={16} color='text-neutral-0' />
							</button>
						) : (
							<button
								type='button'
								onClick={onComenzar}
								className='btn btn-primary btn-lg'
							>
								Comenzar ahora
								<ArrowRight size={16} color='text-neutral-0' />
							</button>
						)}

						<button className='btn btn-secondary btn-lg' onClick={onVerVideo}>
							Ver cómo funciona
							<ArrowRight size={16} color='text-neutral-0' />
						</button>
					</div>
				</div>

				{/* MOCK APP */}
				<div className='relative'>
					<div className='relative overflow-hidden rounded-2xl border border-neutral-200 bg-neutral-0 shadow-2xl shadow-neutral-900/10'>
						{/* APP HEADER */}
						<div className='flex items-center justify-between border-b border-neutral-200 px-5 py-4'>
							<div className='flex items-center gap-3'>
								<Logo size={28} />
								<span className='text-sm font-semibold text-neutral-800'>KOSMO</span>
							</div>

							<div className='flex gap-2'>
								<div className='h-2 w-2 rounded-full bg-neutral-200' />
								<div className='h-2 w-2 rounded-full bg-neutral-200' />
								<div className='h-2 w-2 rounded-full bg-base-950' />
							</div>
						</div>

						<div className='grid grid-cols-[145px_1fr]'>
							{/* SIDEBAR */}
							<div className='border-r border-neutral-200 p-3'>
								<div className='mb-5 px-1 text-[10px] uppercase tracking-wider text-neutral-500'>
									Proyecto
								</div>

								{sidebarItems.map((item, index) => (
									<button
										key={item.label}
										onClick={() => goToStep(index)}
										className={`inline-flex items-center mb-1 w-full rounded-lg px-1 py-2 text-left text-xs transition-colors ${
											activeStep === index
												? 'bg-base-100'
												: 'text-neutral-500 hover:bg-neutral-50'
										}`}
									>
										<span className='mr-1 inline-flex items-center'>{item.icon}</span>
										{item.label}
									</button>
								))}
							</div>

							{/* CONTENT - FIXED HEIGHT */}
							<div className='h-85 overflow-y-auto p-5'>
								<div className='mb-5'>
									<p className='text-xs text-neutral-500'>Proyecto</p>
									<h3 className='mt-1 text-sm font-semibold text-neutral-800'>
										Sistema de Gestión de Reservas
									</h3>
								</div>

								{/* Step 0: Idea - Typing animation */}
								{activeStep === 0 && (
									<div>
										<div className='mb-4 flex items-center justify-between'>
											<div>
												<h3 className='text-sm font-semibold text-neutral-800'>Idea</h3>
												<p className='mt-1 text-[11px] text-neutral-500'>
													Describe tu idea de negocio.
												</p>
											</div>
											<div className='flex h-9 w-9 items-center justify-center rounded-full border border-neutral-200 bg-neutral-100'>
												<Folder size={16} color='text-neutral-500' />
											</div>
										</div>

										<div className='rounded-xl border border-neutral-200 bg-neutral-50 p-4'>
											<div className='text-[11px] leading-5 text-neutral-700'>
												<p>
													{typedText}
													<span className='mock-cursor inline-block h-4 w-0.5 bg-neutral-800' />
												</p>
											</div>
										</div>
									</div>
								)}

								{/* Step 1: Descubrimiento - Cards fade in sequentially */}
								{activeStep === 1 && (
									<div>
										<div className='mb-4 flex items-center justify-between'>
											<div>
												<h3 className='text-sm font-semibold text-neutral-800'>
													Descubrimiento
												</h3>
												<p className='mt-1 text-[11px] text-neutral-500'>
													La IA analiza y refina tu idea.
												</p>
											</div>
											<div className='flex h-9 w-9 items-center justify-center rounded-full border border-neutral-200 bg-neutral-100'>
												<Ai size={16} color='text-neutral-500' />
											</div>
										</div>

										<div className='grid grid-cols-2 gap-3'>
											{discoveryCards.map(([title, text], i) => (
												<div
													key={title}
													className='mock-animate-item rounded-xl border border-neutral-200 bg-neutral-50 p-3'
													style={{ animationDelay: `${i * 100}ms` }}
												>
													<p className='mb-2 text-[11px] font-medium text-neutral-700'>
														{title}
													</p>
													<p className='text-[10px] leading-4 text-neutral-500'>{text}</p>
												</div>
											))}
										</div>
									</div>
								)}

								{/* Step 2: Funcionalidades - Items slide in sequentially */}
								{activeStep === 2 && (
									<div>
										<div className='mb-4 flex items-center justify-between'>
											<div>
												<h3 className='text-sm font-semibold text-neutral-800'>
													Funcionalidades
												</h3>
												<p className='mt-1 text-[11px] text-neutral-500'>
													Se identifican las funcionalidades principales.
												</p>
											</div>
											<div className='flex h-9 w-9 items-center justify-center rounded-full border border-neutral-200 bg-neutral-100'>
												<Characteristics size={16} color='text-neutral-500' />
											</div>
										</div>

										<div className='space-y-2'>
											{functionalities.map((func, i) => (
												<div
													key={func}
													className='mock-animate-item flex items-center gap-3 rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-3'
													style={{ animationDelay: `${i * 100}ms` }}
												>
													<div className='flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary-50 text-[10px] font-medium text-primary-600'>
														{i + 1}
													</div>
													<span className='text-[11px] text-neutral-700'>{func}</span>
												</div>
											))}
										</div>
									</div>
								)}

								{/* Step 3: Criterios EARS - Fade in sequentially */}
								{activeStep === 3 && (
									<div>
										<div className='mb-4 flex items-center justify-between'>
											<div>
												<h3 className='text-sm font-semibold text-neutral-800'>
													Criterios EARS
												</h3>
												<p className='mt-1 text-[11px] text-neutral-500'>
													Criterios de aceptación formato EARS.
												</p>
											</div>
											<div className='flex h-9 w-9 items-center justify-center rounded-full border border-neutral-200 bg-neutral-100'>
												<Requirements size={16} color='text-neutral-500' />
											</div>
										</div>

										<div className='space-y-3'>
											{earsCriteria.map((criteria, i) => (
												<div
													key={i}
													className='mock-animate-item rounded-xl border border-neutral-200 bg-neutral-50 p-3'
													style={{ animationDelay: `${i * 150}ms` }}
												>
													<p className='text-[10px] font-medium text-neutral-400'>EARS</p>
													<p className='mt-1 text-[11px] leading-5 text-neutral-700'>
														{criteria.split(/(EL|DEBE|CUANDO)/).map((part, j) =>
															['EL', 'DEBE', 'CUANDO'].includes(part) ? (
																<span key={j} className='font-medium'>
																	{part}
																</span>
															) : (
																<span key={j}>{part}</span>
															),
														)}
													</p>
												</div>
											))}
										</div>
									</div>
								)}

								{/* Step 4: Diagramas - Nodes appear sequentially */}
								{activeStep === 4 && (
									<div>
										<div className='mb-4 flex items-center justify-between'>
											<div>
												<h3 className='text-sm font-semibold text-neutral-800'>
													Diagramas
												</h3>
												<p className='mt-1 text-[11px] text-neutral-500'>
													Diagrama de actividades del sistema.
												</p>
											</div>
											<div className='flex h-9 w-9 items-center justify-center rounded-full border border-neutral-200 bg-neutral-100'>
												<Modeling size={16} color='text-neutral-500' />
											</div>
										</div>

										<div className='rounded-xl border border-neutral-200 bg-neutral-50 p-4'>
											<div className='flex flex-col items-center space-y-2 text-[10px]'>
												{diagramNodes.map((node, i) => (
													<div key={i} className='flex flex-col items-center'>
														{i > 0 && visibleDiagramNodes > i && (
															<span
																className='mock-animate-item text-neutral-300'
																style={{ animationDelay: '0ms' }}
															>
																↓
															</span>
														)}
														{visibleDiagramNodes > i && (
															<div
																className={`mock-animate-item rounded-lg border px-4 py-2 ${
																	node.type === 'start' || node.type === 'end'
																		? 'rounded-full border-neutral-300 bg-neutral-0 font-medium text-neutral-600'
																		: node.type === 'user'
																			? 'border-primary-200 bg-primary-50 text-primary-700'
																			: 'border-ai-200 bg-ai-50 text-ai-700'
																}`}
																style={{ animationDelay: `${i * 200}ms` }}
															>
																{node.label}
															</div>
														)}
													</div>
												))}
											</div>
										</div>
									</div>
								)}

								{/* Step 5: Implementación - Code lines appear sequentially */}
								{activeStep === 5 && (
									<div>
										<div className='mb-4 flex items-center justify-between'>
											<div>
												<h3 className='text-sm font-semibold text-neutral-800'>
													Implementación
												</h3>
												<p className='mt-1 text-[11px] text-neutral-500'>
													Se genera el código por funcionalidad.
												</p>
											</div>
											<div className='flex h-9 w-9 items-center justify-center rounded-full border border-neutral-200 bg-neutral-100'>
												<Implementation size={16} color='text-neutral-500' />
											</div>
										</div>

										<div className='rounded-xl border border-neutral-200 bg-neutral-900 p-4'>
											<div className='space-y-1.5 font-mono text-[10px] leading-4'>
												{codeLines.map(
													(line, i) =>
														visibleCodeLines > i && (
															<p
																key={i}
																className='mock-animate-code'
																style={{
																	paddingLeft: `${line.indent * 12}px`,
																	animationDelay: `${i * 50}ms`,
																}}
															>
																{line.tokens.map((token, j) => (
																	<span key={j} className={token.color}>
																		{token.text}
																	</span>
																))}
															</p>
														),
												)}
												{visibleCodeLines >= codeLines.length && (
													<p className='pl-0'>
														<span className='mock-cursor inline-block h-3.5 w-1.5 bg-primary-400' />
													</p>
												)}
											</div>
										</div>
									</div>
								)}

								{/* Step 6: Aplicación - Rows slide in sequentially */}
								{activeStep === 6 && (
									<div>
										<div className='mb-4 flex items-center justify-between'>
											<div>
												<h3 className='text-sm font-semibold text-neutral-800'>
													Aplicación
												</h3>
												<p className='mt-1 text-[11px] text-neutral-500'>
													App lista para usar.
												</p>
											</div>
											<div className='flex h-9 w-9 items-center justify-center rounded-full border border-neutral-200 bg-neutral-100'>
												<ArrowRight size={16} color='text-neutral-500' />
											</div>
										</div>

										<div className='rounded-xl border border-neutral-200 bg-neutral-50 p-4'>
											<div className='mb-3 flex items-center justify-between'>
												<p className='text-[11px] font-semibold text-neutral-700'>
													Mis Reservas
												</p>
												<div className='rounded-md bg-primary-500 px-2 py-0.5 text-[9px] font-medium text-neutral-0'>
													+ Nueva
												</div>
											</div>
											<div className='space-y-2'>
												{appReservations.map(
													(r, i) =>
														visibleAppRows > i && (
															<div
																key={r.sala}
																className='mock-animate-row flex items-center justify-between rounded-lg border border-neutral-200 bg-neutral-0 px-3 py-2'
																style={{ animationDelay: `${i * 150}ms` }}
															>
																<div>
																	<p className='text-[10px] font-medium text-neutral-700'>
																		{r.sala}
																	</p>
																	<p className='text-[9px] text-neutral-400'>{r.fecha}</p>
																</div>
																<span
																	className={`rounded-full px-2 py-0.5 text-[9px] font-medium ${
																		r.estado === 'Confirmada'
																			? 'bg-primary-50 text-primary-600'
																			: 'bg-neutral-100 text-neutral-500'
																	}`}
																>
																	{r.estado}
																</span>
															</div>
														),
												)}
											</div>
										</div>
									</div>
								)}
							</div>
						</div>

						{/* BOTÓN SIGUIENTE */}
						<div className='border-t border-neutral-200 px-5 py-3'>
							{activeStep < 6 && (
								<button
									onClick={() => goToStep(activeStep + 1)}
									className='btn btn-primary btn-sm'
								>
									Siguiente: {sidebarItems[activeStep + 1].label}
									<ArrowRight size={14} color='text-neutral-0' />
								</button>
							)}
							{activeStep === 6 && (
								<button
									onClick={user ? () => router.push('/proyecto') : onComenzar}
									className='btn btn-primary btn-sm'
								>
									{user ? 'Mis Proyectos' : 'Comenzar ahora'}
									<ArrowRight size={14} color='text-neutral-0' />
								</button>
							)}
						</div>
					</div>
				</div>
			</div>
		</section>
	);
}
