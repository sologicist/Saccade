// Narrow scoped-run observation on the existing authenticated bridge. This is
// not a browser driver: Rust remains the authority for hosts and tool execution.
function createPlatformScopeObserver(chromeApi, getLines, cdp) {
  const limit = 512;
  const active = () => [...getLines()].filter((line) => line.platformScope);
  // A download policy applies to the profile. Serialize begin/protect/end so a
  // previous run cannot restore defaults after a new run has established denial.
  let transition = Promise.resolve();
  const protectedTabs = new Set();
  const ordered = async (work) => {
    const previous = transition;
    let complete;
    transition = new Promise((resolve) => { complete = resolve; });
    await previous;
    try { return await work(); }
    finally { complete(); }
  };
  const stateFor = (line, observerId) => {
    const state = line.platformScope;
    if (!state || state.id !== observerId) {
      throw new Error("Platform observation was lost or its run identifier changed; operator review is required.");
    }
    return state;
  };
  const record = (event) => {
    if (event.frameId !== undefined && event.frameId !== 0) return;
    if (typeof event.tabId !== "number" || typeof event.url !== "string") return;
    for (const line of active()) {
      const state = line.platformScope;
      if (state.events.length >= limit) state.overflow = true;
      else state.events.push({ tabId: String(event.tabId), url: event.url });
    }
  };
  for (const name of ["onBeforeNavigate", "onCommitted", "onHistoryStateUpdated", "onReferenceFragmentUpdated"]) {
    chromeApi.webNavigation?.[name]?.addListener(record);
  }
  chromeApi.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    const url = changeInfo.pendingUrl || changeInfo.url || tab?.pendingUrl;
    if (typeof url === "string" && url) record({ tabId, url });
  });
  chromeApi.downloads?.onCreated?.addListener((download) => {
    const scoped = active();
    if (!scoped.length) return;
    for (const line of scoped) {
      line.platformScope.failure = "A download was attempted in the scoped profile. Downloads are disabled; operator review is required.";
    }
    // Cancellation can race the transfer. No filename, local path, contents or
    // customer data is inspected, logged or sent across the bridge.
    chromeApi.downloads.cancel(download.id).catch(() => {});
  });
  chromeApi.debugger.onDetach.addListener((source) => {
    for (const line of active()) {
      if (line.platformScope.protected.has(source.tabId)) {
        line.platformScope.failure = "Platform download protection was detached; operator review is required.";
      }
    }
  });
  return {
    begin(line, observerId) { return ordered(async () => {
      if (typeof observerId !== "string" || !observerId || observerId.length > 128) {
        throw new Error("Invalid platform observation identifier.");
      }
      if (!chromeApi.downloads?.onCreated || !chromeApi.downloads.cancel || !chromeApi.webNavigation?.onBeforeNavigate) {
        throw new Error("The extension cannot provide mandatory platform navigation and download observation.");
      }
      if (line.platformScope) throw new Error("A platform observer is already active for this line.");
      line.platformScope = { id: observerId, events: [], overflow: false, failure: "", protected: new Set() };
      return { schema_version: 1, observer_id: observerId, tabs: await chromeApi.tabs.query({}) };
    }); },
    protect(line, observerId, tabId) { return ordered(async () => {
      const state = stateFor(line, observerId);
      if (!Number.isInteger(tabId)) throw new Error("A scoped download policy requires an exact tab id.");
      // A failed reply may follow an applied command; retain the attempted tab
      // for cleanup rather than asserting that no policy change occurred.
      protectedTabs.add(tabId);
      state.protected.add(tabId);
      try {
        await cdp(tabId, "Page.setDownloadBehavior", { behavior: "deny" });
      } catch (error) {
        state.failure = "Download denial could not be established; operator review is required.";
        throw error;
      }
      return { protected: true };
    }); },
    async observe(line, observerId) {
      const state = stateFor(line, observerId);
      const tabs = await chromeApi.tabs.query({});
      return { schema_version: 1, observer_id: state.id, tabs, events: state.events.splice(0),
        overflow: state.overflow, failure: state.failure };
    },
    end(line, observerId) { return ordered(async () => {
      const state = stateFor(line, observerId);
      delete line.platformScope;
      // Retain profile-wide denial while another scoped line is still active.
      // Only this exact observer ends; another line's queue and failure survive.
      const retained = active().length > 0;
      let failures = 0;
      if (!retained) {
        for (const tabId of [...protectedTabs]) {
          try {
            await cdp(tabId, "Page.setDownloadBehavior", { behavior: "default" });
            protectedTabs.delete(tabId);
          } catch (_) { failures += 1; }
        }
      }
      return { schema_version: 1, observer_id: state.id, ended: true,
        download_policy_restored: !retained && failures === 0,
        retained_for_active_scope: retained,
        cleanup_failure: failures
          ? "Download denial could not be fully restored. Operator review of the Chrome profile is required before using downloads."
          : "" };
    }); },
  };
}
