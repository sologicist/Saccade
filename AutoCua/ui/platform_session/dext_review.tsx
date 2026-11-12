import { useEffect, useState } from 'react';

declare global { interface Window { currentSessionId?: string | null; } }

interface ProcedureProposal {
    proposal_id: string; base_revision: string; candidate_revision: string;
    old: string; new: string; diff: string; evidence: string; rationale: string;
}
interface NavigationPreview {
    proposal_id: string; observation_id: string; target_id: number;
    label: string; role: string; route: string; expected_postcondition: string;
    procedure_revision: string; policy_revision: string;
}
interface ControlStatus {
    session_id: string; review_token: string; closed: boolean; pinned_revision: string;
    active: { current: string; previous: string | null };
    previous_content: string | null;
    proposal: ProcedureProposal | null; navigation: NavigationPreview | null;
    observation_id: string | null; clients: string[]; routes: string[];
}

export function DextReview({ enabled }: { enabled: boolean }) {
    const [status, setStatus] = useState<ControlStatus | null>(null);
    const [error, setError] = useState('');
    const [routes, setRoutes] = useState<string[]>([]);
    const [route, setRoute] = useState('workspace');
    const [client, setClient] = useState('');
    const [sending, setSending] = useState(false);
    useEffect(() => {
        if (!enabled) { setStatus(null); return; }
        const controller = new AbortController();
        const refresh = async () => {
            const session = window.currentSessionId;
            if (!session) { setStatus(null); return; }
            try {
                const response = await fetch('/api/dext/control?session_id=' + encodeURIComponent(session), { signal: controller.signal });
                const data = await response.json();
                if (window.currentSessionId === session) setStatus(response.ok ? data : null);
            } catch { if (!controller.signal.aborted) setError('Could not verify operator controls.'); }
        };
        void refresh();
        const timer = window.setInterval(() => { void refresh(); }, 2000);
        return () => { controller.abort(); window.clearInterval(timer); };
    }, [enabled]);

    const decide = async (event: string, fields: Record<string, unknown> = {}) => {
        if (!status || sending || status.session_id !== window.currentSessionId) return;
        setSending(true);
        setError('');
        try {
            const response = await fetch('/api/dext/control?session_id=' + encodeURIComponent(status.session_id), {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ event, review_token: status.review_token, ...fields }),
            });
            const data = await response.json();
            if (!response.ok || data.status === 'blocked') setError(data.error || data.code || 'Request remains blocked.');
            const fresh = await fetch('/api/dext/control?session_id=' + encodeURIComponent(status.session_id));
            const next = await fresh.json();
            if (window.currentSessionId === status.session_id) setStatus(fresh.ok ? next : null);
        } catch { setError('Operator decision could not be verified. Reopen review before retrying.'); }
        finally { setSending(false); }
    };
    if (!enabled) return null;
    const proposal = status?.proposal;
    const navigation = status?.navigation;
    return <details className="dext-review" aria-label="Dext operator review">
        <summary>Dext operator review</summary>
        <p>Navigation previews are available. Live gestures, PDF capture, external analysis and accounting entry remain blocked pending verified boundaries.</p>
        {!status && <p>Start or resume a supervised Dext chat to enable local procedure review.</p>}
        {status && <>
            <p>Pinned procedure: <code>{status.pinned_revision}</code></p>
            {navigation && <fieldset disabled={sending}>
                <legend>Exact navigation preview — no gesture will execute</legend>
                <p>Target [{navigation.target_id}]: {navigation.label} ({navigation.role})</p>
                <p>Requested route: {navigation.route}. Expected check: {navigation.expected_postcondition}</p>
                <p>Observation: <code>{navigation.observation_id}</code></p>
                <button type="button" onClick={() => void decide('navigation_review', { proposal_id: navigation.proposal_id, observation_id: navigation.observation_id, approve: false })}>Reject request</button>
                <button type="button" onClick={() => void decide('navigation_review', { proposal_id: navigation.proposal_id, observation_id: navigation.observation_id, approve: true })}>Approve exact preview (execution blocked)</button>
            </fieldset>}
            <fieldset disabled={sending}>
                <legend>Teach a reusable route from an operator correction</legend>
                <p>Select generic steps only. Chat, page text and private record details are never saved as procedure instructions.</p>
                <select aria-label="Generic route step" value={route} onChange={e => setRoute(e.target.value)}>
                    {status.routes.map(value => <option key={value}>{value}</option>)}
                </select>
                <button type="button" disabled={routes.length >= 8} onClick={() => setRoutes(previous => [...previous, route])}>Add step</button>
                <button type="button" onClick={() => setRoutes([])}>Clear draft</button>
                <p>{routes.join(' → ')}</p>
                <button type="button" disabled={!routes.length || !!proposal} onClick={() => void decide('teach', { routes })}>Propose procedure diff</button>
            </fieldset>
            {proposal && <fieldset disabled={sending}>
                <legend>Review this exact procedure candidate</legend>
                <p>{proposal.evidence} {proposal.rationale}</p>
                <p>Base: <code>{proposal.base_revision}</code></p>
                <p>Candidate: <code>{proposal.candidate_revision}</code></p>
                <details><summary>Previous and proposed text</summary><pre>{proposal.old}</pre><pre>{proposal.new}</pre></details>
                <pre>{proposal.diff}</pre>
                <button type="button" onClick={() => void decide('review', { proposal_id: proposal.proposal_id, base_revision: proposal.base_revision, candidate_revision: proposal.candidate_revision, approve: false })}>Reject candidate</button>
                <button type="button" onClick={() => void decide('review', { proposal_id: proposal.proposal_id, base_revision: proposal.base_revision, candidate_revision: proposal.candidate_revision, approve: true })}>Publish this exact procedure</button>
            </fieldset>}
            <button type="button" disabled={sending || !status.closed || !!proposal || !!navigation}
                onClick={() => void decide('adopt')}>Adopt approved procedure for next run</button>
            {status.active.previous && <details><summary>Review previous procedure for rollback</summary>
                <pre>{status.previous_content}</pre>
                <button type="button" disabled={sending || !status.closed || !!proposal || !!navigation}
                    onClick={() => void decide('rollback', { expected: status.active.current, target: status.active.previous })}>Approve rollback to this revision</button>
            </details>}
            <fieldset disabled={sending || !status.observation_id || status.closed}>
                <legend>Local dossier claim — business access remains blocked</legend>
                <select aria-label="Local dossier" value={client} onChange={e => setClient(e.target.value)}>
                    <option value="">Choose registered dossier</option>
                    {status.clients.map(value => <option key={value}>{value}</option>)}
                </select>
                <button type="button" disabled={!client} onClick={() => void decide('bind', { client_id: client, observation_id: status.observation_id })}>Confirm dossier claim for this observation</button>
                <p>Human confirmation alone cannot prove Dext record identity or authorize external disclosure.</p>
            </fieldset>
        </>}
        {error && <p role="alert">{error}</p>}
    </details>;
}
