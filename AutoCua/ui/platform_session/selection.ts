export type ExecutionMode = 'supervised' | 'auto';
export type PlatformSummary = { id: string; name: string };
export type PlatformSelection = {
    platformId: string;
    executionMode: ExecutionMode;
    bound: boolean;
    busy: boolean;
    restoring: boolean;
    error: string;
};

export function newSelection(): PlatformSelection {
    return { platformId: '', executionMode: 'supervised', bound: false, busy: false, restoring: false, error: '' };
}

export function choosePlatform(state: PlatformSelection, id: string, platforms: PlatformSummary[]): PlatformSelection {
    if (state.bound || state.busy || state.restoring) return state;
    if (id && !platforms.some(platform => platform.id === id)) throw new Error('Unknown Web platform.');
    return { ...state, platformId: id, executionMode: 'supervised', error: '' };
}

export function chooseExecutionMode(state: PlatformSelection, mode: string): PlatformSelection {
    if (state.bound || state.busy || state.restoring || !state.platformId) return state;
    if (mode !== 'supervised' && mode !== 'auto') throw new Error('Unknown execution mode.');
    return { ...state, executionMode: mode };
}

export function restoreSelection(context: unknown, bound: boolean, busy = false): PlatformSelection {
    if (context === null) return { ...newSelection(), bound, busy };
    if (typeof context !== 'object' || context === null) throw new Error('Invalid saved platform context.');
    const data = context as Record<string, unknown>;
    if (typeof data.platform_id !== 'string' || !/^[a-z][a-z0-9_-]{0,63}$/.test(data.platform_id)
        || (data.execution_mode !== 'supervised' && data.execution_mode !== 'auto')) {
        throw new Error('Invalid saved platform context.');
    }
    return { ...newSelection(), platformId: data.platform_id, executionMode: data.execution_mode, bound, busy };
}

export function selectionPayload(state: PlatformSelection, agentMode: string): Record<string, string | null> {
    if (agentMode !== 'web') return {};
    if (state.restoring || state.error) throw new Error(state.error || 'Wait for this chat to finish loading.');
    return state.platformId
        ? { platform_id: state.platformId, execution_mode: state.executionMode }
        : { platform_id: null };
}
