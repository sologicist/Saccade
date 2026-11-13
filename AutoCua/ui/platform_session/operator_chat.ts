import { operatorResumePayload } from './operator_resume.ts';

export interface PendingOperator {
    session_id: string; run_id: string; intervention_id: string; revision: string; token: string;
    state: string; request: { category: string; reason: string; request: string };
    chat_message?: string; error?: string; procedure_summary?: string; procedure_diff?: string;
    presentation_digest?: string;
    procedure_label?: string;
    recovery?: 'cancel_restart'; diagnostic_code?: string;
}

export function samePresentation(a: PendingOperator | null, b: PendingOperator): boolean {
    return !!a && ['session_id', 'run_id', 'intervention_id', 'revision', 'presentation_digest'].every(
        key => a[key as keyof PendingOperator] === b[key as keyof PendingOperator]);
}

async function considerCorrection(text: string, session: string, options: {
    fetch: typeof fetch; currentSession: () => string | null | undefined;
    update: (value: PendingOperator | null) => void; reply?: (payload: string) => void;
}): Promise<boolean> {
    const url = '/api/operator/correction?session_id=' + encodeURIComponent(session);
    const context = await options.fetch(url);
    if (!context.ok) throw new Error('Could not verify the previous navigation context. Please retry.');
    const claim = await context.json();
    if (options.currentSession() !== session) return true;
    const response = await options.fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, claim }) });
    const value = await response.json();
    if (!response.ok) throw new Error('The correction could not be safely matched to the current task. Please retry.');
    if (options.currentSession() !== session) return true;
    if (value.status === 'ordinary') return false;
    if (value.message && value.status !== 'blocked') throw new Error(value.message);
    options.update(value.pending || null);
    if (typeof value.reply_html === 'string') options.reply?.(JSON.stringify(value));
    return true;
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
    if (pending === null) return considerCorrection(text, session, options);
    if (typeof pending !== 'object' || !pending || pending.session_id !== session || !['waiting_operator', 'resuming', 'pausing_operator', 'completed', 'cancelled'].includes(pending.state)) {
        throw new Error('Could not verify the assistant state. Please retry.');
    }
    if (['completed', 'cancelled'].includes(pending.state)) return considerCorrection(text, session, options);
    if (pending.session_id !== session) throw new Error('The assistant question belongs to another conversation.');
    const cancelling = ['cancel', 'cancel task', 'stop', 'annuler', 'annule'].includes(text.trim().toLowerCase());
    if (pending.state === 'resuming' && !cancelling) return considerCorrection(text, session, options);
    if (pending.state === 'pausing_operator' && !cancelling) { options.update(pending); return true; }
    if (!cancelling && !samePresentation(options.presented(), pending)) {
        options.update({ ...pending, chat_message: 'Please review the current question or proposed procedure below, then send your reply.' });
        return true;
    }
    const result = await options.fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run_id: pending.run_id, intervention_id: pending.intervention_id,
            revision: pending.revision, token: pending.token, action: 'chat', answer: text,
            non_sensitive: true, presentation_digest: pending.presentation_digest || null }) });
    const value = await result.json();
    if (!result.ok) throw new Error(pending.recovery === 'cancel_restart' ? 'This session cannot resume safely. Send Cancel, then start a new conversation after reviewing the browser.' : 'This reply could not be matched safely. Review the current assistant question and try again.');
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
