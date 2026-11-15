import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { GearSix, Moon, Sun } from '@phosphor-icons/react';
import { AIChat } from '../components/ai-chat';
import { IconButton } from '../components/ui/action-button';
import type { Conversation } from '../components/ui/conversation-list';
import { chatStore, timestamp } from './runtime-store';
import { AutoCuaScene } from './autocua-scene';
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

function RuntimeControls() {
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const moved: { node: HTMLElement; parent: Node; next: ChildNode | null }[] = [];
    let timer: ReturnType<typeof setTimeout>;
    const mount = () => {
      if (!host.current || moved.length) return;
      for (const id of ['agentModeWrap', 'linkToggle', 'fastQualityToggle', 'chatModelDropdown']) {
        const node = document.getElementById(id);
        if (!node?.parentNode) continue;
        moved.push({ node, parent: node.parentNode, next: node.nextSibling });
        host.current.appendChild(node);
      }
    };
    // Wait until every legacy control has installed its event handlers.
    const schedule = () => { timer = setTimeout(mount, 0); };
    document.addEventListener('chatinput:ready', schedule);
    if (window.saccadeChatInput) schedule();
    return () => {
      clearTimeout(timer);
      document.removeEventListener('chatinput:ready', schedule);
      moved.reverse().forEach(({ node, parent, next }) => parent.insertBefore(node, next?.parentNode === parent ? next : null));
    };
  }, []);
  return <div ref={host} className="saccade-controls" aria-label="Agent and model" />;
}

export function SaccadeChat() {
  const state = useSyncExternalStore(chatStore.subscribe, chatStore.getSnapshot);
  const [runtime, setRuntime] = useState({ model: '', ready: false, hint: 'Starting Saccade…' });
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'));

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
    try { localStorage.setItem('saccade-theme', dark ? 'dark' : 'light'); } catch { /* Storage may be unavailable in a webview. */ }
  }, [dark]);

  useEffect(() => {
    const read = () => {
      const input = document.querySelector<HTMLTextAreaElement>('.chat-input');
      const selection = window.getModelSelection?.();
      const next = { model: selection?.model || '', ready: !!window.saccadeChatInput && !!selection?.provider && !!selection.model
        && !!input && !input.readOnly && (!input.disabled || input.classList.contains('agent-active')),
      hint: input?.placeholder || 'Select a model in Settings to start…' };
      setRuntime(old => old.model === next.model && old.ready === next.ready && old.hint === next.hint ? old : next);
    };
    const observer = new MutationObserver(read);
    const input = document.querySelector('.chat-input');
    const model = document.getElementById('chatModelDropdown');
    if (input) observer.observe(input, { attributes: true, attributeFilter: ['disabled', 'readonly', 'placeholder', 'class'] });
    if (model) observer.observe(model, { subtree: true, childList: true, characterData: true });
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
        composerToolbar={<RuntimeControls />}
        conversationContent={inset => <AutoCuaScene bottomInset={inset} />}
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
