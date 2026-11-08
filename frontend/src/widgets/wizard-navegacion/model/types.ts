export type ProjectStatus = 'active' | 'completed' | 'disable';

export type ItemWizardProps = {
	href: string;
	icon: React.ReactNode;
	iconContainerStyles: string;
	label: string;
	subtitle: string;
	labelStyles: string;
	onClick?: (e: React.MouseEvent) => void;
};

export type stylesIconStatus = {
	iconContainer: string;
	iconStyles: string;
	labelStyles: string;
};
