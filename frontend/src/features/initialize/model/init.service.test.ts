import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/shared/api';

vi.mock('@/entities/discovery', () => ({
	useDiscoveryStore: { getState: vi.fn() },
	getDiscovery: vi.fn(),
}));

vi.mock('@/entities/characteristic', () => ({
	useCharacteristicStore: { getState: vi.fn() },
	getCharacteristics: vi.fn(),
}));

vi.mock('@/entities/requirements', () => ({
	useRequirementsStore: { getState: vi.fn() },
	getRequirements: vi.fn(),
}));

import { useDiscoveryStore, getDiscovery } from '@/entities/discovery';
import { useCharacteristicStore, getCharacteristics } from '@/entities/characteristic';
import { useRequirementsStore, getRequirements } from '@/entities/requirements';
import { initializeProject } from './init.service';

const discoveryState = { setCurrentDiscovery: vi.fn() };
const characteristicState = { setCurrentCharacteristics: vi.fn() };
const requirementsState = { setHasRequirements: vi.fn(), setCurrentRequirements: vi.fn() };

const api = {
	getDiscovery: vi.mocked(getDiscovery),
	getCharacteristics: vi.mocked(getCharacteristics),
	getRequirements: vi.mocked(getRequirements),
};

describe('initializeProject', () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.mocked(useDiscoveryStore.getState).mockReturnValue(discoveryState as never);
		vi.mocked(useCharacteristicStore.getState).mockReturnValue(characteristicState as never);
		vi.mocked(useRequirementsStore.getState).mockReturnValue(requirementsState as never);
	});

	it('ignora el 404 de discovery (caso normal cuando aún no existe)', async () => {
		// Arrange
		api.getDiscovery.mockRejectedValue(new ApiError({ status: 404 }));
		api.getCharacteristics.mockResolvedValue([]);

		// Act & Assert (no debe lanzar)
		await expect(initializeProject('prj_01')).resolves.toBeUndefined();
		expect(discoveryState.setCurrentDiscovery).not.toHaveBeenCalled();
	});

	it('guarda el discovery cuando la consulta es exitosa', async () => {
		// Arrange
		api.getDiscovery.mockResolvedValue({ id: 'd1', project_id: 'prj_01', content: 'x' });
		api.getCharacteristics.mockResolvedValue([]);

		// Act
		await initializeProject('prj_01');

		// Assert
		expect(discoveryState.setCurrentDiscovery).toHaveBeenCalledWith(
			expect.objectContaining({ content: 'x' }),
		);
	});

	it('no lanza si discovery falla con un error distinto a 404 (se captura arriba)', async () => {
		// Arrange
		api.getDiscovery.mockRejectedValue(new Error('network down'));

		// Act & Assert
		await expect(initializeProject('prj_01')).resolves.toBeUndefined();
		expect(api.getCharacteristics).not.toHaveBeenCalled();
	});

	it('retorna temprano si no hay características', async () => {
		// Arrange
		api.getDiscovery.mockResolvedValue(null as never);
		api.getCharacteristics.mockResolvedValue([]);

		// Act
		await initializeProject('prj_01');

		// Assert
		expect(characteristicState.setCurrentCharacteristics).not.toHaveBeenCalled();
		expect(api.getRequirements).not.toHaveBeenCalled();
	});

	it('carga requisitos para cada característica', async () => {
		// Arrange
		api.getDiscovery.mockResolvedValue(null as never);
		api.getCharacteristics.mockResolvedValue([
			{ id: 'f1' } as never,
			{ id: 'f2' } as never,
		]);
		api.getRequirements.mockImplementation(async (_p, id) =>
			id === 'f1'
				? ({ feature_id: 'f1', document_markdown: '## Doc', total: 1 } as never)
				: ({ feature_id: 'f2', document_markdown: '', total: 0 } as never),
		);

		// Act
		await initializeProject('prj_01');

		// Assert
		expect(characteristicState.setCurrentCharacteristics).toHaveBeenCalledWith([
			{ id: 'f1' },
			{ id: 'f2' },
		]);
		expect(requirementsState.setHasRequirements).toHaveBeenCalledWith('f1', true);
		expect(requirementsState.setCurrentRequirements).toHaveBeenCalledWith('f1', '## Doc');
		expect(requirementsState.setHasRequirements).toHaveBeenCalledWith('f2', false);
		expect(requirementsState.setCurrentRequirements).not.toHaveBeenCalledWith('f2', expect.anything());
	});

	it('ignora silenciosamente los features cuya consulta de requisitos falla', async () => {
		// Arrange
		api.getDiscovery.mockResolvedValue(null as never);
		api.getCharacteristics.mockResolvedValue([{ id: 'f1' } as never]);
		api.getRequirements.mockRejectedValue(new Error('boom'));

		// Act & Assert (no debe lanzar)
		await expect(initializeProject('prj_01')).resolves.toBeUndefined();
		expect(requirementsState.setHasRequirements).not.toHaveBeenCalled();
	});

	it('captura cualquier error inesperado sin propagarlo', async () => {
		// Arrange
		api.getDiscovery.mockResolvedValue(null as never);
		api.getCharacteristics.mockRejectedValue(new Error('unexpected'));

		// Act & Assert
		await expect(initializeProject('prj_01')).resolves.toBeUndefined();
	});
});
