import { useDiscoveryStore, getDiscovery } from '@/entities/discovery';
import { useCharacteristicStore, getCharacteristics } from '@/entities/characteristic';
import { useRequirementsStore, getRequirements } from '@/entities/requirements';
import { ApiError } from '@/shared/api';

export const initializeProject = async (projectId: string): Promise<void> => {
	try {
		// El 404 es el caso normal cuando aún no existe el documento de descubrimiento
		try {
			const discovery = await getDiscovery(projectId);
			if (discovery) {
				useDiscoveryStore.getState().setCurrentDiscovery(discovery);
			}
		} catch (error) {
			if (!(error instanceof ApiError && error.status === 404)) {
				throw error;
			}
		}

		const characteristics = await getCharacteristics(projectId);
		if (!characteristics || characteristics.length === 0) return;
		useCharacteristicStore.getState().setCurrentCharacteristics(characteristics);

		await Promise.allSettled(
			characteristics.map(async (c) => {
				const reqResult = await getRequirements(projectId, c.id);
				const content = reqResult.document_markdown ?? '';
				useRequirementsStore.getState().setHasRequirements(c.id, !!content);
				if (content) {
					useRequirementsStore.getState().setCurrentRequirements(c.id, content);
				}
			}),
		);
	} catch (error) {
		console.error('[initializeProject] Error:', error);
	}
};
