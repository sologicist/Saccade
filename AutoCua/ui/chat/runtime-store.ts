// Structured adapter for the existing native/webview runtime. No second agent
// connection: all events come from the same handlers that drive the native app.
export type SavedExchange = {
  task?: string; done_message?: string; done_html?: string; at?: number;
  status?: string; video_url?: string;
};
export type SavedChat = {
  id: string; name?: string; updated_at?: number; exchanges?: SavedExchange[];
  last_done_message?: string; last_done_message_html?: string;
  context_tokens?: number; context_cap?: number;
};
export type RuntimeTool = {
  id: string; name: string; args: Record<string, unknown>;
  status: 'pending' | 'running' | 'success' | 'error'; result?: string; error?: string;
};
export type RuntimeTurn = {
  id: string; task: string; at: string; via?: string; text: string; html: string;
  progress: string; tools: RuntimeTool[]; image?: string; video?: string;
  runId?: string;
};
export type ChatSnapshot = {
  conversations: SavedChat[]; activeId?: string; title: string; turns: RuntimeTurn[];
  running: boolean; loading: boolean; error?: string; used: number; limit: number;
  viewKey: number;
};
export type ChatEvent =
  | { type: 'history'; rows: SavedChat[] }
  | { type: 'opened'; id: string }
  | { type: 'loaded'; chat: SavedChat }
  | { type: 'new' }
  | { type: 'user'; text: string; via?: string }
  | { type: 'session'; id: string; runId?: string }
  | { type: 'reply'; html: string }
  | { type: 'progress'; text: string }
  | { type: 'idle'; error?: string }
  | { type: 'error'; text: string }
  | { type: 'context'; used: number; limit: number }
  | { type: 'image'; image: string }
  | { type: 'video'; url: string; runId?: string }
  | { type: 'tools'; event: string; payload?: string }
  | { type: 'task-start'; id: string; description: string }
  | { type: 'task-line'; id: string; text: string }
  | { type: 'task-end'; id: string; status: string; summary?: string }
  | { type: 'shell-note'; text: string; chatId?: string };

const initial = (): ChatSnapshot => ({
  conversations: [], title: 'New chat', turns: [], running: false,
  loading: false, used: 0, limit: 300000, viewKey: 0,
});
export const timestamp = (seconds?: number) => new Date((seconds || 0) * 1000).toISOString();

export function createChatStore() {
  let state = initial();
  let seq = 0;
  const listeners = new Set<() => void>();
  const publish = (patch: Partial<ChatSnapshot>) => {
    state = { ...state, ...patch };
    listeners.forEach(listener => listener());
  };
  const updateTurn = (update: (turn: RuntimeTurn) => RuntimeTurn) => {
    if (!state.turns.length || state.loading) return;
    const turns = [...state.turns];
    turns[turns.length - 1] = update(turns[turns.length - 1]);
    publish({ turns });
  };
  const finishTools = (turn: RuntimeTurn, failed = false): RuntimeTurn => ({
    ...turn, tools: turn.tools.map(tool => tool.status === 'running'
      ? { ...tool, status: failed ? 'error' : 'success' } : tool),
  });
  function receive(event: ChatEvent) {
    switch (event.type) {
      case 'history': publish({ conversations: event.rows,
        title: event.rows.find(chat => chat.id === state.activeId)?.name || state.title }); break;
      case 'opened':
        publish({ activeId: event.id, title: state.conversations.find(c => c.id === event.id)?.name || 'Chat',
          turns: [], loading: true, error: undefined, viewKey: state.viewKey + 1 });
        break;
      case 'loaded': {
        if (state.activeId !== event.chat.id) return;
        const chat = event.chat;
        let exchanges = chat.exchanges || [];
        if (!exchanges.length && (chat.last_done_message_html || chat.last_done_message)) {
          exchanges = [{ done_html: chat.last_done_message_html, done_message: chat.last_done_message, at: chat.updated_at }];
        }
        publish({ title: chat.name || 'Chat', loading: false, error: undefined,
          used: chat.context_tokens || 0, limit: chat.context_cap || 300000,
          turns: exchanges.map((e, i) => ({ id: `${chat.id}-${i}`, task: e.task || '',
            at: timestamp(e.at), html: e.done_html || '', text: e.done_message || '',
            progress: '', tools: [], video: e.video_url })),
        });
        break;
      }
      case 'new': publish({ ...initial(), conversations: state.conversations, activeId: undefined,
        error: undefined, viewKey: state.viewKey + 1 }); break;
      case 'session':
        updateTurn(t => ({ ...t, runId: event.runId }));
        publish({ activeId: event.id }); break;
      case 'user':
        if (!event.text.trim() || state.loading) return;
        publish({ running: true, error: undefined,
          title: state.turns.length ? state.title : event.text.slice(0, 80),
          turns: [...state.turns, { id: `live-${++seq}`, task: event.text,
            via: event.via, at: new Date().toISOString(), text: '', html: '', progress: '', tools: [] }],
        });
        break;
      case 'reply': updateTurn(t => ({ ...finishTools(t), html: event.html, progress: '' })); break;
      case 'progress': updateTurn(t => ({ ...t, progress: event.text })); break;
      case 'idle':
        updateTurn(t => finishTools({ ...t, text: event.error || t.text }, !!event.error));
        publish({ running: false, ...(event.error ? { error: event.error } : {}) });
        break;
      case 'error': publish({ error: event.text, loading: false }); break;
      case 'context': publish({ used: Math.max(0, event.used), limit: event.limit || 300000 }); break;
      case 'image':
        if (state.running) updateTurn(t => ({ ...t, image: event.image }));
        break;
      case 'video':
        if (event.runId) publish({ turns: state.turns.map(t => t.runId === event.runId
          ? { ...t, image: undefined, video: event.url } : t) });
        else updateTurn(t => ({ ...t, image: undefined, video: event.url }));
        break;
      case 'tools': {
        if (!state.running || state.loading) return;
        let payload: { tools?: Record<string, unknown>[]; text?: string } = {};
        try { payload = JSON.parse(event.payload || '{}'); } catch { return; }
        if (event.event === 'turn') updateTurn(t => finishTools(t));
        if (event.event === 'received') updateTurn(t => ({ ...t, tools: [...t.tools,
          ...(payload.tools || []).map(raw => ({ id: `tool-${++seq}`, name: String(raw.name || 'tool'),
            args: Object.fromEntries(Object.entries(raw).filter(([key]) => key !== 'name')),
            status: 'running' as const })),
        ] }));
        if (event.event === 'error') updateTurn(t => finishTools({ ...t, progress: payload.text || '' }, true));
        if (event.event === 'run_end') updateTurn(t => finishTools(t));
        break;
      }
      case 'task-start': updateTurn(t => ({ ...t, tools: [...t.tools.filter(tool => tool.id !== event.id),
        { id: event.id, name: 'shell', args: { task: event.description }, status: 'running' }] })); break;
      case 'task-line': updateTurn(t => ({ ...t, tools: t.tools.map(tool => tool.id === event.id
        ? { ...tool, result: ((tool.result || '') + event.text + '\n').slice(-24000) } : tool) })); break;
      case 'task-end': updateTurn(t => ({ ...t, tools: t.tools.map(tool => tool.id === event.id
        ? { ...tool, status: /error|fail|stop/.test(event.status) ? 'error' : 'success',
          result: event.summary || tool.result } : tool) })); break;
      case 'shell-note':
        if (event.chatId && event.chatId !== state.activeId) return;
        updateTurn(t => ({ ...t, text: event.text, progress: '' })); break;
    }
  }
  return { getSnapshot: () => state, receive,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; } };
}

export const chatStore = createChatStore();

// Install before the classic scripts load, including their first history fetch.
if (typeof document !== 'undefined') {
  document.addEventListener('saccade:chat', event => chatStore.receive((event as CustomEvent<ChatEvent>).detail));
  document.addEventListener('chat:new', () => chatStore.receive({ type: 'new' }));
  document.addEventListener('chat:opened', event => chatStore.receive({ type: 'opened', id: (event as CustomEvent<{ id: string }>).detail.id }));
}
