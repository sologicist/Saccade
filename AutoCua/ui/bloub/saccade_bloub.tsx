import { useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import {
    BloubBot, makeBlock, type Block, type ColorId, type ExpressionId, type ShapeId,
} from 'bloub-react';

type Kind = 'autocua' | 'computeruse' | 'webuse' | 'mobileuse' | 'coderuse' | 'scraperuse' | 'minion';
type Mood = 'intro' | 'ready' | 'running' | 'success' | 'error';

const SKINS: Record<Kind, { shape: ShapeId; color: ColorId; expression: ExpressionId }> = {
    autocua: { shape: 'cercle', color: 'encre', expression: 'attentif' },
    computeruse: { shape: 'squircle', color: 'bleu', expression: 'curieux' },
    webuse: { shape: 'galet', color: 'turquoise', expression: 'attentif' },
    mobileuse: { shape: 'capsule', color: 'violet', expression: 'heureux' },
    coderuse: { shape: 'hexagone', color: 'orange', expression: 'curieux' },
    scraperuse: { shape: 'nuage', color: 'rose', expression: 'attentif' },
    minion: { shape: 'goutte', color: 'gris', expression: 'excite' },
};

// makeBlock respects Bloub's minimum transition/morph durations. Idle already
// breathes and blinks naturally; only the working cycle should repeat.
const CYCLES: Record<Mood, Block[]> = {
    intro: ['idle', 'wide', 'wink', 'idle'].map(state => makeBlock(state as Block['state'])),
    ready: [makeBlock('idle')],
    running: [makeBlock('thinking'), makeBlock('orbit'), makeBlock('thinking')],
    success: [makeBlock('notify'), makeBlock('idle')],
    error: [makeBlock('alert'), makeBlock('idle')],
};

function Avatar({ kind, mood, active }: { kind: Kind; mood: Mood; active: boolean }) {
    const [block, setBlock] = useState(0);
    const cycle = CYCLES[mood];
    const playing = active && (mood === 'running' || block < cycle.length - 1);

    return (
        <BloubBot
            key={active ? 'live' : 'still'}
            {...SKINS[kind]}
            size={320}
            paper="#ffffff"
            cycle={cycle}
            block={block}
            onBlockChange={setBlock}
            state={active ? cycle[block].state : 'idle'}
            playing={playing}
            frozenAt={active ? undefined : 0}
            follow={active && (mood === 'ready' || mood === 'intro')}
            aria-label={`Avatar ${kind}`}
            style={{ width: '100%', height: '100%', display: 'block' }}
        />
    );
}

function kindOf(host: HTMLElement): Kind {
    if (host.matches('.cc-mbot')) return 'minion';
    if (host.matches('.cc-rbot, .cc-line.cc-answer')) return 'coderuse';

    const name = (
        host.getAttribute('aria-label') ||
        host.closest('[data-kind]')?.getAttribute('data-kind') ||
        host.closest('.chat-turn')?.getAttribute('data-bot') ||
        host.querySelector('img')?.getAttribute('src') || ''
    ).toLowerCase();

    if (name.includes('computer')) return 'computeruse';
    if (name.includes('browser') || name.includes('web')) return 'webuse';
    if (/mobile|ios|android/.test(name)) return 'mobileuse';
    if (/coder|shell/.test(name)) return 'coderuse';
    if (name.includes('scraper')) return 'scraperuse';
    if (name.includes('minion')) return 'minion';
    return 'autocua';
}

function replyMood(reply: Element): Mood {
    return reply.matches('.is-ended') || reply.querySelector('.reply-panel.is-ended')
        ? 'error' : 'success';
}

function moodOf(host: HTMLElement): Mood {
    if (host.closest('#splashOverlay')) return 'intro';
    if (host.closest('#welcomeHero')) return 'ready';
    if (host.matches('.agent-container.show-reply, .cc-line.cc-answer')) return replyMood(host);
    if (host.matches('#modeBot .mb-bot')) return 'ready';
    if (host.matches('.chain-bot')) {
        const reply = host.closest('.chat-turn')?.querySelector('.agent-container.show-reply');
        return reply ? replyMood(reply) : 'running';
    }
    if (host.matches('.cc-rbot.handing')) {
        const answer = host.closest('.coder-card')?.querySelector('.cc-answer.cc-bot-wait');
        if (answer) return replyMood(answer);
    }
    if (host.matches('.cc-mbot')) return host.matches('.working') ? 'running' : 'ready';
    return 'running';
}

function shouldDisplay(host: HTMLElement): boolean {
    if (host.matches('.agent-container.show-reply')) {
        const turn = host.closest('.chat-turn');
        return !!turn?.classList.contains('live') && !turn.querySelector(':scope > .chain-bot.docked');
    }
    if (host.matches('.cc-line.cc-answer')) {
        const answers = host.closest('.coder-card')?.querySelectorAll('.cc-line.cc-answer');
        if (!answers || answers[answers.length - 1] !== host) return false;
    }
    // The latest answer waits for the flying Shell bot to hand over.
    return !host.matches('.cc-line.cc-answer.cc-bot-wait');
}

const TARGETS = [
    '#splashOverlay .bot', '#welcomeHero .bot', '#modeBot .mb-bot', '#liveTurn > .chain-bot',
    '.sub-box > .sub-bot', '.coder-card .cc-rbot', '.coder-card .cc-mbot',
    '.agent-container.show-reply', '.coder-card .cc-line.cc-answer',
].join(', ');

interface Entry {
    root: Root;
    mount: HTMLSpanElement;
    visible: boolean;
    signature: string;
}

// The classic scripts keep their original DOM/image hooks and own all travel
// animations. React owns only these isolated, disposable SVG layers.
export function startSaccadeBloub(): () => void {
    const entries = new Map<HTMLElement, Entry>();
    const hosts = new Map<Element, HTMLElement>();
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;

    function render(host: HTMLElement): void {
        const entry = entries.get(host);
        if (!entry) return;
        const kind = kindOf(host);
        const mood = moodOf(host);
        const active = entry.visible && !motion.matches && !document.hidden
            && getComputedStyle(entry.mount).visibility !== 'hidden';
        const signature = `${kind}:${mood}:${active}`;
        if (entry.signature === signature) return;
        entry.signature = signature;
        entry.mount.dataset.kind = kind;
        entry.mount.dataset.mood = mood;
        entry.mount.dataset.active = String(active);
        entry.root.render(<Avatar key={`${kind}:${mood}`} kind={kind} mood={mood} active={active} />);
    }

    // Observe the avatar itself: a reply's avatar can sit above/beside its
    // host, and clipped/off-screen history must not keep a RAF loop alive.
    const visibility = new IntersectionObserver(changes => {
        for (const change of changes) {
            const host = hosts.get(change.target);
            if (!host) continue;
            const entry = entries.get(host);
            if (!entry) continue;
            entry.visible = change.isIntersecting;
            render(host);
        }
    });

    function remove(host: HTMLElement, entry: Entry): void {
        visibility.unobserve(entry.mount);
        hosts.delete(entry.mount);
        entry.root.unmount();
        entry.mount.remove();
        entries.delete(host);
    }

    function sync(): void {
        frame = 0;
        const wanted = new Set(Array.from(document.querySelectorAll<HTMLElement>(TARGETS)).filter(shouldDisplay));
        for (const [host, entry] of entries) {
            // Legacy text/HTML replacement can remove a layer without removing
            // its host. Recreate the root in that case as well.
            if (!host.isConnected || !wanted.has(host) || !host.contains(entry.mount)) remove(host, entry);
        }
        for (const host of wanted) {
            if (!entries.has(host)) {
                const mount = document.createElement('span');
                mount.className = 'saccade-bloub-layer';
                mount.setAttribute('aria-hidden', 'true');
                const parent = host.querySelector('.mb-bot-body, .chain-bot-body') || host;
                parent.appendChild(mount);
                entries.set(host, { root: createRoot(mount), mount, visible: false, signature: '' });
                hosts.set(mount, host);
                visibility.observe(mount);
            }
            render(host);
        }
    }

    function schedule(): void {
        if (!frame) frame = requestAnimationFrame(sync);
    }

    const observer = new MutationObserver(mutations => {
        if (mutations.some(mutation => {
            const element = mutation.target instanceof Element ? mutation.target : mutation.target.parentElement;
            // Bloub updates its SVG every frame. Never feed those mutations
            // back into a document-wide scan.
            return !element?.closest('.saccade-bloub-layer');
        })) schedule();
    });
    observer.observe(document.body, {
        childList: true, subtree: true, attributes: true,
        attributeFilter: ['class', 'src', 'data-kind', 'data-bot', 'aria-label'],
    });
    motion.addEventListener('change', schedule);
    document.addEventListener('visibilitychange', schedule);
    document.body.classList.add('saccade-bloub');
    sync();

    return () => {
        observer.disconnect();
        visibility.disconnect();
        cancelAnimationFrame(frame);
        motion.removeEventListener('change', schedule);
        document.removeEventListener('visibilitychange', schedule);
        for (const [host, entry] of entries) remove(host, entry);
        document.body.classList.remove('saccade-bloub');
    };
}
