import { useEffect, useRef, useState } from 'react';
import { submitOperatorChat, type PendingOperator } from './operator_chat.ts';

declare global { interface Window {
    remoteRunStarted?: (payload: string) => void;
    submitOperatorChat?: (text: string, session: string) => Promise<boolean>;
    operatorChatReply?: (payload: string) => void;
} }

/** The assistant reply and ordinary composer are the operator interface. */
export function OperatorReview() {
    const [pending, setPending] = useState<PendingOperator | null>(null);
    const [error, setError] = useState('');
    const presented = useRef<PendingOperator | null>(null);
    useEffect(() => { presented.current = pending; }, [pending]);
    useEffect(() => {
        window.submitOperatorChat = (text, session) => submitOperatorChat(text, session, {
            fetch: window.fetch.bind(window), currentSession: () => window.currentSessionId,
            presented: () => presented.current, update: setPending,
            resume: payload => window.remoteRunStarted?.(payload),
            reply: payload => window.operatorChatReply?.(payload),
        }).catch(error => {
            if (window.currentSessionId === session) setError(error instanceof Error ? error.message : 'Could not verify this reply.');
            throw error;
        });
        const abort = new AbortController();
        const refresh = async () => {
            const session = window.currentSessionId;
            if (!session) { setPending(null); return; }
            try {
                const response = await fetch('/api/operator?session_id=' + encodeURIComponent(session), { signal: abort.signal });
                const value = await response.json();
                if (window.currentSessionId === session) setPending(response.ok ? value : null);
            } catch { if (!abort.signal.aborted) setError('Could not verify the assistant pause. Please retry before replying.'); }
        };
        void refresh();
        document.addEventListener('operator:changed', refresh);
        const timer = window.setInterval(() => { void refresh(); }, 1500);
        return () => { abort.abort(); window.clearInterval(timer); document.removeEventListener('operator:changed', refresh); delete window.submitOperatorChat; };
    }, []);
    if (!pending || !['waiting_operator', 'resuming', 'pausing_operator'].includes(pending.state)) return null;
    return <section className="operator-assistance" aria-label="Assistant assistance" style={{ pointerEvents: 'auto', padding: '8px 12px', maxHeight: '35vh', overflow: 'auto' }}>
        <small role="status">{pending.state === 'pausing_operator' ? 'Pause requested - correction not applied yet' : pending.state === 'resuming' ? 'Checking the browser before continuing...' : 'Paused - no model requests'}</small>
        {pending.chat_message && <p>{pending.chat_message}</p>}
        {pending.procedure_summary && <>
            <p>I can remember this operator-assisted procedure for future sessions. Should I save it?</p>
            <p style={{ whiteSpace: 'pre-wrap' }}>{pending.procedure_label}</p>
            <details><summary>Read the procedure to be saved</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{pending.procedure_summary}</pre></details>
            <details><summary>What will change?</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{pending.procedure_diff}</pre></details>
        </>}
        <p>Reply in the chat below. Send only non-sensitive information; never send passwords or authentication codes. You can say "Cancel" to stop.</p>
        {pending.error && <p role="alert">{pending.error}</p>}
        {error && <p role="alert">{error}</p>}
    </section>;
}
