import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createChatStore } from './runtime-store.ts';

test('restores all saved exchanges and rejects stale conversation responses', () => {
  const store = createChatStore();
  store.receive({ type: 'opened', id: 'a' });
  store.receive({ type: 'opened', id: 'b' });
  store.receive({ type: 'loaded', chat: { id: 'a', name: 'Stale', exchanges: [{ task: 'wrong' }] } });
  assert.equal(store.getSnapshot().loading, true);
  store.receive({ type: 'loaded', chat: { id: 'b', name: 'Current', context_tokens: 4200, context_cap: 32000,
    exchanges: [{ task: 'Bonjour 👋', done_html: '<p>Réponse</p>', at: 1800000000 },
      { task: 'Suite', done_message: 'Texte', at: 1800000010 }] } });
  const state = store.getSnapshot();
  assert.equal(state.turns.length, 2);
  assert.equal(state.turns[0].html, '<p>Réponse</p>');
  assert.equal(state.turns[1].text, 'Texte');
  assert.equal(state.title, 'Current');
  assert.equal(state.used, 4200);
  assert.equal(state.limit, 32000);
});

test('tracks native user, tools, progress, completion and context updates', () => {
  const store = createChatStore();
  store.receive({ type: 'user', text: 'Read my page', via: 'Telegram' });
  store.receive({ type: 'session', id: 'session', runId: 'run-1' });
  store.receive({ type: 'tools', event: 'received', payload: JSON.stringify({ tools: [{ name: 'click', x: 12, y: 48 }] }) });
  store.receive({ type: 'progress', text: 'Reading…' });
  assert.equal(store.getSnapshot().turns[0].tools[0].status, 'running');
  assert.deepEqual(store.getSnapshot().turns[0].tools[0].args, { x: 12, y: 48 });
  store.receive({ type: 'context', used: 7000, limit: 64000 });
  store.receive({ type: 'reply', html: '<p>Complete</p>' });
  store.receive({ type: 'idle' });
  assert.equal(store.getSnapshot().running, false);
  assert.equal(store.getSnapshot().turns[0].tools[0].status, 'success');
  assert.equal(store.getSnapshot().turns[0].progress, '');
  assert.equal(store.getSnapshot().used, 7000);
});

test('new chat clears active session, errors and pending view state', () => {
  const store = createChatStore();
  store.receive({ type: 'history', rows: [{ id: 'saved' }] });
  store.receive({ type: 'user', text: 'Old task' });
  store.receive({ type: 'session', id: 'old' });
  store.receive({ type: 'error', text: 'Old error' });
  store.receive({ type: 'new' });
  const state = store.getSnapshot();
  assert.equal(state.activeId, undefined);
  assert.equal(state.error, undefined);
  assert.equal(state.running, false);
  assert.equal(state.turns.length, 0);
  assert.equal(state.conversations.length, 1);
  assert.equal(state.viewKey, 1);
  store.receive({ type: 'tools', event: 'received', payload: '{"tools":[{"name":"late"}]}' });
  assert.equal(store.getSnapshot().turns.length, 0);
});

test('keeps a late recording on its original turn', () => {
  const store = createChatStore();
  for (const id of ['one', 'two']) {
    store.receive({ type: 'user', text: id });
    store.receive({ type: 'session', id: 'chat', runId: id });
    store.receive({ type: 'idle' });
  }
  store.receive({ type: 'video', url: '/recordings/one.mp4', runId: 'one' });
  assert.equal(store.getSnapshot().turns[0].video, '/recordings/one.mp4');
  assert.equal(store.getSnapshot().turns[1].video, undefined);
});

test('surfaces startup failures and shell output without mixing sessions', () => {
  const store = createChatStore();
  store.receive({ type: 'user', text: 'Build' });
  store.receive({ type: 'session', id: 'chat' });
  store.receive({ type: 'task-start', id: 'task', description: 'Run build' });
  store.receive({ type: 'task-line', id: 'task', text: 'build output' });
  store.receive({ type: 'task-end', id: 'task', status: 'error', summary: 'Build failed' });
  store.receive({ type: 'shell-note', chatId: 'other', text: 'Wrong answer' });
  assert.equal(store.getSnapshot().turns[0].text, '');
  assert.equal(store.getSnapshot().turns[0].tools[0].status, 'error');
  store.receive({ type: 'idle', error: 'Error: provider unavailable' });
  assert.equal(store.getSnapshot().running, false);
  assert.equal(store.getSnapshot().turns[0].text, 'Error: provider unavailable');
});
