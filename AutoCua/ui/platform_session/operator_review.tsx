import { useEffect, useState } from 'react';
import { operatorResumePayload } from './operator_resume';

declare global { interface Window { remoteRunStarted?: (payload: string) => void; } }

interface Pending {
    session_id: string; run_id: string; intervention_id: string; revision: string; token: string;
    state: string; request: { category: string; reason: string; request: string };
    error?: string;
}

export function OperatorReview() {
    const [pending, setPending] = useState<Pending | null>(null);
    const [answer, setAnswer] = useState('');
    const [safe, setSafe] = useState(false);
    const [error, setError] = useState('');
    const [busy, setBusy] = useState(false);
    useEffect(() => {
        const abort = new AbortController();
        const refresh = async () => {
            const session = window.currentSessionId;
            if (!session) { setPending(null); return; }
            try {
                const response = await fetch('/api/operator?session_id=' + encodeURIComponent(session), { signal: abort.signal });
                const value = await response.json();
                if (window.currentSessionId === session) setPending(response.ok ? value : null);
            } catch { if (!abort.signal.aborted) setError('Could not verify operator checkpoint.'); }
        };
        void refresh();
        const timer = window.setInterval(() => { void refresh(); }, 1500);
        return () => { abort.abort(); window.clearInterval(timer); };
    }, []);
    useEffect(() => { setAnswer(''); setSafe(false); }, [pending?.revision]);
    if (!pending || !['waiting_operator', 'resuming'].includes(pending.state)) return null;
    const respond = async (action: string) => {
        setBusy(true); setError('');
        try {
            const response = await fetch('/api/operator?session_id=' + encodeURIComponent(pending.session_id), {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
                    run_id: pending.run_id, intervention_id: pending.intervention_id, revision: pending.revision,
                    token: pending.token, action, answer, non_sensitive: safe,
                }),
            });
            const value = await response.json();
            if (!response.ok) throw new Error(value.error || 'Resume failed. The task remains suspended.');
            if (value.status === 'started') {
                document.dispatchEvent(new CustomEvent('platformsession:busy'));
                window.remoteRunStarted?.(JSON.stringify(operatorResumePayload(value, pending.session_id)));
            }
            setPending(null); setAnswer('');
        } catch (e) { setError(e instanceof Error ? e.message : 'Resume failed.'); }
        finally { setBusy(false); }
    };
    return <section className="platform-session" style={{ pointerEvents: 'auto', background: 'white', maxHeight: '45vh', overflow: 'auto' }} aria-label="Operator intervention">
        <strong>{pending.state === 'resuming' ? 'Revalidating resources…' : 'Agent paused — no model requests'}</strong>
        <p>{pending.request.category}: {pending.request.request}</p>
        <p>Reason: {pending.request.reason}. Responses grant no permissions. Never enter passwords, authentication codes, keys or secrets.</p>
        {pending.error && <p role="alert">{pending.error}</p>}
        {pending.request.category === 'question' && <>
            <textarea aria-label="Non-sensitive operator answer" maxLength={2000} value={answer} onChange={e => setAnswer(e.target.value)} />
            <label><input type="checkbox" checked={safe} onChange={e => setSafe(e.target.checked)} />This answer contains no sensitive information.</label>
        </>}
        <button type="button" disabled={busy || pending.state !== 'waiting_operator' || (pending.request.category === 'question' && (!safe || !answer.trim()))} onClick={() => void respond('resume')}>Resume original task</button>
        <button type="button" disabled={busy} onClick={() => void respond('cancel')}>Cancel task</button>
        {error && <p role="alert">{error}</p>}
    </section>;
}
