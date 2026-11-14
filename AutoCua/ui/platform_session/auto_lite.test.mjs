import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

test('the composer and chat lifecycle retain generic agent modes without hidden platform controls',()=>{
    const composer=fs.readFileSync(new URL('../chat_input/chat_input.tsx',import.meta.url),'utf8');
    const requests=fs.readFileSync(new URL('../chat_input/chat_input.js',import.meta.url),'utf8');
    const chats=fs.readFileSync(new URL('../chat/chat.js',import.meta.url),'utf8');
    assert.ok(composer.includes('<AgentMode />'));
    assert.ok(requests.includes("if (agentMode === 'mobile' && !agentSub)"));
    assert.ok(requests.includes('currentSessionId'));
    for(const source of [composer,requests,chats]) {
        assert.ok(!/PlatformSessionSelector|getPlatformSelection|platformsession:|selectionPayload/.test(source));
    }
    assert.ok(requests.includes('mode: agentMode'));
});
