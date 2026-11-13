import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { operatorResumePayload } from './operator_resume.ts';
import { restoreSelection } from './selection.ts';
import { submitOperatorChat } from './operator_chat.ts';

function operatorTransport(changes = {}) {
    const pending = { session_id: 'chat', run_id: 'run', intervention_id: 'request', revision: 'revision', token: 'opaque',
        state: 'waiting_operator', request: { category: 'authentication', reason: 'authentication_required', request: 'Please sign in privately.' }, ...changes };
    const calls = [], resumed = [], updates = [];
    let shown = pending, session = 'chat';
    const options = { currentSession: () => session, presented: () => shown, update: value => updates.push(value),
        resume: value => resumed.push(JSON.parse(value)), fetch: async (url, init) => {
            calls.push({ url, init });
            return { ok: true, json: async () => init ? { status: 'started', session_id: 'chat', run_id: 'new-run', platform_context: { platform_id: 'dext', execution_mode: 'supervised' } } : pending };
        } };
    return { options, calls, resumed, updates, hide: () => { shown = null; }, move: () => { session = 'other'; } };
}

test('ordinary replies enter only the broker and resume the same chat with the user text', async () => {
    const ui = operatorTransport();
    assert.equal(await submitOperatorChat('Je suis connecté', 'chat', ui.options), true);
    assert.equal(ui.calls.length, 2);
    assert.ok(ui.calls.every(call => call.url === '/api/operator?session_id=chat'));
    const body = JSON.parse(ui.calls[1].init.body);
    assert.equal(body.action, 'chat');
    assert.equal(body.intervention_id, 'request');
    assert.equal(ui.resumed[0].session_id, 'chat');
    assert.equal(ui.resumed[0].task, 'Je suis connecté');
    assert.equal(ui.resumed[0].platform_context.platform_id, 'dext');
});

test('an unshown or changed proposal cannot consume a yes or start a run', async () => {
    const ui = operatorTransport({ presentation_digest: 'exact-candidate', procedure_summary: 'Purchases then Inbox' });
    ui.hide();
    assert.equal(await submitOperatorChat('Yes', 'chat', ui.options), true);
    assert.equal(ui.calls.length, 1);
    assert.equal(ui.resumed.length, 0);
    assert.match(ui.updates[0].chat_message, /review/);
});

test('broker failures and changing chats never fall through into an unrelated run', async () => {
    const ui = operatorTransport();
    ui.options.fetch = async () => { throw Error('offline'); };
    await assert.rejects(submitOperatorChat('Done', 'chat', ui.options));
    assert.equal(ui.resumed.length, 0);
    const moved = operatorTransport();
    moved.move();
    assert.equal(await submitOperatorChat('Done', 'chat', moved.options), true);
    assert.equal(moved.calls.length, 1);
    assert.equal(moved.resumed.length, 0);
});

test('only an explicitly absent pending intervention allows normal composer routing', async () => {
    const ui = operatorTransport();
    ui.options.fetch = async (url, init) => ({ ok: true, json: async () =>
        url.includes('/correction?') ? (init ? { status: 'ordinary' } : { signature: 'context', token: 'one-use' }) : null });
    assert.equal(await submitOperatorChat('A new task', 'chat', ui.options), false);
    assert.equal(ui.resumed.length, 0);
});

test('spontaneous corrections use context-bound host classification without starting another run', async () => {
    const ui = operatorTransport();
    const calls = [];
    ui.options.fetch = async (url, init) => {
        calls.push({ url, init });
        return { ok: true, json: async () => !url.includes('/correction?') ? null : !init ?
            { signature: 'context', token: 'one-use' } : { status: 'waiting_operator', pending: {
                session_id: 'chat', state: 'pausing_operator', request: { request: 'Pause requested; correction not applied yet.' } } } };
    };
    assert.equal(await submitOperatorChat('First click Purchases, then Inbox.', 'chat', ui.options), true);
    assert.equal(ui.resumed.length, 0);
    assert.equal(ui.updates[0].state, 'pausing_operator');
    assert.equal(calls.filter(call => call.init).length, 1);
    assert.equal(JSON.parse(calls[2].init.body).claim.token, 'one-use');
    assert.ok(calls.every(call => !call.url.includes('start-agent')));
});

test('an active pending procedure or authentication reply takes priority over spontaneous classification', async () => {
    const ui = operatorTransport({ state: 'pausing_operator' });
    assert.equal(await submitOperatorChat('A different route', 'chat', ui.options), true);
    assert.equal(ui.calls.length, 1);
    assert.equal(ui.resumed.length, 0);
});

test('operator resume restores the same chat and Dext platform through the existing lifecycle', () => {
    const context = { platform_id: 'dext', execution_mode: 'supervised' };
    const payload = operatorResumePayload({ session_id: 'chat', run_id: 'run', platform_context: context }, 'chat');
    const restored = restoreSelection(payload.platform_context, true, true);
    assert.equal(payload.session_id, 'chat');
    assert.equal(payload.mode, 'web');
    assert.equal(restored.platformId, 'dext');
    assert.equal(restored.bound, true);
    assert.equal(restored.busy, true);
    assert.equal(operatorResumePayload({ session_id: 'chat', run_id: 'run', platform_context: null }, 'chat').platform_context, null);
    for (const value of [undefined, {}, { platform_id: 'dext', execution_mode: 'invalid' }]) {
        assert.throws(() => operatorResumePayload({ session_id: 'chat', run_id: 'run', platform_context: value }, 'chat'));
    }
    assert.throws(() => operatorResumePayload({ session_id: 'other', run_id: 'run', platform_context: context }, 'chat'));
});

test('the actual reply renderer treats waiting_operator as a pause, not a failure', () => {
    const classes = new Map();
    const reply = { innerHTML: '', classList: { toggle: (name, value) => classes.set(name, value) } };
    const zone = { querySelector: () => reply, classList: { add() {} } };
    const window = {};
    const document = { getElementById: id => id === 'agentContainer' ? zone : null };
    vm.runInNewContext(readFileSync(new URL('../container/agent/run_reply.js', import.meta.url), 'utf8'), { window, document });
    window.showRunReply('Paused for operator intervention.', 'waiting_operator', true);
    assert.equal(classes.get('is-ended'), false);
    assert.equal(reply.innerHTML, 'Paused for operator intervention.');
    window.showRunReply('Failure', 'error', true);
    assert.equal(classes.get('is-ended'), true);
});
