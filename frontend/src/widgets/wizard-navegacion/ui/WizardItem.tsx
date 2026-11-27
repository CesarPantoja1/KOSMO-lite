import Link from 'next/link';
import { ItemWizardProps } from '../model/types';

const WizardItem = ({
	href,
	icon,
	iconContainerStyles,
	label,
	subtitle,
	labelStyles,
	onClick,
}: ItemWizardProps) => {
	return (
		<Link
			href={href}
			onClick={onClick}
			className='group relative flex-none flex items-center gap-2 px-3 py-1 transition-all duration-200 hover:scale-105'
		>
			<span
				className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-all duration-300 ${iconContainerStyles}`}
			>
				{icon}
			</span>
			<div className='flex flex-col'>
				<span
					className={`whitespace-nowrap text-xs font-semibold leading-none transition-colors duration-200 tracking-wide ${labelStyles}`}
				>
					{label}
				</span>
				<span className='whitespace-nowrap text-[11px] leading-tight text-neutral-500 mt-1'>
					{subtitle}
				</span>
			</div>
		</Link>
	);
};

export default WizardItem;
