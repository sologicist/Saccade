import { useLayoutEffect, useRef, useState } from 'react';
import { chooseExecutionMode, choosePlatform, newSelection, restoreSelection, selectionPayload } from './selection.ts';
import type { PlatformSummary } from './selection.ts';

declare global {
    interface Window {
        getPlatformSelection?: (agentMode: string) => Record<string, string | null>;
    }
}

export function PlatformSessionSelector() {
    const [state, setState] = useState(newSelection);
    const [platforms, setPlatforms] = useState<PlatformSummary[]>([]);
    const [catalogError, setCatalogError] = useState('');
    const [web, setWeb] = useState(false);
    const current = useRef(state);
    current.current = state;

    useLayoutEffect(() => {
        let mounted = true;
        const controller = new AbortController();
        fetch('/api/platforms', { signal: controller.signal })
            .then(async response => {
                const data = await response.json();
                if (!response.ok || !Array.isArray(data.platforms)) throw new Error(data.error || 'Could not load Web platforms.');
                if (mounted) setPlatforms(data.platforms);
            })
            .catch(error => { if (mounted && error.name !== 'AbortError') setCatalogError('Could not load Web platforms.'); });

        window.getPlatformSelection = mode => selectionPayload(current.current, mode);
        const modeChanged = () => setWeb(document.getElementById('agentModeWrap')?.dataset.mode === 'web');
        const reset = () => setState(newSelection());
        const opening = () => setState({ ...newSelection(), restoring: true });
        const busy = () => setState(previous => ({ ...previous, busy: true }));
        const idle = () => setState(previous => ({ ...previous, busy: false }));
        const restore = (event: Event) => {
            const detail = (event as CustomEvent).detail || {};
            try { setState(restoreSelection(detail.context, detail.bound === true, detail.busy === true)); }
            catch { setState(previous => ({ ...previous, restoring: false, error: 'Could not validate this chat. Reopen it before sending.' })); }
        };
        const failed = () => setState(previous => ({ ...previous, restoring: false, error: 'Could not load this chat. Reopen it before sending.' }));
        const modeWrap = document.getElementById('agentModeWrap');
        const observer = new MutationObserver(modeChanged);
        if (modeWrap) observer.observe(modeWrap, { attributes: true, attributeFilter: ['data-mode'] });
        modeChanged();
        const listeners: [string, EventListener][] = [
            ['chat:new', reset], ['chat:opened', opening], ['platformsession:restore', restore],
            ['platformsession:busy', busy], ['platformsession:idle', idle], ['platformsession:error', failed],
        ];
        listeners.forEach(([name, listener]) => document.addEventListener(name, listener));
        return () => {
            mounted = false;
            controller.abort();
            observer.disconnect();
            listeners.forEach(([name, listener]) => document.removeEventListener(name, listener));
            delete window.getPlatformSelection;
        };
    }, []);

    const locked = state.bound || state.busy || state.restoring;
    const missing = state.platformId && !platforms.some(platform => platform.id === state.platformId);
    return (
        <div className="platform-session" hidden={!web} aria-label="Web platform session">
            <div className="platform-session-fields">
                <label>Platform
                    <select aria-label="Web platform" value={state.platformId} disabled={locked || !!catalogError}
                        onChange={event => setState(previous => choosePlatform(previous, event.target.value, platforms))}>
                        <option value="">Generic AutoCua</option>
                        {platforms.map(platform => <option key={platform.id} value={platform.id}>{platform.name}</option>)}
                        {missing && <option value={state.platformId}>{state.platformId} (saved platform)</option>}
                    </select>
                </label>
                {state.platformId && <label>Execution
                    <select aria-label="Platform execution mode" value={state.executionMode} disabled={locked}
                        onChange={event => setState(previous => chooseExecutionMode(previous, event.target.value))}>
                        <option value="supervised">Supervised</option>
                        <option value="auto">Auto</option>
                    </select>
                </label>}
            </div>
            <p className="platform-session-note" role="status">
                {state.error || catalogError || (state.restoring ? 'Loading saved platform context…' : state.bound
                    ? 'Platform and execution mode are saved for this chat. Start a new chat to change them.'
                    : state.platformId ? 'Observe and navigate in Chrome. Complete sign-in manually; other actions require approval controls.' : '')}
            </p>
        </div>
    );
}
