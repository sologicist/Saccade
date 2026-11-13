import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { operatorResumePayload } from './operator_resume.ts';
import { restoreSelection } from './selection.ts';

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
