'use client';

import {
	DEFAULT_AI_MODEL,
	DEFAULT_AI_PROVIDER,
	TIER_LABELS,
	maskApiKey,
	useAiConfigStore,
	type AIProvider,
	type SaveAIConfigRequest,
} from '@/entities/ai-config';
import { formatApiError } from '@/shared/api/errors';
import { toast } from '@/shared/ui';
import { useCallback, useEffect, useMemo, useState } from 'react';

interface AiConfigFormProps {
	onSaved?: () => void;
	embedded?: boolean;
}

export function AiConfigForm({ onSaved, embedded }: AiConfigFormProps) {
	const { config, providers, loading, error, saveConfig, deleteConfig, fetchProviders } =
		useAiConfigStore();

	const [provider, setProvider] = useState<AIProvider>(
		config?.provider ?? DEFAULT_AI_PROVIDER,
	);
	const [model, setModel] = useState(config?.model ?? DEFAULT_AI_MODEL);
	const [apiKey, setApiKey] = useState('');
	const [showApiKey, setShowApiKey] = useState(false);
	const [isEditing, setIsEditing] = useState(false);

	useEffect(() => {
		if (providers.length === 0) fetchProviders();
	}, [fetchProviders, providers.length]);

	const selectedProviderInfo = useMemo(
		() => providers.find((p) => p.value === provider),
		[providers, provider],
	);

	const handleProviderChange = useCallback(
		(newProvider: AIProvider) => {
			setProvider(newProvider);
			const info = providers.find((p) => p.value === newProvider);
			if (info && info.models.length > 0) {
				const modelIds = info.models.map((m) => m.id);
				setModel((prev) => (modelIds.includes(prev) ? prev : modelIds[0]));
			}
		},
		[providers],
	);

	const handleSave = async () => {
		if (!apiKey.trim()) return;
		try {
			const data: SaveAIConfigRequest = { provider, model, api_key: apiKey.trim() };
			await saveConfig(data);
			toast.success('Configuración de IA guardada correctamente');
			setIsEditing(false);
			setApiKey('');
			setShowApiKey(false);
			onSaved?.();
		} catch (err) {
			toast.error(formatApiError(err, 'Error al guardar la configuración de IA'));
		}
	};

	const handleDelete = async () => {
		try {
			await deleteConfig();
			toast.success(
				'Clave de API eliminada. Configura una nueva clave para usar funciones de IA.',
			);
			setIsEditing(false);
			setApiKey('');
			setShowApiKey(false);
			onSaved?.();
		} catch (err) {
			toast.error(formatApiError(err, 'Error al eliminar la configuración de IA'));
		}
	};

	const handleStartEditing = () => {
		setIsEditing(true);
		setApiKey('');
		setShowApiKey(false);
		if (config?.provider) {
			setProvider(config.provider);
			setModel(config.model ?? DEFAULT_AI_MODEL);
		}
	};

	const handleCancel = () => {
		setIsEditing(false);
		setApiKey('');
		setShowApiKey(false);
		if (config?.provider) {
			setProvider(config.provider);
			setModel(config.model ?? DEFAULT_AI_MODEL);
		} else {
			setProvider(DEFAULT_AI_PROVIDER);
			setModel(DEFAULT_AI_MODEL);
		}
	};

	const maskedKey = config?.masked_key ?? maskApiKey(apiKey);
	const hasExistingKey = config?.has_api_key ?? false;
	const canSave = apiKey.trim().length > 0 && !loading;

	const tierOrder: Array<'flagship' | 'balanced' | 'fast'> = [
		'flagship',
		'balanced',
		'fast',
	];
	const modelsByTier = tierOrder
		.map((tier) => ({
			tier,
			models: selectedProviderInfo?.models.filter((m) => m.tier === tier) ?? [],
		}))
		.filter((group) => group.models.length > 0);

	const cardClasses = embedded
		? 'flex flex-col gap-4'
		: 'bg-neutral-0 border border-neutral-200 rounded-xl shadow-sm p-6';

	return (
		<div className={cardClasses}>
			<div className='flex items-center justify-between mb-4'>
				<h3 className='text-lg font-semibold text-neutral-800'>Configura tu API Key</h3>
				{hasExistingKey && !isEditing && (
					<span className='text-xs font-medium px-2.5 py-1 rounded-full bg-success-50 text-success-700 border border-success-500/20'>
						Configurado
					</span>
				)}
			</div>

			{error && (
				<div className='bg-error-50 text-error-700 border border-error-500/20 rounded-lg px-4 py-3 text-sm mb-4'>
					{error}
				</div>
			)}

			{!isEditing && hasExistingKey && (
				<div className='mb-4'>
					<p className='text-neutral-500 text-sm mb-2'>Clave configurada:</p>
					<p className='text-neutral-800 font-mono text-sm bg-neutral-50 border border-neutral-300 rounded-lg px-3 py-2.5'>
						{maskedKey}
					</p>
				</div>
			)}

			{!isEditing && !hasExistingKey && (
				<p className='text-neutral-400 text-sm mb-4'>No hay clave de API configurada</p>
			)}

			{!isEditing ? (
				<div className='flex gap-2'>
					{hasExistingKey ? (
						<>
							<button
								type='button'
								onClick={handleStartEditing}
								className='btn btn-secondary btn-sm'
							>
								Reemplazar
							</button>
							<button
								type='button'
								onClick={handleDelete}
								disabled={loading}
								className='btn btn-destructive btn-sm disabled:opacity-50'
							>
								{loading ? 'Eliminando...' : 'Eliminar'}
							</button>
						</>
					) : (
						<button
							type='button'
							onClick={handleStartEditing}
							className='btn btn-primary btn-sm'
						>
							Agregar API Key
						</button>
					)}
				</div>
			) : (
				<div className='flex flex-col gap-4'>
					<div>
						<label className='text-neutral-500 text-sm font-medium mb-1.5 block'>
							Proveedor
						</label>
						<select
							value={provider}
							onChange={(e) => handleProviderChange(e.target.value as AIProvider)}
							className='bg-neutral-50 border border-neutral-300 text-neutral-800 rounded-lg px-3 py-2.5 outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 transition-all w-full'
						>
							{providers.map((p) => (
								<option key={p.value} value={p.value}>
									{p.label}
								</option>
							))}
						</select>
					</div>

					<div>
						<label className='text-neutral-500 text-sm font-medium mb-1.5 block'>
							Modelo
						</label>
						<select
							value={model}
							onChange={(e) => setModel(e.target.value)}
							className='bg-neutral-50 border border-neutral-300 text-neutral-800 rounded-lg px-3 py-2.5 outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 transition-all w-full'
						>
							{modelsByTier.map(({ tier, models }) => (
								<optgroup key={tier} label={`— ${TIER_LABELS[tier]}`}>
									{models.map((m) => (
										<option key={m.id} value={m.id}>
											{m.display_name}
										</option>
									))}
								</optgroup>
							))}
						</select>
					</div>

					<div>
						<label className='text-neutral-500 text-sm font-medium mb-1.5 block'>
							Clave de API
						</label>
						<div className='flex items-center gap-2'>
							<input
								type={showApiKey ? 'text' : 'password'}
								value={apiKey}
								onChange={(e) => setApiKey(e.target.value)}
								placeholder={hasExistingKey ? '••••••••****' : 'sk-...'}
								className='bg-neutral-50 border border-neutral-300 text-neutral-800 rounded-lg px-3 py-2.5 outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 transition-all placeholder:text-neutral-400 flex-1'
							/>
							<button
								type='button'
								onClick={() => setShowApiKey(!showApiKey)}
								className='px-3 py-2.5 bg-neutral-100 border border-neutral-300 rounded-lg text-neutral-600 hover:text-neutral-800 transition-colors'
							>
								{showApiKey ? 'Ocultar' : 'Mostrar'}
							</button>
						</div>
					</div>

					<div className='flex gap-2'>
						<button
							type='button'
							onClick={handleSave}
							disabled={!canSave}
							className='btn btn-primary btn-sm disabled:opacity-50'
						>
							{loading ? 'Verificando y guardando...' : 'Guardar'}
						</button>
						<button
							type='button'
							onClick={handleCancel}
							disabled={loading}
							className='btn btn-secondary btn-sm disabled:opacity-50'
						>
							Cancelar
						</button>
					</div>
				</div>
			)}
		</div>
	);
}
