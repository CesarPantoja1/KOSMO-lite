'use client';

import Link from 'next/link';
import { useEffect } from 'react';

import { useCharacteristicStore } from '@/entities/characteristic';
import { useImplementationStore } from '@/entities/implementation';
import { useModelingStore } from '@/entities/modeling';
import { useProjectStore } from '@/entities/project';
import { useProjectGithubRepo } from '@/features/github-sync';
import { formatApiError } from '@/shared/api';
import {
	Ai,
	ArrowLeft,
	CursorClickFill,
	Implementation,
	Load,
	Loading,
	SuccessCheckIcon,
	toast,
	WarningIcon,
} from '@/shared/ui';
import { AsideCharacteristic } from '@/widgets';

const ImplementationPage = () => {
	const characteristics = useCharacteristicStore((s) => s.currentCharacteristics);
	const selectedId = useCharacteristicStore((s) => s.selectedId);
	const setSelectedId = useCharacteristicStore((s) => s.setSelectedId);
	const getCharacteristics = useCharacteristicStore((s) => s.getCharacteristics);
	const currentProject = useProjectStore((s) => s.currentProject);
	const currentProjectId = currentProject?.id;

	const {
		viewState: githubViewState,
		status: githubStatus,
		loading: githubLoading,
		error: githubError,
		createRepo: retryCreateRepo,
	} = useProjectGithubRepo(currentProjectId ?? null);

	const status = useImplementationStore((s) => s.status);
	const progress = useImplementationStore((s) => s.progress);
	const errorMessage = useImplementationStore((s) => s.errorMessage);
	const implementations = useImplementationStore((s) => s.implementations);
	const requiresReviewByFeature = useImplementationStore((s) => s.requiresReviewByFeature);
	const startGeneration = useImplementationStore((s) => s.startGeneration);
	const loadImplementation = useImplementationStore((s) => s.loadImplementation);

	const hasDiagram = useModelingStore((s) => s.hasDiagram);

	const selectedCharacteristic = characteristics.find((c) => c.id === selectedId) ?? null;
	const hasCharacteristics = characteristics.length > 0;
	const hasAnyImplementation = Object.values(implementations).some(Boolean);
	const currentHasImpl = selectedId ? !!implementations[selectedId] : false;
	const currentRequiresReview = selectedId
		? !!requiresReviewByFeature[selectedId] || status === 'requires_review'
		: false;
	const selectedHasDiagram = selectedId ? !!hasDiagram[selectedId] : false;
	const isGenerating = status === 'generating';

	useEffect(() => {
		if (!currentProjectId) return;
		let cancelled = false;

		void getCharacteristics(currentProjectId)
			.then((features) => {
				if (cancelled) return;
				const currentSelection = useCharacteristicStore.getState().selectedId;
				if (!features.some((feature) => feature.id === currentSelection)) {
					setSelectedId(features[0]?.id ?? null);
				}
			})
			.catch((error: unknown) => {
				if (!cancelled)
					toast.error(formatApiError(error, 'Error al cargar las funcionalidades'));
			});

		return () => {
			cancelled = true;
		};
	}, [currentProjectId, getCharacteristics, setSelectedId]);

	// La verdad de la implementación vive en el backend: al abrir el proyecto o
	// cambiar de característica se hidrata el estado desde el servidor.
	useEffect(() => {
		if (!selectedCharacteristic) return;
		loadImplementation(
			selectedCharacteristic.id,
			selectedCharacteristic.title,
			selectedCharacteristic.display_id,
		);
	}, [selectedCharacteristic, loadImplementation]);

	const handleSelectCharacteristic = (id: string) => {
		setSelectedId(id);
	};

	const handleGenerate = async () => {
		if (!selectedId || !selectedCharacteristic) return;
		await startGeneration(
			selectedId,
			selectedCharacteristic.title,
			selectedCharacteristic.display_id,
		);
	};

	const renderGenerateAction = (buttonLabel: string) => {
		if (githubViewState === 'syncing') {
			return (
				<div className='flex flex-col items-center gap-2'>
					<button disabled className='btn btn-secondary cursor-not-allowed opacity-80'>
						<span className='inline-flex animate-spin text-primary-500'>
							<Load size={16} color='text-current' />
						</span>
						Preparando repositorio en GitHub...
					</button>
					<p className='text-xs text-neutral-400'>
						El repositorio se está inicializando en segundo plano. Estará listo en un momento.
					</p>
				</div>
			);
		}

		if (githubViewState === 'failed') {
			return (
				<div className='flex flex-col items-center gap-3 p-4 rounded-xl border border-error-200 bg-error-50 max-w-md text-center'>
					<div className='flex items-center gap-2 text-error-700 font-semibold text-sm'>
						<WarningIcon size={18} color='text-error-600' />
						Error al preparar repositorio de GitHub
					</div>
					<p className='text-xs text-error-600'>
						{githubStatus?.error_message ??
							githubError ??
							'No se pudo crear el repositorio en GitHub. Se requiere tener el repositorio listo antes de implementar.'}
					</p>
					<button
						type='button'
						onClick={async () => {
							const repoName =
								githubStatus?.suggested_repo_name || `kosmo-${currentProject?.slug || 'app'}`;
							try {
								await retryCreateRepo({ repo_name: repoName, is_public: true });
								toast.success('Repositorio creado exitosamente en GitHub');
							} catch {
								toast.error('No se pudo crear el repositorio. Verifica tu conexión.');
							}
						}}
						disabled={githubLoading}
						className='btn btn-primary btn-sm'
					>
						{githubLoading ? 'Reintentando...' : 'Reintentar creación de repositorio'}
					</button>
				</div>
			);
		}

		if (githubViewState === 'not-linked') {
			return (
				<div className='flex flex-col items-center gap-2 p-4 rounded-xl border border-warning-200 bg-warning-50 max-w-md text-center'>
					<p className='text-xs text-warning-700 font-medium'>
						Debes conectar tu cuenta de GitHub antes de generar la implementación.
					</p>
					<Link href='/perfil' className='btn btn-secondary btn-sm'>
						Conectar GitHub en Perfil
					</Link>
				</div>
			);
		}

		return (
			<button onClick={handleGenerate} className='btn btn-ai'>
				<Ai color='' size={18} />
				{buttonLabel}
			</button>
		);
	};

	return (
		<>
			{isGenerating && (
				<Loading
					title='Generando implementación'
					description='Transformando requisitos y modelo en código funcional.'
					messages={progress}
				/>
			)}

			{status === 'failed' && errorMessage && (
				<div className='mb-4 flex items-center gap-3 rounded-lg border border-warning-200 bg-warning-50 px-4 py-3'>
					<WarningIcon size={20} color='text-warning-600' />
					<p className='text-sm text-warning-700'>{errorMessage}</p>
				</div>
			)}

			<section className='page-container px-0'>
				<div className='page-header'>
					<div className='flex items-start justify-between gap-4'>
						<div className='flex flex-col gap-1'>
							<h1 className='text-neutral-800 text-lg md:text-xl font-bold'>
								Implementación
							</h1>
							<p className='text-neutral-500 text-sm md:text-base'>
								Tu aplicación está lista. KOSMO ha transformado todo lo que definiste en
								los pasos anteriores en una estructura funcional para continuar con su
								desarrollo.
							</p>
						</div>

						{hasCharacteristics && hasAnyImplementation && (
							<div className='flex items-center gap-3 shrink-0'>
								<Link href='/proyecto/codigo/resumen' className='btn btn-primary'>
									Ver resumen
								</Link>
							</div>
						)}
					</div>

					{!hasCharacteristics ? (
						<div className='w-full my-auto min-h-105 flex flex-col items-center justify-center'>
							<div className='flex flex-col items-center gap-5 text-center px-6 max-w-lg'>
								<div className='flex h-20 w-20 items-center justify-center rounded-2xl bg-neutral-100'>
									<Implementation color='text-neutral-400' size={48} />
								</div>
								<div className='flex flex-col gap-2'>
									<h3 className='text-xl font-semibold text-neutral-800'>
										No hay funcionalidades definidas
									</h3>
									<p className='text-neutral-500 text-base'>
										Primero debes generar las funcionalidades del proyecto para poder
										generar su implementación.
									</p>
								</div>
								<Link href='/proyecto/caracteristicas' className='btn btn-secondary'>
									<ArrowLeft color='' size={18} />
									Ir a Funcionalidades
								</Link>
							</div>
						</div>
					) : (
						<div className='flex gap-1 flex-1 min-h-0'>
							<AsideCharacteristic
								characteristics={characteristics}
								selectedId={selectedId}
								onSelectCharacteristic={handleSelectCharacteristic}
								hasIcon={implementations}
								warningByFeature={requiresReviewByFeature}
								icon={Implementation}
							/>

							<div className='relative flex-1 flex flex-col pl-3 pt-2 bg-neutral-50 border-l border-neutral-200 min-h-0 overflow-hidden'>
								{!selectedCharacteristic && (
									<div className='flex flex-col items-center justify-center h-full gap-4'>
										<div className='flex h-16 w-16 items-center justify-center rounded-2xl bg-neutral-100'>
											<CursorClickFill color='text-neutral-400' size={40} />
										</div>
										<div className='flex flex-col items-center gap-2 text-center max-w-sm'>
											<h3 className='text-neutral-700 text-lg font-semibold'>
												Selecciona una funcionalidad
											</h3>
											<p className='text-neutral-400 text-sm'>
												Elige una funcionalidad del listado lateral para generar su
												implementación.
											</p>
										</div>
									</div>
								)}

								{selectedCharacteristic && !currentHasImpl && (
									<div className='flex flex-col flex-1 min-h-0 gap-3'>
										<div className='flex flex-col gap-1 px-2'>
											<div className='flex items-center gap-2'>
												<span className='text-base font-bold text-neutral-500'>
													{selectedCharacteristic.display_id}
												</span>
												<span className='text-base font-semibold text-neutral-800'>
													{selectedCharacteristic.title}
												</span>
											</div>
											<p className='text-neutral-500 text-sm'>
												{selectedCharacteristic.description}
											</p>
										</div>

										{!selectedHasDiagram ? (
											<div className='flex flex-col my-auto items-center gap-5 px-12'>
												<div className='flex h-20 w-20 items-center justify-center rounded-2xl bg-warning-50'>
													<Ai color='text-warning-500' size={48} />
												</div>
												<div className='flex flex-col items-center gap-2 text-center max-w-md'>
													<h3 className='text-neutral-800 text-lg font-semibold'>
														Falta diagrama de actividad
													</h3>
													<p className='text-neutral-500 text-sm'>
														Esta funcionalidad no tiene diagrama de actividad generado.
														Genera el diagrama antes de continuar con la implementación.
													</p>
												</div>
												<Link href='/proyecto/modelo' className='btn btn-secondary'>
													<ArrowLeft color='' size={18} />
													Ir a diagramas
												</Link>
											</div>
										) : (
											<div className='flex flex-col my-auto items-center gap-5 px-12'>
												<div className='flex h-20 w-20 items-center justify-center rounded-2xl bg-ai-50'>
													<Ai color='text-ai-500' size={48} />
												</div>
												<div className='flex flex-col items-center gap-2 text-center max-w-md'>
													<h3 className='text-neutral-800 text-lg font-semibold'>
														Aún no hay implementación generada
													</h3>
													<p className='text-neutral-500 text-sm'>
														Esta funcionalidad aún no tiene código generado. El asistente
														creará la estructura de implementación automáticamente.
													</p>
												</div>
												{renderGenerateAction('Generar implementación')}
											</div>
										)}
									</div>
								)}

								{selectedCharacteristic && currentHasImpl && (
									<div className='flex flex-col flex-1 min-h-0 gap-3'>
										<div className='flex flex-col gap-1 px-2'>
											<div className='flex items-center gap-2 flex-wrap'>
												<span className='text-base font-bold text-neutral-500'>
													{selectedCharacteristic.display_id}
												</span>
												<span className='text-base font-semibold text-neutral-800'>
													{selectedCharacteristic.title}
												</span>
												{currentRequiresReview && (
													<span className='rounded-full bg-warning-100 text-warning-800 border border-warning-200 px-2.5 py-0.5 text-xs font-semibold'>
														Requiere actualización
													</span>
												)}
											</div>
											<p className='text-neutral-500 text-sm'>
												{selectedCharacteristic.description}
											</p>
										</div>

										{currentRequiresReview ? (
											<div className='flex flex-col my-auto items-center gap-5 px-12'>
												<div className='flex h-20 w-20 items-center justify-center rounded-2xl bg-warning-50'>
													<WarningIcon size={44} color='text-warning-600' />
												</div>
												<div className='flex flex-col items-center gap-2 text-center max-w-lg'>
													<h3 className='text-neutral-800 text-lg font-semibold'>
														Implementación desactualizada
													</h3>
													<p className='text-neutral-600 text-sm'>
														Las especificaciones de esta funcionalidad (Descubrimiento, Requisitos o Modelo) cambiaron recientemente. El código generado previamente ya no coincide con los nuevos requisitos.
													</p>
													<p className='text-neutral-500 text-xs mt-1'>
														Haz clic en «Regenerar implementación» para actualizar el código automáticamente con las nuevas reglas.
													</p>
												</div>
												<div className='flex items-center gap-3 mt-2 flex-wrap justify-center'>
													{renderGenerateAction('Regenerar implementación')}
													<Link href='/proyecto/codigo/resumen' className='btn btn-secondary'>
														Ver código actual
													</Link>
												</div>
											</div>
										) : (
											<div className='flex flex-col my-auto items-center gap-5 px-12'>
												<div className='flex h-20 w-20 items-center justify-center rounded-2xl bg-success-50'>
													<SuccessCheckIcon size={40} color='text-success-600' />
												</div>
												<div className='flex flex-col items-center gap-2 text-center max-w-md'>
													<h3 className='text-neutral-800 text-lg font-semibold'>
														Implementación generada
													</h3>
													<p className='text-neutral-500 text-sm'>
														La estructura de esta funcionalidad ha sido generada
														exitosamente. Puedes ver el resumen completo en el botón
														&quot;Ver resumen&quot;.
													</p>
												</div>
											</div>
										)}
									</div>
								)}
							</div>
						</div>
					)}
				</div>
			</section>
		</>
	);
};

export { ImplementationPage };
