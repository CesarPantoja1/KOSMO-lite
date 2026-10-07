'use client';

import { useState } from 'react';
import { useController, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useCharacteristicStore } from '@/entities/characteristic';
import { toast } from '@/shared/ui';
import { useProjectStore } from '@/entities/project';
import { useRouter } from 'next/navigation';
import { CharacteristicFormData, characteristicSchema, FieldError } from '../model/types';

interface UseCreateCharacteristicReturn {
	titleValue: string;
	titleOnBlur: () => void;
	titleRef: React.Ref<HTMLInputElement>;
	descValue: string;
	descOnBlur: () => void;
	descRef: React.Ref<HTMLTextAreaElement>;
	titleCount: number;
	descCount: number;
	fieldErrors: FieldError;
	showSuggestionsModal: boolean;
	openSuggestionsModal: () => void;
	closeSuggestionsModal: () => void;
	handleTitleChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
	handleDescChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
	handleSubmit: (e: React.FormEvent<HTMLFormElement>) => void;
	handleCancel: () => void;
	applySuggestion: (title: string, description: string) => void;
	showConsistencyModal: boolean;
	consistencyInfo: { origin: string; reason: string } | null;
	isValidating: boolean;
	closeConsistencyModal: () => void;
}

function validateField(value: string, maxLength: number): string {
	const trimmed = value.trim();
	if (trimmed.length === 0) return 'Este campo es obligatorio';
	if (value.length > maxLength) return `Máximo ${maxLength} caracteres`;
	return '';
}

export function useCreateCharacteristic(): UseCreateCharacteristicReturn {
	const projectId = useProjectStore((s) => s.currentProject?.id);
	const router = useRouter();
	const storeAddCharacteristic = useCharacteristicStore((s) => s.addCharacteristic);
	const {
		control,
		handleSubmit: formSubmit,
		setValue,
	} = useForm<CharacteristicFormData>({
		mode: 'onChange',
		resolver: zodResolver(characteristicSchema),
		defaultValues: { title: '', description: '' },
	});

	const {
		field: {
			value: titleValue,
			onChange: titleOnChange,
			onBlur: titleOnBlur,
			ref: titleRef,
		},
	} = useController({ name: 'title', control });

	const {
		field: { value: descValue, onChange: descOnChange, onBlur: descOnBlur, ref: descRef },
	} = useController({ name: 'description', control });

	const [showSuggestionsModal, setShowSuggestionsModal] = useState(false);
	const [showConsistencyModal, setShowConsistencyModal] = useState(false);
	const [isValidating, setIsValidating] = useState(false);
	const [consistencyInfo, setConsistencyInfo] = useState<{
		origin: string;
		reason: string;
	} | null>(null);
	const [fieldErrors, setFieldErrors] = useState<FieldError>({
		title: '',
		description: '',
	});

	const titleCount = titleValue.length;
	const descCount = descValue.length;

	const handleTitleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
		const sanitizedValue = e.target.value.replace(/[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ\s]/g, '');
		const syntheticEvent = {
			...e,
			target: { ...e.target, value: sanitizedValue, name: e.target.name },
		};
		titleOnChange(syntheticEvent);
		if (fieldErrors.title) setFieldErrors((p) => ({ ...p, title: '' }));
	};

	const handleDescChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
		const sanitizedValue = e.target.value.replace(
			/[^a-zA-Z0-9áéíóúüñÁÉÍÓÚÜÑ\s.,:;\-()¿?¡!]/g,
			'',
		);
		const syntheticEvent = {
			...e,
			target: { ...e.target, value: sanitizedValue, name: e.target.name },
		};
		descOnChange(syntheticEvent);
		if (fieldErrors.description) setFieldErrors((p) => ({ ...p, description: '' }));
	};

	const onSubmit = async (data: CharacteristicFormData) => {
		const titleError = validateField(data.title, 50);
		const descError = validateField(data.description, 500);
		if (titleError || descError) {
			setFieldErrors({ title: titleError, description: descError });
			return;
		}
		if (!projectId) return;
		setIsValidating(true);
		try {
			const result = await storeAddCharacteristic(projectId, {
				title: data.title,
				description: data.description,
			});
			setIsValidating(false);

			if (result.is_saved) {
				if (result.warnings && result.warnings.length > 0) {
					toast.warning(result.warnings.join('\n'), undefined, 'Advertencia de solapamiento');
				}
				router.push('/proyecto/caracteristicas');
			} else {
				setConsistencyInfo({
					origin: result.origin || '',
					reason: result.inconsistency_reason || '',
				});
				setShowConsistencyModal(true);
			}
		} catch (err) {
			setIsValidating(false);
			const message =
				err instanceof Error
					? err.message
					: 'No se pudo guardar la característica. Intenta nuevamente.';
			toast.error(message);
		}
	};

	const handleCancel = () => {
		router.push('/proyecto/caracteristicas');
	};

	const applySuggestion = (title: string, description: string) => {
		setValue('title', title);
		setValue('description', description);
		setShowSuggestionsModal(false);
	};

	return {
		titleValue,
		titleOnBlur,
		titleRef,
		descValue,
		descOnBlur,
		descRef,
		titleCount,
		descCount,
		fieldErrors,
		showSuggestionsModal,
		openSuggestionsModal: () => setShowSuggestionsModal(true),
		closeSuggestionsModal: () => setShowSuggestionsModal(false),
		handleTitleChange,
		handleDescChange,
		handleSubmit: formSubmit(onSubmit),
		handleCancel,
		applySuggestion,
		showConsistencyModal,
		consistencyInfo,
		isValidating,
		closeConsistencyModal: () => setShowConsistencyModal(false),
	};
}
