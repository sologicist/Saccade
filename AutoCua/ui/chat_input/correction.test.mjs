import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./chat_input.js', import.meta.url), 'utf8');

function composer(handler) {
    const keys = new Map(), events = new Map();
    const input = { value: '', readOnly: false, style: {}, classList: { contains: () => false },
        addEventListener: (name, callback) => keys.set(name, callback) };
    const status = { textContent: '' };
    const send = { contentWindow: {} }, stop = { contentWindow: {} };
    const content = { querySelector: selector => selector === '.chat-input' ? input : null };
    const document = { readyState: 'complete', dispatchEvent() {},
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
