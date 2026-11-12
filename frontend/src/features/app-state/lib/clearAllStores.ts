import { clearAuthStore } from '@/shared/model/auth-store';
import { clearProjectStore } from '@/entities/project';
import { clearDiscoveryStore } from '@/entities/discovery';
import { clearCharacteristicStore } from '@/entities/characteristic';
import { clearRequirementsStore } from '@/entities/requirements';
import { clearImplementationStore } from '@/entities/implementation';
import { useChatSessionsStore } from '@/entities/chat';
import { useConsistencyGateStore } from '@/entities/consistency';
import { clearAppStore } from '../model/app.store';

export const clearAllStores = () => {
	clearAuthStore();
	clearProjectStore();
	clearDiscoveryStore();
	clearCharacteristicStore();
	clearRequirementsStore();
	clearImplementationStore();
	useChatSessionsStore.getState().reset();
	useConsistencyGateStore.getState().reset();
	clearAppStore();
};
