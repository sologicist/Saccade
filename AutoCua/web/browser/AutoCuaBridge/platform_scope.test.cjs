"use strict";

// Exercise the extension's real observer with synthetic Chrome events. No
// browser, page, account, local download or customer reference is involved.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "platform_scope.js"), "utf8");
const plain = (value) => JSON.parse(JSON.stringify(value));

function event() {
  const listeners = [];
  return {
    addListener(listener) { listeners.push(listener); },
    async emit(...args) { await Promise.all(listeners.map((listener) => listener(...args))); },
  };
}

function fixture() {
  let tabs = [{ id: 1, url: "https://app.dext.com/login", active: true }];
  let queryFailure = null;
  let cdpFailure = null;
  let cdpHook = null;
  const calls = [];
  const cancellations = [];
  const lines = new Set();
  const chrome = {
    tabs: {
      onUpdated: event(),
      async query() {
        if (queryFailure) throw queryFailure;
        return structuredClone(tabs);
      },
    },
    webNavigation: {
      onBeforeNavigate: event(),
      onCommitted: event(),
      onHistoryStateUpdated: event(),
      onReferenceFragmentUpdated: event(),
    },
    downloads: {
      onCreated: event(),
      async cancel(id) { cancellations.push(id); },
    },
    debugger: { onDetach: event() },
  };
  const context = vm.createContext({});
  vm.runInContext(source + "\nglobalThis.createObserver = createPlatformScopeObserver;", context);
  const observer = context.createObserver(chrome, () => lines.values(), async (...args) => {
    calls.push(plain(args));
    if (cdpFailure) throw cdpFailure;
    if (cdpHook) await cdpHook(...args);
  });
  return {
    chrome, lines, observer, calls, cancellations,
    line() { const line = {}; lines.add(line); return line; },
    setTabs(value) { tabs = value; },
    failQuery(error) { queryFailure = error; },
    failCdp(error) { cdpFailure = error; },
    setCdpHook(hook) { cdpHook = hook; },
  };
}

test("a transient cross-host redirect remains observable after an allowed final URL", async () => {
  const f = fixture(), line = f.line();
  const begun = plain(await f.observer.begin(line, "run-one"));
  assert.equal(begun.schema_version, 1);
  assert.equal(begun.observer_id, "run-one");
  await f.chrome.webNavigation.onBeforeNavigate.emit({ tabId: 1, frameId: 0, url: "https://identity.example.test/sign-in" });
  await f.chrome.webNavigation.onCommitted.emit({ tabId: 1, frameId: 0, url: "https://app.dext.com/" });
  f.setTabs([{ id: 1, url: "https://app.dext.com/" }]);
  const observation = plain(await f.observer.observe(line, "run-one"));
  assert.deepEqual(observation.events, [
    { tabId: "1", url: "https://identity.example.test/sign-in" },
    { tabId: "1", url: "https://app.dext.com/" },
  ]);
  assert.equal(observation.tabs[0].url, "https://app.dext.com/");
  assert.deepEqual(plain(await f.observer.observe(line, "run-one")).events, []);
});

test("pending navigation, popups and history changes retain exact tab identity", async () => {
  const f = fixture(), line = f.line();
  await f.observer.begin(line, "run-one");
  await f.chrome.tabs.onUpdated.emit(1, {}, { pendingUrl: "https://app.dext.com.evil.test/" });
  await f.chrome.tabs.onUpdated.emit(2, { url: "https://popup.example.test/" }, {});
  await f.chrome.webNavigation.onHistoryStateUpdated.emit({ tabId: 1, frameId: 0, url: "https://app.dext.com/history" });
  await f.chrome.webNavigation.onReferenceFragmentUpdated.emit({ tabId: 1, frameId: 0, url: "https://app.dext.com/history#row" });
  await f.chrome.webNavigation.onBeforeNavigate.emit({ tabId: 1, frameId: 7, url: "https://frame.example.test/" });
  f.setTabs([
    { id: 1, url: "https://app.dext.com/", pendingUrl: "https://app.dext.com.evil.test/" },
    { id: 2, url: "https://popup.example.test/" },
  ]);
  const observation = plain(await f.observer.observe(line, "run-one"));
  assert.deepEqual(observation.events.map((item) => item.tabId), ["1", "2", "1", "1"]);
  assert.equal(observation.events[0].url, "https://app.dext.com.evil.test/");
  assert.equal(observation.tabs[1].id, 2);
  assert.equal(observation.events.some((item) => item.url.includes("frame.example")), false);
});

test("navigation overflow is bounded and cannot be cleared by draining events", async () => {
  const f = fixture(), line = f.line();
  await f.observer.begin(line, "run-one");
  for (let index = 0; index < 520; index++) {
    await f.chrome.webNavigation.onBeforeNavigate.emit({ tabId: 1, frameId: 0, url: `https://app.dext.com/${index}` });
  }
  const observation = plain(await f.observer.observe(line, "run-one"));
  assert.equal(observation.events.length, 512);
  assert.equal(observation.overflow, true);
  const drained = plain(await f.observer.observe(line, "run-one"));
  assert.deepEqual(drained.events, []);
  assert.equal(drained.overflow, true);
});

test("observation identifiers are bound to a line and are lost on teardown or reconnect", async () => {
  const f = fixture(), line = f.line(), other = f.line();
  for (const id of ["", null, 7, "x".repeat(129)]) {
    await assert.rejects(f.observer.begin(line, id), /identifier/i);
  }
  await f.observer.begin(line, "run-one");
  await assert.rejects(f.observer.observe(line, "wrong-run"), /operator review/i);
  await assert.rejects(f.observer.observe(other, "run-one"), /operator review/i);
  await assert.rejects(f.observer.protect(other, "run-one", 1), /operator review/i);
  await f.observer.end(line, "run-one");
  await assert.rejects(f.observer.observe(line, "run-one"), /operator review/i);
  const reconnected = f.line();
  await assert.rejects(f.observer.observe(reconnected, "run-one"), /operator review/i);
  assert.deepEqual(f.calls, []);
});

test("draining one scoped line does not consume another line's navigation evidence", async () => {
  const f = fixture(), first = f.line(), second = f.line();
  await f.observer.begin(first, "run-one");
  await f.observer.begin(second, "run-two");
  await f.chrome.webNavigation.onBeforeNavigate.emit({ tabId: 1, frameId: 0, url: "https://identity.example.test/" });
  const one = plain(await f.observer.observe(first, "run-one"));
  const two = plain(await f.observer.observe(second, "run-two"));
  assert.deepEqual(two.events, one.events);
  assert.equal(one.observer_id, "run-one");
  assert.equal(two.observer_id, "run-two");
  assert.equal(one.events.length, 1);
});

test("downloads are cancelled and cause a sticky review state without reading private fields", async () => {
  const f = fixture(), line = f.line();
  await f.observer.begin(line, "run-one");
  const download = { id: 19 };
  for (const field of ["filename", "url", "finalUrl", "fileSize", "body"]) {
    Object.defineProperty(download, field, { get() { throw new Error(`Private download field was read: ${field}`); } });
  }
  await f.chrome.downloads.onCreated.emit(download);
  assert.deepEqual(f.cancellations, [19]);
  const observation = plain(await f.observer.observe(line, "run-one"));
  assert.match(observation.failure, /download.*operator review/i);
  assert.equal(JSON.stringify(observation).includes("filename"), false);
  assert.equal(plain(await f.observer.observe(line, "run-one")).failure, observation.failure);
});

test("generic lines receive no scoped policy, download cancellation or observation state", async () => {
  const f = fixture(), generic = f.line();
  await f.chrome.webNavigation.onBeforeNavigate.emit({ tabId: 1, frameId: 0, url: "https://generic.example.test/" });
  await f.chrome.downloads.onCreated.emit({ id: 11 });
  assert.equal(generic.platformScope, undefined);
  assert.deepEqual(f.cancellations, []);
  assert.deepEqual(f.calls, []);
  const scoped = f.line();
  await f.observer.begin(scoped, "run-one");
  await f.observer.end(scoped, "run-one");
  await f.chrome.downloads.onCreated.emit({ id: 12 });
  assert.deepEqual(f.cancellations, []);
});


test("scoped tab observation requires exact identity and stops after debugger detachment", async () => {
  const f = fixture();
  const line = f.line();

  await f.observer.begin(line, "run-one");

  // Tab identity must remain exact.
  await assert.rejects(
    f.observer.protect(line, "run-one", "1"),
    /exact tab id/i
  );

  assert.deepEqual(
    plain(await f.observer.protect(line, "run-one", 1)),
    { observed: true }
  );

  // The extension must not issue browser-level CDP commands.
  assert.deepEqual(f.calls, []);

  // Detaching an unrelated tab must not stop this observer.
  await f.chrome.debugger.onDetach.emit({ tabId: 2 });

  assert.equal(
    plain(await f.observer.observe(line, "run-one")).failure,
    ""
  );

  // Losing the watched tab's debugger requires operator review.
  await f.chrome.debugger.onDetach.emit({ tabId: 1 });

  const observation = plain(
    await f.observer.observe(line, "run-one")
  );

  assert.match(
    observation.failure,
    /debugger was detached.*operator review/i
  );

  // The failure must remain sticky.
  assert.equal(
    plain(await f.observer.observe(line, "run-one")).failure,
    observation.failure
  );
});


test("missing observation capabilities and failed tab reads never fabricate an authorized snapshot", async () => {
  const missing = fixture(), line = missing.line();
  delete missing.chrome.downloads.cancel;
  await assert.rejects(missing.observer.begin(line, "run-one"), /mandatory.*observation/i);
  assert.equal(line.platformScope, undefined);

  const disconnected = fixture(), second = disconnected.line();
  await disconnected.observer.begin(second, "run-two");
  disconnected.failQuery(new Error("Chrome observation disconnected"));
  await assert.rejects(disconnected.observer.observe(second, "run-two"), /disconnected/);
});

function automaticToolsFixture() {
  const commands = [], tabReads = [], created = [], removed = [];
  const chrome = {
    debugger: {
      onEvent: event(), onDetach: event(),
      async sendCommand(...args) { commands.push(plain(args)); return {}; },
    },
    tabs: {
      onRemoved: event(),
      async get(id) { tabReads.push(id); return null; },
      async create(options) { created.push(options); return { id: 2 }; },
      async remove(id) { removed.push(id); },
    },
  };
  const context = vm.createContext({ chrome, setTimeout, clearTimeout });
  const toolsSource = fs.readFileSync(path.join(__dirname, "tools.js"), "utf8");
  vm.runInContext(toolsSource + `
globalThis.actualTools = {
  own: (id, line) => toolsOurs.set(id, line),
  dialogHeld: (id) => toolsDialogs.has(id),
  wasReplaced: (id) => toolsReplaced.has(id),
  reopen: toolsReopen,
  setScopeReview: (handler) => { toolsOnScopeReview = handler; },
};`, context);
  return { chrome, tools: context.actualTools, commands, tabReads, created, removed };
}

test("scoped beforeunload dialogs remain unanswered and require operator review", async () => {
  const f = automaticToolsFixture();
  const line = { platformScope: { failure: "" } };
  f.tools.own(1, line);
  await f.chrome.debugger.onEvent.emit({ tabId: 1 }, "Page.javascriptDialogOpening",
    { type: "beforeunload", message: "Synthetic leave confirmation" });
  assert.match(line.platformScope.failure, /operator review.*beforeunload/i);
  assert.equal(f.tools.dialogHeld(1), true);
  assert.deepEqual(f.commands, []);
});

test("profile-wide scoped review also holds a dialog on an initial unowned tab", async () => {
  const f = automaticToolsFixture();
  const notices = [];
  f.tools.setScopeReview((tabId, message) => { notices.push([tabId, message]); return true; });
  await f.chrome.debugger.onEvent.emit({ tabId: 7 }, "Page.javascriptDialogOpening",
    { type: "beforeunload", message: "Synthetic initial page" });
  assert.equal(notices[0][0], 7);
  assert.match(notices[0][1], /operator review/i);
  assert.equal(f.tools.dialogHeld(7), true);
  assert.deepEqual(f.commands, []);
});

test("scoped crash and freeze recovery never create, navigate or close a tab", async () => {
  for (const reason of ["crashed", "froze"]) {
    const f = automaticToolsFixture();
    const line = { platformScope: { failure: "Earlier scoped violation." } };
    f.tools.own(1, line);
    await f.tools.reopen(1, reason);
    assert.equal(line.platformScope.failure, "Earlier scoped violation.");
    assert.equal(f.tools.wasReplaced(1), false);
    assert.deepEqual(f.tabReads, []);
    assert.deepEqual(f.created, []);
    assert.deepEqual(f.removed, []);
    assert.deepEqual(f.commands, []);
  }
});

test("generic automatic dialog and recovery behavior stays available", async () => {
  const f = automaticToolsFixture();
  const generic = {};
  f.tools.own(1, generic);
  f.tools.setScopeReview(() => false);
  await f.chrome.debugger.onEvent.emit({ tabId: 1 }, "Page.javascriptDialogOpening",
    { type: "beforeunload", message: "Synthetic leave confirmation" });
  assert.equal(f.tools.dialogHeld(1), false);
  assert.deepEqual(f.commands, [[{ tabId: 1 }, "Page.handleJavaScriptDialog", { accept: true }]]);
  await f.tools.reopen(1, "crashed");
  assert.equal(f.tools.wasReplaced(1), true);
  assert.deepEqual(f.tabReads, [1]);
  assert.equal(generic.platformScope, undefined);
});

test("scope teardown rejects stale identities without ending another observer", async () => {
  const f = fixture(), first = f.line(), second = f.line();
  await f.observer.begin(first, "run-one");
  await f.observer.begin(second, "run-two");
  await assert.rejects(f.observer.end(first, "run-two"), /operator review/i);
  assert.equal(first.platformScope.id, "run-one");
  assert.equal(second.platformScope.id, "run-two");
  await f.observer.end(first, "run-one");
  assert.equal(first.platformScope, undefined);
  assert.equal(second.platformScope.id, "run-two");
  await assert.rejects(f.observer.end(first, "run-one"), /operator review/i);
});



test("last scoped teardown stops observation without changing native download policy", async () => {
  const f = fixture();
  const line = f.line();

  await f.observer.begin(line, "run-one");
  await f.observer.protect(line, "run-one", 1);

  const ended = plain(
    await f.observer.end(line, "run-one")
  );

  assert.deepEqual(ended, {
    schema_version: 1,
    observer_id: "run-one",
    ended: true,
    cleanup_failure: "",
  });

  // Native Rust owns the browser-level download policy.
  // The extension must neither enable nor restore it.
  assert.deepEqual(f.calls, []);

  // After teardown, the extension must stop scoped cancellation.
  await f.chrome.downloads.onCreated.emit({ id: 17 });

  assert.deepEqual(f.cancellations, []);
  assert.equal(line.platformScope, undefined);

  // The ended observer cannot be used again.
  await assert.rejects(
    f.observer.observe(line, "run-one"),
    /operator review/i
  );
});



test("ending one observer preserves another without changing native download policy", async () => {
  const f = fixture();
  const first = f.line();
  const second = f.line();

  await f.observer.begin(first, "run-one");
  await f.observer.protect(first, "run-one", 1);

  await f.observer.begin(second, "run-two");
  await f.observer.protect(second, "run-two", 2);

  // Ending the first observer must not stop the second.
  const firstEnded = plain(
    await f.observer.end(first, "run-one")
  );

  assert.deepEqual(firstEnded, {
    schema_version: 1,
    observer_id: "run-one",
    ended: true,
    cleanup_failure: "",
  });

  assert.equal(first.platformScope, undefined);
  assert.equal(second.platformScope.id, "run-two");

  // The remaining observer must continue detecting downloads.
  await f.chrome.downloads.onCreated.emit({ id: 18 });

  assert.deepEqual(f.cancellations, [18]);

  const observation = plain(
    await f.observer.observe(second, "run-two")
  );

  assert.match(observation.failure, /download/i);

  const secondEnded = plain(
    await f.observer.end(second, "run-two")
  );

  assert.equal(secondEnded.ended, true);
  assert.equal(secondEnded.cleanup_failure, "");

  // The extension must never modify the browser-level CDP policy.
  assert.deepEqual(f.calls, []);
});



test("observer teardown succeeds after a tab read failure without modifying native download policy", async () => {
  const f = fixture();
  const line = f.line();

  await f.observer.begin(line, "run-one");
  await f.observer.protect(line, "run-one", 1);

  // A failed Chrome tab read must not produce a valid observation.
  f.failQuery(new Error("Synthetic tab observation failure"));

  await assert.rejects(
    f.observer.observe(line, "run-one"),
    /Synthetic tab observation failure/
  );

  // The observer must still be removable after the failure.
  const ended = plain(
    await f.observer.end(line, "run-one")
  );

  assert.deepEqual(ended, {
    schema_version: 1,
    observer_id: "run-one",
    ended: true,
    cleanup_failure: "",
  });

  assert.equal(line.platformScope, undefined);

  // Only native Rust may change the browser-level download policy.
  assert.deepEqual(f.calls, []);

  // Scoped download cancellation must stop after observer teardown.
  await f.chrome.downloads.onCreated.emit({ id: 19 });
  assert.deepEqual(f.cancellations, []);
});


test("automatic effects stay paused while the browser is being released", async () => {
  const f = automaticToolsFixture();
  const ending = { platformScopeEnding: true };
  f.tools.own(1, ending);
  await f.chrome.debugger.onEvent.emit({ tabId: 1 }, "Page.javascriptDialogOpening", { type: "beforeunload" });
  await f.tools.reopen(1, "crashed");
  assert.equal(f.tools.dialogHeld(1), true);
  assert.deepEqual(f.commands, []);
  assert.deepEqual(f.tabReads, []);
  assert.deepEqual(f.created, []);
});

test("observer transitions serialize without changing native download policy", async () => {
  const f = fixture();
  const first = f.line();
  const second = f.line();

  await f.observer.begin(first, "run-one");
  await f.observer.protect(first, "run-one", 1);

  const ended = f.observer.end(first, "run-one");
  const begun = f.observer.begin(second, "run-two");

  await ended;
  await begun;

  assert.equal(first.platformScope, undefined);
  assert.equal(second.platformScope.id, "run-two");
  assert.deepEqual(f.calls, []);
});

test("scoped downloads must not rely on a tab-level CDP policy", async () => {
  const f = fixture();
  const line = f.line();

  await f.observer.begin(line, "run-one");
  await f.observer.protect(line, "run-one", 1);

  assert.equal(
    f.calls.some(call => call[1] === "Page.setDownloadBehavior"),
    false,
    "Download protection must use browser-level CDP, not chrome.debugger"
  );
});