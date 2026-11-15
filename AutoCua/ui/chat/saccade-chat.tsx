import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { GearSix, Moon, Sun } from '@phosphor-icons/react';
import { AIChat } from '../components/ai-chat';
import { IconButton } from '../components/ui/action-button';
import type { Conversation } from '../components/ui/conversation-list';
import { chatStore, timestamp } from './runtime-store';
import { AutoCuaScene } from './autocua-scene';
import { AgentActivity } from './agent-activity';
import { Segmented } from '../components/ui/segmented-control';
import './saccade-chat.css';

declare global {
  interface Window {
    saccadeChats?: { open(id: string): void; create(): void; delete(id: string): void; download(id: string): void };
    saccadeChatInput?: { send(text: string): boolean };
    getModelSelection?: () => { provider?: string; model?: string };
  }
}

// Stable identity keeps ConversationList's undo timer from restarting on stream updates.
const deleteConversation = (chat: Conversation) => window.saccadeChats?.delete(chat.id);


type SpeedMode = 'fast' | 'quality';
type PhoneLink = 'wireless' | 'wired';

function RuntimeControls({ running }: { running: boolean }) {
  const host = useRef<HTMLDivElement>(null);

  const [speed, setSpeed] = useState<SpeedMode>(() => {
    const legacy = document.getElementById('fastQualityToggle');
    return legacy && !legacy.classList.contains('quality')
      ? 'fast'
      : 'quality';
  });

  const [link, setLink] = useState<PhoneLink>(() => {
    const legacy = document.getElementById('linkToggle');
    return legacy && !legacy.classList.contains('wired')
      ? 'wireless'
      : 'wired';
  });

  const [agentMode, setAgentMode] = useState('computer');
  const [pairing, setPairing] = useState(false);

  // Fast / Quality :
  // Le contrôleur Saccade lit la classe "quality" lors de l'envoi.
  const selectSpeed = (next: SpeedMode) => {
    const legacy = document.getElementById('fastQualityToggle');

    if (!legacy) return;

    legacy.classList.toggle('quality', next === 'quality');
    legacy.setAttribute(
      'aria-checked',
      String(next === 'quality')
    );

    setSpeed(next);
  };

  // Wi-Fi / Wired :
  // Un vrai clic sur le contrôle historique déclenche
  // /api/phone-link et l'événement phonelink:changed.
  const selectLink = (next: PhoneLink) => {
    const legacy = document.getElementById('linkToggle');
    const modeWrap = document.getElementById('agentModeWrap');

    if (!legacy || modeWrap?.dataset.pair === 'pairing') return;

    const current: PhoneLink = legacy.classList.contains('wired')
      ? 'wired'
      : 'wireless';

    if (current !== next) {
      legacy.click();
    }

    // Refléter le véritable état après le traitement du clic.
    setLink(
      legacy.classList.contains('wired') ? 'wired' : 'wireless'
    );
  };

  useEffect(() => {
    const moved: {
      node: HTMLElement;
      parent: Node;
      next: ChildNode | null;
    }[] = [];

    let timer: ReturnType<typeof setTimeout>;
    let modeObserver: MutationObserver | undefined;

    const readMode = () => {
      const wrap = document.getElementById('agentModeWrap');

      if (!wrap) return;

      setAgentMode(wrap.dataset.mode || 'computer');
      setPairing(wrap.dataset.pair === 'pairing');
    };

    const readLink = () => {
      const legacy = document.getElementById('linkToggle');

      if (!legacy) return;

      setLink(
        legacy.classList.contains('wired') ? 'wired' : 'wireless'
      );
    };

    const mount = () => {
      if (!host.current || moved.length) return;

      const linkControl = host.current.querySelector(
        '.saccade-link-segmented'
      );

      if (!linkControl) return;

      // Les deux anciens toggles restent dans le composeur
      // natif invisible pour conserver leurs contrôleurs JS.
      //
      // Seuls le sélecteur de mode agent et le modèle
      // sont déplacés dans la barre TUFFUI.

      for (const id of [
        'agentModeWrap',
        'chatModelDropdown',
      ]) {
        const node = document.getElementById(id);

        if (!node?.parentNode) continue;

        moved.push({
          node,
          parent: node.parentNode,
          next: node.nextSibling,
        });

        if (id === 'chatModelDropdown') {
          host.current.appendChild(node);
        } else {
          host.current.insertBefore(node, linkControl);
        }
      }

      readMode();
      readLink();

      const wrap = document.getElementById('agentModeWrap');

      if (wrap) {
        modeObserver = new MutationObserver(readMode);

        modeObserver.observe(wrap, {
          attributes: true,
          attributeFilter: [
            'data-mode',
            'data-sub',
            'data-pair',
          ],
        });
      }
    };

    const schedule = () => {
      clearTimeout(timer);
      timer = setTimeout(mount, 0);
    };

    document.addEventListener('chatinput:ready', schedule);
    document.addEventListener('phonelink:changed', readLink);
    document.addEventListener('agentmode:changed', readMode);

    if (window.saccadeChatInput) {
      schedule();
    }

    return () => {
      clearTimeout(timer);
      modeObserver?.disconnect();

      document.removeEventListener('chatinput:ready', schedule);
      document.removeEventListener('phonelink:changed', readLink);
      document.removeEventListener('agentmode:changed', readMode);

      moved.reverse().forEach(({ node, parent, next }) => {
        parent.insertBefore(
          node,
          next?.parentNode === parent ? next : null
        );
      });
    };
  }, []);

  return (
    <div
      ref={host}
      className="saccade-controls"
      aria-label="Agent and model"
    >
      <Segmented<PhoneLink>
        label="Phone connection"
        size="sm"
        className="saccade-link-segmented"
        value={link}
        onValueChange={selectLink}
        options={[
          {
            value: 'wireless',
            label: 'Wi-Fi',
            disabled: pairing || (running && agentMode === 'mobile'),
          },
          {
            value: 'wired',
            label: 'Wired',
            disabled: pairing || (running && agentMode === 'mobile'),
          },
        ]}
      />

      <Segmented<SpeedMode>
        label="Execution speed"
        size="sm"
        className="saccade-speed-segmented"
        value={speed}
        onValueChange={selectSpeed}
        options={[
          {
            value: 'fast',
            label: 'Fast',
            disabled: running,
          },
          {
            value: 'quality',
            label: 'Quality',
            disabled: running,
          },
        ]}
      />
    </div>
  );
}


export function SaccadeChat() {
  const state = useSyncExternalStore(chatStore.subscribe, chatStore.getSnapshot);
  const [runtime, setRuntime] = useState({ model: '', mode: 'computer', ready: false, hint: 'Starting Saccade…' });
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'));

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    try { localStorage.setItem('saccade-theme', dark ? 'dark' : 'light'); } catch { /* Storage may be unavailable in a webview. */ }
  }, [dark]);

  useEffect(() => {
    const read = () => {
      const input = document.querySelector<HTMLTextAreaElement>('.chat-input');
      const selection = window.getModelSelection?.();
      const next = { model: selection?.model || '', mode: document.getElementById('agentModeWrap')?.dataset.mode || 'computer',
      ready: !!window.saccadeChatInput && !!selection?.provider && !!selection.model
        && !!input && !input.readOnly && (!input.disabled || input.classList.contains('agent-active')),
      hint: input?.placeholder || 'Select a model in Settings to start…' };
      setRuntime(old => old.model === next.model && old.mode === next.mode && old.ready === next.ready && old.hint === next.hint ? old : next);
    };
    const observer = new MutationObserver(read);
    const input = document.querySelector('.chat-input');
    const model = document.getElementById('chatModelDropdown');
    const mode = document.getElementById('agentModeWrap');
    if (input) observer.observe(input, { attributes: true, attributeFilter: ['disabled', 'readonly', 'placeholder', 'class'] });
    if (model) observer.observe(model, { subtree: true, childList: true, characterData: true });
    if (mode) observer.observe(mode, { attributes: true, attributeFilter: ['data-mode'] });
    document.addEventListener('chatinput:ready', read);
    document.addEventListener('agentmode:changed', read);
    read();
    return () => { observer.disconnect(); document.removeEventListener('chatinput:ready', read); document.removeEventListener('agentmode:changed', read); };
  }, []);

  const send = useCallback((text: string) => {
    if (window.saccadeChatInput?.send(text)) return true;
    chatStore.receive({ type: 'error', text: document.querySelector<HTMLTextAreaElement>('.chat-input')?.placeholder || 'Select a model in Settings to start.' });
    return false;
  }, []);

  return <>
    <div className="saccade-chat-screen">
      <AIChat resetKey={state.viewKey} data={{
        conversations: state.conversations.map(chat => ({ id: chat.id, title: chat.name || 'New chat', updatedAt: timestamp(chat.updated_at),
          running: state.running && chat.id === state.activeId })),
        activeId: state.activeId, title: state.title, model: runtime.model || 'Saccade',
        messages: state.turns.map(turn => ({ id: turn.id, role: 'user', at: turn.at, content: null })),
        starters: [], context: { limit: state.limit, segments: [{ id: 'conversation', label: 'Conversation', tokens: state.used }] },
        user: { name: 'You' },
      }} status={state.running ? 'streaming' : 'idle'}
        onSend={send}
        onStop={() => window.postMessage('pcbtn:clicked', window.location.origin)}
        onNewChat={() => window.saccadeChats?.create()}
        onSelectConversation={chat => {
          if (chat.id === state.activeId) return;
          if (state.running) chatStore.receive({ type: 'error', text: 'Stop the running agent before opening another conversation.' });
          else window.saccadeChats?.open(chat.id);
        }}
        onDeleteConversation={deleteConversation}
        shareLabel="Download conversation"
        onShare={state.activeId ? () => window.saccadeChats?.download(state.activeId!) : undefined}
        composerDisabled={state.loading || (!state.running && !runtime.ready)}
        allowAttachments={false}
        composerToolbar={<RuntimeControls running={state.running} />}
        composerStatus={<AgentActivity key={state.turns[state.turns.length - 1]?.id || 'empty'}
          turn={state.turns[state.turns.length - 1]} running={state.running} />}
        conversationContent={inset => <AutoCuaScene bottomInset={inset} mode={runtime.mode} />}
        headerActions={<>
          <IconButton icon={dark ? Sun : Moon} label={dark ? 'Activer le mode clair' : 'Activer le mode sombre'}
            aria-pressed={dark} onClick={() => setDark(value => !value)} />
          <IconButton icon={GearSix} label="Settings" onClick={() => document.dispatchEvent(new CustomEvent('open-settings'))} />
        </>}
        notice={state.loading ? <p role="status" className="px-2 text-xs text-muted-foreground">Loading conversation…</p>
          : state.error ? <p role="alert" className="px-2 text-xs text-negative">{state.error}</p>
          : !runtime.ready && !state.running ? <button type="button" className="px-2 text-left text-xs text-muted-foreground hover:text-foreground"
            onClick={() => document.dispatchEvent(new CustomEvent('open-settings'))}>{runtime.hint}</button> : undefined}
      />
    </div>
  </>;
}
