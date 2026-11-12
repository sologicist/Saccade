
"use strict";

// Observe scoped navigation and download attempts.
// Browser-level download denial is established and verified by native Rust.
function createPlatformScopeObserver(chromeApi, getLines) {
  const limit = 512;
  const active = () => [...getLines()].filter((line) => line.platformScope);

  let transition = Promise.resolve();

  const ordered = async (work) => {
    const previous = transition;
    let complete;
    transition = new Promise((resolve) => { complete = resolve; });
    await previous;
    try {
      return await work();
    } finally {
      complete();
    }
  };

  const stateFor = (line, observerId) => {
    const state = line.platformScope;
    if (!state || state.id !== observerId) {
      throw new Error(
        "Platform observation was lost or its run identifier changed; operator review is required."
      );
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

  for (const name of [
    "onBeforeNavigate",
    "onCommitted",
    "onHistoryStateUpdated",
    "onReferenceFragmentUpdated",
  ]) {
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
      line.platformScope.failure =
        "A download was attempted in the scoped profile; operator review is required.";
    }

    // Secondary defense only. Cancellation is not proof of download denial.
    // Do not read filenames, paths, contents or customer information.
    chromeApi.downloads.cancel(download.id).catch(() => {});
  });

  chromeApi.debugger.onDetach.addListener((source) => {
    for (const line of active()) {
      if (line.platformScope.watchedTabs.has(source.tabId)) {
        line.platformScope.failure =
          "Platform tab debugger was detached; operator review is required.";
      }
    }
  });

  return {
    begin(line, observerId) {
      return ordered(async () => {
        if (
          typeof observerId !== "string" ||
          !observerId ||
          observerId.length > 128
        ) {
          throw new Error("Invalid platform observation identifier.");
        }

        if (
          !chromeApi.downloads?.onCreated ||
          !chromeApi.downloads.cancel ||
          !chromeApi.webNavigation?.onBeforeNavigate
        ) {
          throw new Error(
            "The extension cannot provide mandatory platform navigation and download observation."
          );
        }

        if (line.platformScope) {
          throw new Error("A platform observer is already active for this line.");
        }

        line.platformScope = {
          id: observerId,
          events: [],
          overflow: false,
          failure: "",
          watchedTabs: new Set(),
        };

        return {
          schema_version: 1,
          observer_id: observerId,
          tabs: await chromeApi.tabs.query({}),
        };
      });
    },

    // The existing bridge operation name is retained for compatibility.
    // This registers observation only; it does NOT enable download denial.
    protect(line, observerId, tabId) {
      return ordered(async () => {
        const state = stateFor(line, observerId);

        if (!Number.isInteger(tabId)) {
          throw new Error("Platform observation requires an exact tab id.");
        }

        state.watchedTabs.add(tabId);
        return { observed: true };
      });
    },

    async observe(line, observerId) {
      const state = stateFor(line, observerId);
      const tabs = await chromeApi.tabs.query({});

      return {
        schema_version: 1,
        observer_id: state.id,
        tabs,
        events: state.events.splice(0),
        overflow: state.overflow,
        failure: state.failure,
      };
    },

    end(line, observerId) {
      return ordered(async () => {
        const state = stateFor(line, observerId);
        delete line.platformScope;

        // Native Rust owns browser-level download policy restoration.
        return {
          schema_version: 1,
          observer_id: state.id,
          ended: true,
          cleanup_failure: "",
        };
      });
    },
  };
}
