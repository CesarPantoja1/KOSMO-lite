'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import { formatApiError } from '@/shared/api';
import {
	Ai,
	ArrowLeft,
	ArrowRight,
	CursorClickFill,
	Loading,
	ModalConfirm,
	Requirements,
	toast,
} from '@/shared/ui';

import { useCharacteristicStore } from '@/entities/characteristic';
import { useProjectStore } from '@/entities/project';
import { useRequirementsStore } from '@/entities/requirements';

import { useAppStore, useUnsavedChanges } from '@/features/app-state';
import { AsideCharacteristic } from '@/features/aside-characteristic';
import { PanelAsistenteRequisito } from '@/features/chatbot';
import { MarkdownEditor, type SaveStatus } from '@/features/markdown-editor';

const generatingRequirementsMessages = [
	'Analizando característica...',
	'Generando requisitos EARS...',
	'Finalizando generación de requisitos...',
];

const RequirementsPage = () => {
	const router = useRouter();

	// Características estado
	const characteristics = useCharacteristicStore((s) => s.currentCharacteristics);
	const selectedId = useCharacteristicStore((s) => s.selectedId);
	const setSelectedId = useCharacteristicStore((s) => s.setSelectedId);
	const getCharacteristics = useCharacteristicStore((s) => s.getCharacteristics);
	const [isGenerating, setIsGenerating] = useState(false);
	const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

	// Requisitos estado
	const [isLoadingRequirements, setIsLoadingRequirements] = useState(false);
	const hasRequirements = useRequirementsStore((s) => s.hasRequirements);
	const currentRequirements = useRequirementsStore((s) => s.currentRequirements);
	const getRequirements = useRequirementsStore((s) => s.getRequirements);
	const saveRequirements = useRequirementsStore((s) => s.saveRequirements);
	const generateRequirements = useRequirementsStore((s) => s.generateRequirements);
	const deleteRequirementsStore = useRequirementsStore((s) => s.deleteRequirements);

	const [markdown, setMarkdown] = useState('');
	const [savedContent, setSavedContent] = useState('');
	const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');

	// App estado
	const pendingNavigationPath = useAppStore((s) => s.pendingNavigationPath);
	const setPendingNavigationPath = useAppStore((s) => s.setPendingNavigationPath);
	const setHasUnsavedChanges = useAppStore((s) => s.setHasUnsavedChanges);
	const isEditorMaximized = useAppStore((s) => s.isEditorMaximized);
	const setEditorMaximized = useAppStore((s) => s.setEditorMaximized);
	const currentProject = useProjectStore((s) => s.currentProject);
	const currentProjectId = currentProject?.id;

	// Otros estados
	const [isChatbotOpen, setIsChatbotOpen] = useState(false);
	const [isAsideExpanded, setIsAsideExpanded] = useState(true);
	const selectedCharacteristic = characteristics.find((c) => c.id === selectedId) ?? null;
	const hasUnsavedChanges = markdown !== savedContent;
	const [pendingCharSwitch, setPendingCharSwitch] = useState<string | null>(null);

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

	useEffect(() => {
		if (!hasUnsavedChanges && pendingCharSwitch) {
			const timer = setTimeout(() => setPendingCharSwitch(null), 0);
			return () => clearTimeout(timer);
		}
	}, [hasUnsavedChanges, pendingCharSwitch]);

	useEffect(() => {
		if (!selectedId || !currentProject) return;

		let cancelled = false;

		const load = async () => {
			const storedContent = currentRequirements[selectedId];
			if (storedContent) {
				setMarkdown(storedContent);
				setSavedContent(storedContent);
				return;
			}

			setIsLoadingRequirements(true);
			try {
				const content = await getRequirements(currentProject.id, selectedId);
				if (cancelled) return;
				setMarkdown(content);
				setSavedContent(content);
			} catch (err) {
				if (!cancelled && (err as { status?: number }).status !== 404) {
					toast.error(formatApiError(err, 'Error al cargar los requisitos'));
				}
			} finally {
				if (!cancelled) setIsLoadingRequirements(false);
			}
		};

		load();

		return () => {
			cancelled = true;
		};
	}, [selectedId, currentProject, currentRequirements, getRequirements]);

	const handleSelectCharacteristic = (id: string) => {
		if (id === selectedId) return;
		if (hasUnsavedChanges) {
			setPendingCharSwitch(id);
		} else {
			applySelected(id);
		}
	};

	const applySelected = (id: string) => {
		// Reset editor state before switching so the new editor always mounts clean
		setMarkdown('');
		setSavedContent('');
		setSaveStatus('idle');
		setSelectedId(id);
		setPendingCharSwitch(null);
		if (!hasRequirements[id]) {
			setIsChatbotOpen(false);
		}
	};

	const handleConfirmSwitch = () => {
		if (pendingCharSwitch) applySelected(pendingCharSwitch);
	};

	const handleCancelSwitch = () => {
		setPendingCharSwitch(null);
	};

	const handleGenerate = async () => {
		if (!selectedCharacteristic || !currentProject) return;
		setIsGenerating(true);
		try {
			const content = await generateRequirements(
				currentProject.id,
				selectedCharacteristic.id,
			);
			setMarkdown(content);
			setSavedContent(content);
		} catch (err) {
			toast.error(formatApiError(err, 'Error al generar los requisitos'));
		} finally {
			setIsGenerating(false);
		}
	};

	const handleDeleteRequirements = async () => {
		if (!confirmDeleteId || !currentProject) return;
		const featureId = confirmDeleteId;
		setConfirmDeleteId(null);
		try {
			await deleteRequirementsStore(currentProject.id, featureId);

			setMarkdown('');
			setSavedContent('');
			toast.success('Requisitos eliminados');
		} catch (err) {
			toast.error(formatApiError(err, 'Error al eliminar los requisitos'));
		}
	};

	const handleDeleteClick = (id: string) => {
		setConfirmDeleteId(id);
	};

	const handleSave = useCallback(async () => {
		if (!selectedId || !currentProject) return;

		setSaveStatus('saving');
		try {
			await saveRequirements(currentProject.id, selectedId, markdown);
			setSavedContent(markdown);
			setSaveStatus('saved');
		} catch (err) {
			setSaveStatus('error');
			toast.error(formatApiError(err, 'Error al guardar los requisitos'));
		}
	}, [currentProject, selectedId, markdown, saveRequirements]);

	const handleNextLink = (href: string) => (e: React.MouseEvent) => {
		const { hasUnsavedChanges: unsaved, setPendingNavigationPath: setPath } =
			useAppStore.getState();
		if (unsaved) {
			e.preventDefault();
			setPath(href);
		}
	};

	const confirmLeave = useCallback(() => {
		const path = pendingNavigationPath;
		setPendingNavigationPath(null);
		setHasUnsavedChanges(false);
		if (!path) return;
		router.push(path);
	}, [pendingNavigationPath, setPendingNavigationPath, setHasUnsavedChanges, router]);

	const cancelLeave = useCallback(() => {
		setPendingNavigationPath(null);
	}, [setPendingNavigationPath]);

	useUnsavedChanges({
		isDirty: hasUnsavedChanges,
		onAutosave: handleSave,
	});

	const hasCharacteristics = characteristics.length > 0;

	return (
		<>
			{pendingCharSwitch && (
				<ModalConfirm onCancel={handleCancelSwitch} onConfirm={handleConfirmSwitch} />
			)}

			{pendingNavigationPath && (
				<ModalConfirm onCancel={cancelLeave} onConfirm={confirmLeave} />
			)}

			{confirmDeleteId && (
				<ModalConfirm
					title='Eliminar requisitos'
					description='Esta acción no se puede deshacer. Se eliminarán los criterios de aceptación de esta funcionalidad.'
					cancelText='Cancelar'
					confirmText='Eliminar'
					onCancel={() => setConfirmDeleteId(null)}
					onConfirm={handleDeleteRequirements}
				/>
			)}

			{isGenerating && (
				<Loading
					title='Generando criterios de aceptación'
					description='Estructurando la funcionalidad seleccionada bajo el estándar EARS. Esto tomará unos segundos.'
					messages={generatingRequirementsMessages}
				/>
			)}

			<div className={`page-container ${isEditorMaximized ? 'px-8' : 'px-0'}`}>
				<div className='page-header'>
					<div className='flex items-start justify-between gap-4'>
						<div className='flex flex-col gap-1'>
							<h1 className='text-neutral-800 text-lg md:text-xl font-bold'>
								Criterios de aceptación
							</h1>
							<p className='text-neutral-500 text-sm md:text-base'>
								Estructura los requisitos de cada funcionalidad bajo el estándar EARS.
							</p>
						</div>

						{hasCharacteristics && !isEditorMaximized && (
							<div className='flex items-center gap-3 shrink-0'>
								{hasRequirements[selectedId ? selectedId : ''] && (
									<button
										onClick={() => {
											setIsChatbotOpen(true);
											setIsAsideExpanded(false);
										}}
										className='btn btn-ai disabled:opacity-50 disabled:cursor-not-allowed'
									>
										<Ai size={18} color='' />
										Mejorar con IA
									</button>
								)}
								<Link
									href='codigo'
									onClick={handleNextLink('codigo')}
									className='btn btn-primary'
								>
									Continuar
									<ArrowRight color='' size={18} />
								</Link>
							</div>
						)}
					</div>

					{!hasCharacteristics ? (
						<div className='w-full my-auto min-h-105 flex flex-col items-center justify-center'>
							<div className='flex flex-col items-center gap-5 text-center px-6 max-w-lg'>
								<div className='flex h-20 w-20 items-center justify-center rounded-2xl bg-neutral-100'>
									<Ai color='text-neutral-400' size={48} />
								</div>
								<div className='flex flex-col gap-2'>
									<h3 className='text-xl font-semibold text-neutral-800'>
										No hay funcionalidades definidas
									</h3>
									<p className='text-neutral-500 text-base'>
										Primero debes generar las funcionalidades del proyecto para poder
										definir sus criterios de aceptación.
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
								onDeleteCharacteristic={handleDeleteClick}
								hasIcon={hasRequirements}
								icon={Requirements}
								isExpanded={isAsideExpanded}
								onToggleExpand={setIsAsideExpanded}
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
												Elige una funcionalidad del listado lateral para ver o generar sus
												criterios de aceptación.
											</p>
										</div>
									</div>
								)}

								{selectedCharacteristic && isLoadingRequirements && (
									<div className='flex flex-1 items-center justify-center gap-3'>
										<div className='h-5 w-5 animate-spin rounded-full border-2 border-neutral-200 border-t-primary-500' />
										<span className='text-neutral-500 text-sm'>
											Cargando criterios...
										</span>
									</div>
								)}

								{selectedCharacteristic &&
									!isLoadingRequirements &&
									hasRequirements[selectedCharacteristic.id] &&
									markdown && (
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
											<div className='flex-1 min-h-0'>
												<MarkdownEditor
													key={selectedId}
													markdown={markdown}
													onChange={setMarkdown}
													isMaximized={isEditorMaximized}
													onMaximize={() => setEditorMaximized(true)}
													onMinimize={() => setEditorMaximized(false)}
													saveStatus={saveStatus}
												/>
											</div>
										</div>
									)}

								{selectedCharacteristic &&
									!isLoadingRequirements &&
									!hasRequirements[selectedCharacteristic.id] && (
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

											<div className='flex flex-col my-auto items-center gap-5 px-12'>
												<div className='flex h-20 w-20 items-center justify-center rounded-2xl bg-ai-50'>
													<Ai color='text-ai-500' size={48} />
												</div>
												<div className='flex flex-col items-center gap-2 text-center max-w-md'>
													<h3 className='text-neutral-800 text-lg font-semibold'>
														Aún no hay criterios generados
													</h3>
													<p className='text-neutral-500 text-sm'>
														Esta funcionalidad aún no tiene criterios de aceptación. El
														asistente los estructurará automáticamente bajo el formato
														EARS.
													</p>
												</div>
												<button onClick={handleGenerate} className='btn btn-ai'>
													<Ai color='' size={18} />
													Generar criterios
												</button>
											</div>
										</div>
									)}
							</div>
						</div>
					)}
				</div>

				{isChatbotOpen && (
					<PanelAsistenteRequisito
						featureId={selectedId}
						projectId={currentProject?.id ?? null}
						onClose={() => {
							setIsChatbotOpen(false);
							setIsAsideExpanded(true);
						}}
					/>
				)}
			</div>
		</>
	);
};

export { RequirementsPage };
