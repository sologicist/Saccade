import { restoreSelection } from './selection.ts';

/** Use the existing chat lifecycle with the server's verified platform binding. */
export function operatorResumePayload(value: { session_id: string; run_id: string; platform_context: unknown }, session: string) {
    if (value.session_id !== session || !value.run_id) throw new Error('Invalid operator continuation session.');
    // Missing/invalid context must never silently restore Generic AutoCua.
    restoreSelection(value.platform_context, true, true);
    return { task: 'Continue the original task after operator intervention.', mode: 'web',
        session_id: session, run_id: value.run_id, platform_context: value.platform_context, via: 'operator' };
}
