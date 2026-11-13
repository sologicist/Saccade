import { operatorResumePayload } from './operator_resume.ts';

export interface PendingOperator {
    session_id: string; run_id: string; intervention_id: string; revision: string; token: string;
    state: string; request: { category: string; reason: string; request: string };
    chat_message?: string; error?: string; procedure_summary?: string; procedure_diff?: string;
    presentation_digest?: string;
    procedure_label?: string;
}

export function samePresentation(a: PendingOperator | null, b: PendingOperator): boolean {
    return !!a && ['session_id', 'run_id', 'intervention_id', 'revision', 'presentation_digest'].every(
        key => a[key as keyof PendingOperator] === b[key as keyof PendingOperator]);
}

/** Host-only reply transport. A failure or unshown question never starts a task. */
export async function submitOperatorChat(text: string, session: string, options: {
    fetch: typeof fetch; currentSession: () => string | null | undefined;
    presented: () => PendingOperator | null; update: (value: PendingOperator | null) => void;
    resume: (payload: string) => void;
    reply?: (payload: string) => void;
}): Promise<boolean> {
    const url = '/api/operator?session_id=' + encodeURIComponent(session);
    const response = await options.fetch(url);
    if (!response.ok) throw new Error('Could not verify the pending assistant question. Please retry.');
    const pending: PendingOperator | null = await response.json();
    if (options.currentSession() !== session) return true;
    if (pending === null) return false;
    if (typeof pending !== 'object' || !pending || pending.session_id !== session || !['waiting_operator', 'resuming', 'completed', 'cancelled'].includes(pending.state)) {
        throw new Error('Could not verify the assistant state. Please retry.');
    }
    if (['completed', 'cancelled'].includes(pending.state)) return false;
    if (pending.session_id !== session) throw new Error('The assistant question belongs to another conversation.');
    if (pending.state === 'resuming') { options.update(pending); return true; }
    if (!samePresentation(options.presented(), pending)) {
        options.update({ ...pending, chat_message: 'Please review the current question or proposed procedure below, then send your reply.' });
        return true;
    }
    const result = await options.fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: pending.run_id, intervention_id: pending.intervention_id,
            revision: pending.revision, token: pending.token, action: 'chat', answer: text,
            non_sensitive: true, presentation_digest: pending.presentation_digest || null }) });
    const value = await result.json();
    if (!result.ok) throw new Error('This reply could not be matched safely. Review the current assistant question and try again.');
    if (options.currentSession() !== session) return true;
    if (value.status === 'started') {
        options.update(null);
        options.resume(JSON.stringify({ ...operatorResumePayload(value, session), task: text }));
    } else {
        options.update(value.pending || null);
        if (['waiting_operator', 'cancelled'].includes(value.status) && typeof value.reply_html === 'string') options.reply?.(JSON.stringify(value));
    }
    return true;
}
