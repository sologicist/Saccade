import assert from 'node:assert/strict';
import test from 'node:test';
import { chooseExecutionMode, choosePlatform, newSelection, restoreSelection, selectionPayload } from './selection.ts';

const platforms = [{ id: 'synthetic', name: 'Synthetic platform' }];

test('registered selection is dynamic and defaults to supervised', () => {
    const state = choosePlatform(newSelection(), 'synthetic', platforms);
    assert.deepEqual(selectionPayload(state, 'web'), { platform_id: 'synthetic', execution_mode: 'supervised' });
    assert.throws(() => choosePlatform(newSelection(), 'unknown', platforms));
});

test('generic and non-Web requests preserve their existing behavior', () => {
    assert.deepEqual(selectionPayload(newSelection(), 'web'), { platform_id: null });
    assert.deepEqual(selectionPayload(choosePlatform(newSelection(), 'synthetic', platforms), 'computer'), {});
});

test('auto requires a separate explicit choice and a new platform resets it', () => {
    const scoped = choosePlatform(newSelection(), 'synthetic', platforms);
    const auto = chooseExecutionMode(scoped, 'auto');
    assert.equal(auto.executionMode, 'auto');
    assert.equal(choosePlatform(auto, '', platforms).executionMode, 'supervised');
    assert.throws(() => chooseExecutionMode(scoped, 'invalid'));
});

test('started or restored chats cannot silently change platform or mode', () => {
    const saved = restoreSelection({ platform_id: 'synthetic', execution_mode: 'auto' }, true);
    assert.equal(choosePlatform(saved, '', platforms), saved);
    assert.equal(chooseExecutionMode(saved, 'supervised'), saved);
    const busy = { ...choosePlatform(newSelection(), 'synthetic', platforms), busy: true };
    assert.equal(choosePlatform(busy, '', platforms), busy);
    assert.equal(chooseExecutionMode(busy, 'auto'), busy);
});

test('loading or invalid saved context cannot silently downgrade to generic', () => {
    assert.throws(() => selectionPayload({ ...newSelection(), restoring: true }, 'web'));
    assert.throws(() => selectionPayload({ ...newSelection(), error: 'Invalid saved context.' }, 'web'));
    for (const context of [undefined, {}, { platform_id: '../dext', execution_mode: 'auto' }, { platform_id: 'dext', execution_mode: 'invalid' }]) {
        assert.throws(() => restoreSelection(context, true));
    }
});
