import { useState, type ElementType } from 'react';
import type { CharacteristicResponse } from '@/entities/characteristic';
import {
	CloseMarkdownContent,
	OpenMarkdownContent,
	Trash,
	WarningIcon,
} from '@/shared/ui';

type AsideCharacteristicProps = {
	title?: string;
	characteristics: CharacteristicResponse[];
	selectedId: string | null;
	onSelectCharacteristic: (id: string) => void;
	onDeleteCharacteristic?: (id: string) => void;
	hasIcon: Record<string, boolean>;
	warningByFeature?: Record<string, boolean>;
	defaultExpanded?: boolean;
	isExpanded?: boolean;
	onToggleExpand?: (expanded: boolean) => void;
	icon: ElementType<{ size?: number; color: string }>;
};

const AsideCharacteristic = ({
	title = 'Funcionalidades',
	characteristics,
	selectedId,
	onSelectCharacteristic,
	onDeleteCharacteristic,
	hasIcon,
	warningByFeature,
	defaultExpanded = true,
	isExpanded: isExpandedProp,
	onToggleExpand,
	icon: Icon,
}: AsideCharacteristicProps) => {
	const [isExpandedInternal, setIsExpandedInternal] = useState(defaultExpanded);
	const isExpanded = isExpandedProp ?? isExpandedInternal;

	const toggleExpand = (value: boolean) => {
		if (onToggleExpand) {
			onToggleExpand(value);
		} else {
			setIsExpandedInternal(value);
		}
	};

	return (
		<aside
			className='bg-neutral-50 border-r border-neutral-200 flex flex-col shrink-0 transition-all duration-300'
			style={{ width: isExpanded ? 288 : 52 }}
		>
			{isExpanded ? (
				<>
					<div className='flex items-center justify-between px-4 py-3 border-b border-neutral-200 shrink-0'>
						<h3 className='text-xs font-semibold uppercase tracking-wider text-neutral-500'>
							{title}
						</h3>
						<button
							onClick={() => toggleExpand(false)}
							className='cursor-pointer p-1 text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100 rounded transition-colors'
						>
							<CloseMarkdownContent size={18} />
						</button>
					</div>

					<div className='flex-1 flex flex-col gap-0.5 overflow-y-auto py-2 px-2'>
						{characteristics.length === 0 && (
							<p className='text-neutral-400 text-xs px-3 py-2'>
								No hay funcionalidades disponibles.
							</p>
						)}
						{characteristics.map((c) => {
							const isSelected = c.id === selectedId;
							return (
								<button
									key={c.id}
									onClick={() => onSelectCharacteristic(c.id)}
									className={`group w-full px-3 py-2.5 flex justify-start items-start gap-2.5 text-left cursor-pointer transition-colors rounded-md ${
										isSelected ? 'bg-neutral-200/75' : 'hover:bg-neutral-50'
									}`}
								>
									<span
										className={`text-xs font-medium mt-0.5 shrink-0 ${
											isSelected ? 'text-base-950' : 'text-neutral-500'
										}`}
									>
										{c.display_id}
									</span>
									<p
										className={`flex-1 text-xs font-medium leading-snug pt-0.5 ${
											isSelected ? 'text-base-950 font-semibold!' : 'text-neutral-500'
										}`}
									>
										{c.title}
									</p>
									{hasIcon[c.id] && (
										<div
											className='relative shrink-0 mt-0.5 w-4 h-4'
											title={
												warningByFeature?.[c.id]
													? 'Requiere actualización por cambios en especificaciones'
													: undefined
											}
										>
											<span className='absolute inset-0 opacity-100 group-hover:opacity-0 transition-opacity flex items-center justify-center'>
												{warningByFeature?.[c.id] ? (
													<WarningIcon size={16} color='text-warning-500' />
												) : (
													<Icon
														size={16}
														color={isSelected ? 'text-neutral-600' : 'text-neutral-400'}
													/>
												)}
											</span>
											{onDeleteCharacteristic && (
												<span
													onClick={(e) => {
														e.stopPropagation();
														onDeleteCharacteristic(c.id);
													}}
													className='absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center cursor-pointer hover:bg-error-50 rounded'
													title='Eliminar'
												>
													<Trash size={15} color='text-error-500' />
												</span>
											)}
										</div>
									)}
								</button>
							);
						})}
					</div>
				</>
			) : (
				<>
					<div className='flex justify-center py-3 border-b border-neutral-200 shrink-0'>
						<button
							onClick={() => toggleExpand(true)}
							className='cursor-pointer p-1 text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100 rounded transition-colors'
						>
							<OpenMarkdownContent size={18} />
						</button>
					</div>

					<div className='flex-1 flex flex-col gap-0.5 overflow-y-auto py-2 px-1'>
						{characteristics.map((c) => {
							const isSelected = c.id === selectedId;
							return (
								<button
									key={c.id}
									onClick={() => onSelectCharacteristic(c.id)}
									title={c.title}
									className={`group w-full py-2 flex flex-col items-center gap-1 cursor-pointer transition-colors rounded-md ${
										isSelected ? 'bg-neutral-200' : 'hover:bg-neutral-100'
									}`}
								>
									<span
										className={`text-[10px] font-bold ${
											isSelected ? 'text-neutral-500' : 'text-neutral-400'
										}`}
									>
										{c.display_id}
									</span>
									{hasIcon[c.id] && (
										<div
											className='relative shrink-0 w-3.5 h-3.5'
											title={
												warningByFeature?.[c.id]
													? 'Requiere actualización por cambios en especificaciones'
													: undefined
											}
										>
											<span className='absolute inset-0 opacity-100 group-hover:opacity-0 transition-opacity flex items-center justify-center'>
												{warningByFeature?.[c.id] ? (
													<WarningIcon size={14} color='text-warning-500' />
												) : (
													<Icon
														size={14}
														color={isSelected ? 'text-neutral-600' : 'text-neutral-400'}
													/>
												)}
											</span>
											{onDeleteCharacteristic && (
												<span
													onClick={(e) => {
														e.stopPropagation();
														onDeleteCharacteristic(c.id);
													}}
													className='absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center cursor-pointer hover:bg-error-50 rounded'
													title='Eliminar'
												>
													<Trash size={13} color='text-error-500' />
												</span>
											)}
										</div>
									)}
								</button>
							);
						})}
					</div>
				</>
			)}
		</aside>
	);
};

export default AsideCharacteristic;
