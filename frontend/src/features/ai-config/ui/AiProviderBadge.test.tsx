import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useAiConfigStore } from '@/entities/ai-config';
import { crearAiConfig, renderWithProviders } from '@/test';
import { AiProviderBadge } from './AiProviderBadge';

const PROVEEDORES = [
	{ value: 'google', label: 'Google Gemini', models: [] },
	{ value: 'anthropic', label: 'Anthropic', models: [] },
];

describe('AiProviderBadge', () => {
	describe('con IA propia configurada', () => {
		it('muestra el proveedor como personalizado y la clave enmascarada', () => {
			useAiConfigStore.setState({
				config: crearAiConfig({ provider: 'anthropic', masked_key: 'sk-••••9f2a' }),
				providers: PROVEEDORES,
			});

			renderWithProviders(<AiProviderBadge />);

			expect(screen.getByText('Anthropic (Personalizado)')).toBeInTheDocument();
			expect(screen.getByText('sk-••••9f2a')).toBeInTheDocument();
		});

		it('usa el identificador del proveedor si no hay etiqueta disponible', () => {
			useAiConfigStore.setState({
				config: crearAiConfig({ provider: 'deepseek', masked_key: null }),
				providers: PROVEEDORES,
			});

			renderWithProviders(<AiProviderBadge />);

			expect(screen.getByText('deepseek (Personalizado)')).toBeInTheDocument();
		});

		it('no ofrece configurar aunque se pida el enlace', () => {
			useAiConfigStore.setState({ config: crearAiConfig(), providers: PROVEEDORES });

			renderWithProviders(<AiProviderBadge showLink onConfigureClick={vi.fn()} />);

			expect(screen.queryByRole('button')).not.toBeInTheDocument();
		});
	});

	describe('con el proveedor predeterminado', () => {
		const sinIaPropia = () =>
			useAiConfigStore.setState({
				config: crearAiConfig({ has_api_key: false, is_custom: false }),
			});

		it('muestra "Proveedor predeterminado" sin enlace por defecto', () => {
			sinIaPropia();

			renderWithProviders(<AiProviderBadge />);

			expect(screen.getByText('Proveedor predeterminado')).toBeInTheDocument();
			expect(screen.queryByRole('button')).not.toBeInTheDocument();
		});

		it('ofrece configurar una IA propia cuando se pide el enlace', async () => {
			sinIaPropia();
			const onConfigureClick = vi.fn();
			const { user } = renderWithProviders(
				<AiProviderBadge showLink onConfigureClick={onConfigureClick} />,
			);

			await user.click(screen.getByRole('button', { name: 'Configurar IA propia' }));

			expect(onConfigureClick).toHaveBeenCalledOnce();
		});

		it('sin configuración cargada también usa el proveedor predeterminado', () => {
			renderWithProviders(<AiProviderBadge />);

			expect(screen.getByText('Proveedor predeterminado')).toBeInTheDocument();
		});
	});
});
