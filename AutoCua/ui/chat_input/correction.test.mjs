import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./chat_input.js', import.meta.url), 'utf8');

test('host clarifications use the existing user and assistant chat renderers without a run', () => {
    const ui = composer(() => null);
    const user = [], replies = [];
    let archived = 0;
    ui.window.currentSessionId = 'chat';
    ui.window.chatScroll = { archiveLive: () => { archived++; }, setLive() {}, setLiveBot() {} };
    ui.window.showUserMessage = text => user.push(text);
    ui.window.showRunReply = (html, status) => replies.push({ html, status });
    ui.window.operatorChatReply(JSON.stringify({ session_id: 'chat', answer: 'Non, pas encore', reply_html: '<p>Take your time.</p>' }));
    assert.deepEqual(user, ['Non, pas encore']);
    assert.equal(replies[0].status, 'waiting_operator');
    assert.equal(archived, 1);
    assert.equal(ui.fetches(), 0);
    ui.window.operatorChatReply(JSON.stringify({ session_id: 'other', answer: 'Done', reply_html: '<p>Foreign.</p>' }));
    assert.equal(archived, 1);
});

test('the real composer routes a paused French reply before model selection and teaching mode', async () => {
    let replies = 0, corrections = 0, models = 0;
    const ui = composer(() => { corrections++; return null; });
    ui.window.currentSessionId = 'chat';
    ui.window.getModelSelection = () => { models++; return {}; };
    ui.window.submitOperatorChat = async (text, session) => {
        replies++;
        assert.equal(text, 'Je suis connecté');
        assert.equal(session, 'chat');
        return true;
    };
    ui.input.value = 'Je suis connecté';
    ui.enter(); ui.enter();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(replies, 1);
    assert.equal(corrections, 0);
    assert.equal(models, 0);
    assert.equal(ui.fetches(), 0);
    assert.equal(ui.input.value, '');
});

test('a missing or failing reply channel cannot send a paused answer to a model', async () => {
    const ui = composer(() => { throw Error('Must not reach correction mode'); });
    ui.window.currentSessionId = 'chat';
    ui.input.value = 'Done';
    ui.enter();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(ui.fetches(), 0);
    assert.equal(ui.input.value, 'Done');
    ui.window.submitOperatorChat = () => Promise.reject(Error('offline'));
    ui.enter();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(ui.fetches(), 0);
    assert.equal(ui.input.value, 'Done');
});

function composer(handler) {
    const keys = new Map(), events = new Map();
    const input = { value: '', readOnly: false, style: {}, classList: { contains: () => false },
        addEventListener: (name, callback) => keys.set(name, callback) };
    const status = { textContent: '' };
    const send = { contentWindow: {} }, stop = { contentWindow: {} };
    const content = { querySelector: selector => selector === '.chat-input' ? input : null };
    const document = { readyState: 'complete', dispatchEvent() {}, querySelector: () => null,
        getElementById: id => ({ chatWrapper: { querySelector: () => content }, agentText: status,
            sendBtnFrame: send, stopBtnFrame: stop })[id] || null };
    let fetches = 0;
    const window = { location: { origin: 'http://127.0.0.1:12000' },
        submitDextChatCorrection: handler, getModelSelection: () => ({}),
        addEventListener: (name, callback) => events.set(name, callback) };
    vm.runInNewContext(source, { window, document, setTimeout: callback => callback(),
        CustomEvent: class {}, fetch: () => { fetches++; throw Error('Unexpected provider/run request'); } });
    return { input, status, send, window, events, fetches: () => fetches,
        enter: () => keys.get('keydown')({ key: 'Enter', shiftKey: false, preventDefault() {} }) };
}

test('explicit local correction intercepts Enter before model selection or run persistence', async () => {
    const received = [];
    const ui = composer(text => { received.push(text); return Promise.resolve(); });
    ui.input.value = 'Open invoices then confirm the workspace.';
    ui.enter();
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(received, ['Open invoices then confirm the workspace.']);
    assert.equal(ui.fetches(), 0);
    assert.equal(ui.input.value, '');
});

test('rejected correction is not sent to the agent and raw draft is not echoed in errors', async () => {
    const ui = composer(() => Promise.reject(Error('unsupported_navigation_correction')));
    ui.input.value = 'PRIVATE SYNTHETIC VALUE';
    ui.enter();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(ui.fetches(), 0);
    assert.equal(ui.input.value, 'PRIVATE SYNTHETIC VALUE');
    assert.equal(ui.status.textContent, 'unsupported_navigation_correction');
});

test('foreign or wrong-frame postMessage cannot submit an operator correction', () => {
    let calls = 0;
    const ui = composer(() => { calls++; return Promise.resolve(); });
    ui.input.value = 'Open invoices';
    const message = ui.events.get('message');
    message({ data: 'sendbtn:clicked', source: {}, origin: ui.window.location.origin });
    message({ data: 'sendbtn:clicked', source: ui.send.contentWindow, origin: 'https://app.dext.com' });
    assert.equal(calls, 0);
    assert.equal(ui.fetches(), 0);
});

test('the actual local send-frame message still submits the local correction', async () => {
    let calls = 0;
    const ui = composer(() => { calls++; return Promise.resolve(); });
    ui.input.value = 'Open invoices';
    ui.events.get('message')({ data: 'sendbtn:clicked', source: ui.send.contentWindow, origin: ui.window.location.origin });
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(calls, 1);
    assert.equal(ui.fetches(), 0);
});

test('disabled local correction mode preserves normal model selection guard', () => {
    const ui = composer(() => null);
    ui.input.value = 'Normal generic request';
    ui.enter();
    assert.equal(ui.input.value, 'Normal generic request');
    assert.equal(ui.fetches(), 0);
});

test('a second installed platform keeps the ordinary composer available during a run', () => {
    const ui = composer(() => null);
    ui.window.currentSessionId = 'portal-chat';
    ui.input.disabled = true;
    ui.window.remoteRunStarted({ task: 'Open Billing', mode: 'web', session_id: 'portal-chat',
        platform_context: { platform_id: 'synthetic_portal', execution_mode: 'supervised' } });
    assert.equal(ui.input.disabled, false);
    assert.equal(ui.window.currentSessionId, 'portal-chat');
    assert.equal(ui.fetches(), 0);
});
