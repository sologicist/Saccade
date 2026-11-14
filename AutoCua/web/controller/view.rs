//! route_action — the browser agent's hands.
//!
//! Takes the `[{type, ...}]` action dicts the model's native tool calls were
//! converted into, and carries each one out. Return shapes are NOT free-form:
//! the agent loop keys on specific fields, so they are fixed contracts —
//!
//!     done        -> {"action": "done", "summary": ...}      ends the loop
//!     wait        -> {"tool": "wait", "duration": N}          sets the inter-step delay
//!     todo_list   -> {"action": "todo_created"}
//!     update_todo -> {"action": "todo_updated"}
//!     a batch     -> {"action": "multiple", "results": [...]} one entry PER action,
//!                                                             in order, so the loop can
//!                                                             pair each result to the
//!                                                             tool call that produced it
//!
//! That last one is load-bearing: `_pair_results` in the agent only pairs
//! per-call when len(results) == len(calls), so every action must contribute
//! exactly one result, failures included.

use std::sync::{Arc, Mutex};

use pyo3::prelude::*;
use serde_json::{json, Map, Value};

use super::service::{ActErr, ControllerService};
use super::{
    click, dialog, done, input, keyboard, run_script, scratchpad, scroll, skills, tab, todo_tracker, vault, wait,
};
use crate::browser::{truthy, web_store_url, BrowserScanner, ScannerInner, WEB_STORE_BLOCKED};
use crate::agent::main_driver::view::py_str_of;

/// The page actions a popup (a JavaScript alert, confirm or prompt) holding the
/// current tab freezes (see `one`). run_script
/// is not here: it can name another tab, and one into a held tab is refused below it.
const HELD_BY_POPUP: [&str; 9] =
    ["click", "hold_click", "input", "vault", "keyboard", "scroll", "update_tab", "navigate_tab", "more"];

/// The page actions refused on a tab that is on the Chrome Web Store (see `one`); the
/// tab tools are how it is left.
const ON_THE_PAGE: [&str; 6] = ["click", "hold_click", "input", "vault", "keyboard", "scroll"];

/// Routes one step's actions against the live browser.
pub struct ControllerView {
    business: Mutex<Option<crate::tool_registry::business::BusinessGate>>,
    automatic_business: Mutex<bool>,
    active_business_platform: Mutex<Option<String>>,
    google_runtime: Mutex<Option<(String,String,Option<String>)>>,
    download_operation: Mutex<Option<(String,u64)>>,
    /// The scanner owns the CDP connection, so every page action has to go
    /// through it — there is no second channel to the browser.
    scanner: Arc<Mutex<ScannerInner>>,
    stop_event: Option<Py<PyAny>>,
    /// Parallel-run mode: this agent drives exactly ONE dedicated tab, so the
    /// tab-lifecycle tools (new_tab/switch_tab/close_tab) are refused here as
    /// a backstop for providers that don't enforce the tool registry.
    single_tab: bool,
    pub controller_service: ControllerService,
    pub todo_tracker: todo_tracker::service::TodoTrackerService,
    pub scratchpad_service: scratchpad::service::ScratchpadService,
    /// The ids from the scan the model was just shown — replaced per step by
    /// set_elements.
    state: Mutex<ElementsState>,
}

struct ElementsState {
    elements: Map<String, Value>,
}

impl ControllerView {
    /// `web_dir` is AutoCua/web — where the scratchpad/todo files live.
    /// `session_id` scopes them to scratchpad/{sid}/ so parallel agents never
    /// share notes; `single_tab` marks a parallel agent pinned to one tab.
    pub fn new(
        web_dir: &std::path::Path,
        session_id: Option<&str>,
        single_tab: bool,
        scanner: Arc<Mutex<ScannerInner>>,
        stop_event: Option<Py<PyAny>>,
    ) -> std::io::Result<Self> {
        let scratchpad_base = match session_id {
            Some(sid) => web_dir.join("scratchpad").join(sid),
            None => web_dir.join("scratchpad"),
        };
        Ok(ControllerView {
            business: Mutex::new(None),
            automatic_business: Mutex::new(true),
            active_business_platform: Mutex::new(None),
            google_runtime: Mutex::new(None),
            download_operation: Mutex::new(None),
            scanner,
            stop_event,
            single_tab,
            controller_service: ControllerService,
            todo_tracker: todo_tracker::service::TodoTrackerService::new(&scratchpad_base)?,
            scratchpad_service: scratchpad::service::ScratchpadService::new(&scratchpad_base)?,
            state: Mutex::new(ElementsState { elements: Map::new() }),
        })
    }

    // ------------------------------------------------------------------ setup

    pub fn configure_business(&self, py: Python<'_>, context: Option<&Bound<'_, PyAny>>) -> PyResult<()> {
        *self.automatic_business.lock().unwrap() = context.is_none();
        *self.active_business_platform.lock().unwrap() = None;
        let gate = match context {
            Some(context) => {
                let value: Value = pythonize::depythonize(context)?;
                if value["platform_id"] == "dext" && value["execution_mode"] == "supervised" {
                    Some(crate::tool_registry::business::BusinessGate::new(py, context)?)
                } else { None }
            }
            None => None,
        };
        *self.business.lock().unwrap() = gate;
        Ok(())
    }

    pub fn refresh_business(&self, py: Python<'_>) -> PyResult<Option<Value>> {
        if *self.automatic_business.lock().unwrap() {
            let url = self.scanner.lock().unwrap().url.clone();
            let module = py.import("AutoCua.saccade.automatic_platform")?;
            let platform: Option<String> = module.call_method1("detect_platform", (&url,))?.extract()?;
            let mut active = self.active_business_platform.lock().unwrap();
            if *active != platform {
                *self.business.lock().unwrap() = None;
                *active = None;
                if let Some(id) = platform.as_ref() {
                    let run = module.call_method1("business_for_platform", (id,))?;
                    if !run.is_none() {
                        *self.business.lock().unwrap() = Some(crate::tool_registry::business::BusinessGate::automatic(run.unbind()));
                    }
                }
                *active = platform;
            }
        }
        let automatic = *self.automatic_business.lock().unwrap();
        let business = self.business.lock().unwrap();
        if automatic {
            if let (Some(gate),Some((provider,model,key))) = (business.as_ref(),self.google_runtime.lock().unwrap().as_ref()) {
                gate.configure_google(py,provider,model,key.as_deref())?;
            }
        }
        business.as_ref().map(|gate| gate.refresh(py)).transpose()
    }

    pub fn configure_google_runtime(&self, provider: &str, model: &str, key: Option<&str>) {
        *self.google_runtime.lock().unwrap() = Some((provider.into(),model.into(),if provider == "google" {key.map(str::to_owned)} else {None}));
    }

    #[cfg(test)]
    pub fn business_fixture(&self, run: Py<PyAny>) {
        *self.automatic_business.lock().unwrap() = false;
        *self.business.lock().unwrap() = Some(crate::tool_registry::business::BusinessGate::from_fixture(run));
    }

    fn call_business(&self, py: Python<'_>, action: &Value) -> PyResult<Value> {
        let automatic = *self.automatic_business.lock().unwrap();
        if automatic {
            self.check_download(py, &mut json!({}))?;
            // Reobserve before dispatch; never refresh a stale model selection
            // into new authority or attach a single-site browser scope.
            let observed = super::service::scan_op(py, &self.scanner, |scanner| {
                scanner.scan_core()?;
                Ok(scanner.url.clone())
            });
            let url = match observed {
                Ok(url) => url,
                Err(_) => return Ok(json!({"status":"error","tool":"call_function",
                    "code":"business_observation_unavailable","operator_review_required":true})),
            };
            let platform: Option<String> = py.import("AutoCua.saccade.automatic_platform")?
                .call_method1("detect_platform", (&url,))?.extract()?;
            if platform.is_none() || platform != *self.active_business_platform.lock().unwrap() {
                *self.business.lock().unwrap() = None;
                *self.active_business_platform.lock().unwrap() = None;
                return Ok(crate::tool_registry::business::denied());
            }
        }
        let business = self.business.lock().unwrap();
        let Some(gate) = business.as_ref() else { return Ok(crate::tool_registry::business::denied()) };
        let permit = match gate.authorize(py, action) {
            Ok(permit) => permit,
            Err(error) => return Ok(crate::tool_registry::business::denied_error(py, &error)),
        };
        if let Err(error) = super::service::scan_op(py, &self.scanner, |scanner| {
            if automatic { scanner.check_platform_scope() } else { scanner.authorize_business_action(action, &permit) }
        }) {
            return match error {
                ActErr::Py(error) => Err(error),
                ActErr::Msg(_) => Ok(crate::tool_registry::business::denied()),
            };
        }
        match gate.execute(py, permit, self.stop_event.as_ref()) {
            Ok(value) => Ok(value),
            Err(error) if error.is_instance_of::<pyo3::exceptions::PyKeyboardInterrupt>(py) => Err(error),
            Err(_) => Ok(crate::tool_registry::business::denied()),
        }
    }

    /// Hand over the ids from the scan the model was just shown. The app-name
    /// parameter is accepted for signature parity with the mac/ios controllers
    /// and unused here — nothing web-side ever read it.
    pub fn set_elements(&self, elements_mapping: Map<String, Value>, _application_name: &str) {
        self.state.lock().unwrap().elements = elements_mapping;
    }

    // ---------------------------------------------------------------- helpers

    fn stopped(&self, py: Python<'_>) -> PyResult<bool> {
        match &self.stop_event {
            Some(ev) => ev.bind(py).call_method0("is_set")?.is_truthy(),
            None => Ok(false),
        }
    }

    /// Keep policy failures in the normal one-result-per-call protocol. The
    /// scanner latches scoped violations so the native loop stops for review.
    fn platform_check(&self, py: Python<'_>, action: Option<&Value>) -> PyResult<Option<Value>> {
        let action = action.cloned();
        let tool = action.as_ref().and_then(|a| a.get("type")).cloned().unwrap_or(Value::Null);
        let checked = super::service::scan_op(py, &self.scanner, move |scanner| {
            match action {
                Some(action) => scanner.authorize_platform_action(&action),
                None => scanner.check_platform_scope(),
            }
        });
        match checked {
            Ok(()) => Ok(None),
            Err(ActErr::Msg(message)) => Ok(Some(json!({
                "status": "error", "tool": tool, "message": message,
                "operator_review_required": true,
            }))),
            Err(ActErr::Py(error)) => Err(error),
        }
    }

    fn check_download(&self, py: Python<'_>, result: &mut Value) -> PyResult<()> {
        let operation = self.download_operation.lock().unwrap().clone();
        let Some((tab,started)) = operation else { return Ok(()) };
        let observed = super::service::scan_op(py, &self.scanner, |scanner| {
            if scanner.current_target_id().ok().as_deref() != Some(tab.as_str()) {
                return Err(crate::browser::ScanErr::s("Download observation tab changed"));
            }
            scanner.bridge_call(json!({"type":"download_status","download_operation":started.to_string()}))
        });
        let observation = match observed {
            Ok(reply) if reply["download"]["state"].is_string() => reply["download"].clone(),
            _ => json!({"state":"observation_unavailable","operation":started.to_string()}),
        };
        // Native operation identity is never accepted from model arguments.
        if observation["operation"] != started.to_string() {
            if let Some(gate) = self.business.lock().unwrap().as_ref() { gate.invalidate_download(py,started)?; }
            result["download"] = json!({"state":"observation_unavailable"});
            return Ok(());
        }
        result["download"] = observation;
        let automatic = *self.automatic_business.lock().unwrap();
        let business = self.business.lock().unwrap();
        let gate = if automatic { business.as_ref() } else { None };
        // Consume Chrome's path privately, before the tool result reaches the
        // model. This is a folder hint from the actual completed download, not
        // a new downloader or model-selected filesystem authority.
        if result["download"]["state"] == "complete" {
            let path = result["download"]["absolute_path"].as_str().map(str::to_owned);
            if let Some(download) = result["download"].as_object_mut() { download.remove("absolute_path"); }
            let pdf = result["download"]["filename"].as_str().is_some_and(|name|name.to_lowercase().ends_with(".pdf"));
            if let Some(gate) = gate {
                if let Some(path) = path.filter(|_|pdf) {
                    if gate.note_download(py,&path,started).is_err() {
                        gate.invalidate_download(py,started)?;
                        result["download"] = json!({"state":"file_verification_failed"});
                    }
                } else {
                    gate.invalidate_download(py,started)?;
                }
            }
        } else if !matches!(result["download"]["state"].as_str(),Some("not_observed"|"in_progress")) {
            if let Some(gate) = gate { gate.invalidate_download(py,started)?; }
        }
        if let Some(download) = result["download"].as_object_mut() {
            download.remove("operation");
            download.remove("absolute_path");
        }
        Ok(())
    }

    fn check_after_settle(&self, py: Python<'_>, result: &mut Value) -> PyResult<()> {
        self.check_download(py,result)?;
        if let Some(mut failure) = self.platform_check(py, None)? {
            failure["tool"] = result.get("tool").cloned().unwrap_or(Value::Null);
            *result = failure;
        }
        Ok(())
    }

    /// After a page action that succeeded, wait until the page has taken it:
    /// the page's own pace, not the clock's (see settle_after_action).
    ///
    /// After EVERY page action — the last one of a batch and a lone one
    /// included, not only between the actions of a batch, which is how this
    /// started. The scan that follows a step reads the page the moment the
    /// step returns, and the scanner's own settle counts network requests
    /// only. A dialog that closes with nothing in flight — Google Flights'
    /// date picker keeps its full layout for ~300ms after Done while the
    /// button's ripple plays, then goes display:none — was still in the DOM
    /// snapshot and already gone from the screenshot taken a moment later.
    /// The model was handed the tree of a page that no longer existed, and
    /// clicked "Done. Search for one-way flights…" on a spot that was the
    /// map by then. An idle page answers in about a tenth of a second; the
    /// scan itself is untouched.
    fn settle_after(&self, py: Python<'_>, result: &Value) {
        let ok = result.get("status").and_then(Value::as_str) == Some("success");
        let tool = result.get("tool").and_then(Value::as_str).unwrap_or("");
        if !ok
            || !matches!(tool, "click" | "hold_click" | "input" | "vault" | "keyboard" | "scroll" | "run_script" | "dialog")
        {
            return;
        }
        // Nothing reads the page after a Stop, so waiting on it only delays
        // the stop — by up to the cap on a page that never goes quiet.
        if self.stopped(py).unwrap_or(false) {
            return;
        }
        super::service::settle_after_action(py, &self.scanner);
    }

    // ----------------------------------------------------------------- routing

    /// Execute this step's actions in order. Never returns a tool failure as
    /// an error — a failed action becomes a failed RESULT so the model sees
    /// it and can recover. (A raised Python error — KeyboardInterrupt — still
    /// flies, exactly as it did through Python's `except Exception`.)
    pub fn route_action(&self, py: Python<'_>, actions: &Value) -> PyResult<Value> {
        let actions: Vec<Value> = match actions {
            Value::Object(_) => vec![actions.clone()],
            Value::Array(items) => items.clone(),
            _ => Vec::new(),
        };

        if actions.len() > 1 && actions.iter().any(|a| a["type"] == "call_function") && actions.iter().any(|a| a["type"] == "done") {
            return Ok(json!({"status":"error", "action":"multiple", "results": actions.iter().map(|a|
                json!({"status":"not_run", "tool":a["type"], "code":"done_must_be_alone"})).collect::<Vec<_>>()}));
        }
        if actions.len() == 1 {
            let (mut result, opened) = self.one(py, &actions[0])?;
            // A page frozen by the popup this action opened has nothing to settle.
            if !opened {
                self.settle_after(py, &result);
            }
            self.check_after_settle(py, &mut result)?;
            return Ok(result);
        }

        let mut results: Vec<Value> = Vec::new();
        let mut failed_at: Option<usize> = None;
        // The action that opened a popup: the page is frozen behind it, so the rest
        // of the batch waits for the model's answer.
        let mut popup_at: Option<usize> = None;
        for (n, action) in actions.iter().enumerate() {
            let n = n + 1;
            if self.stopped(py)? {
                results.push(json!({
                    "status": "stopped",
                    "tool": action.get("type").cloned().unwrap_or(Value::Null),
                    "message": "stopped by user",
                }));
                continue;
            }
            if let Some(failed) = failed_at {
                // Everything after a failure is reported, never silently
                // dropped: the loop pairs results to tool calls one-for-one
                // and a short list breaks the transcript. Saying WHICH action
                // broke the chain also tells the model why its later steps
                // did not happen.
                let failed_tool = results[failed - 1].get("tool").cloned().unwrap_or(Value::Null);
                let reason = if results[failed - 1].get("operator_review_required").and_then(Value::as_bool) == Some(true) {
                    "the review requirement for"
                } else { "the failure of" };
                results.push(json!({
                    "status": "not_run",
                    "tool": action.get("type").cloned().unwrap_or(Value::Null),
                    "message": format!(
                        "not run - stopped by {reason} action {failed} \
                         ({}). The page may have \
                         changed, so re-read the latest element_tree before retrying.",
                        py_str_of(&failed_tool)
                    ),
                }));
                continue;
            }
            if let Some(at) = popup_at {
                results.push(json!({
                    "status": "not_run",
                    "tool": action.get("type").cloned().unwrap_or(Value::Null),
                    "message": format!(
                        "not run - action {at} opened a popup that freezes the page until it \
                         is answered: answer it first (see <dialog> in the next input)"
                    ),
                }));
                continue;
            }
            let (mut result, opened) = self.one(py, action)?;
            let ok_so_far = result.get("status").and_then(Value::as_str) == Some("success");
            let tool = result.get("tool").and_then(Value::as_str).unwrap_or("").to_string();
            if ok_so_far && tool == "wait" {
                // A `wait` inside the batch sleeps here, where it was asked
                // for. One that ENDS the batch is slept by the agent loop
                // instead, which keeps checking the stop event as it goes.
                if n < actions.len() {
                    let secs = result.get("duration").and_then(Value::as_f64).unwrap_or(0.0).max(0.0);
                    let mut left = secs;
                    while left > 0.0 {
                        if self.stopped(py)? {
                            break;
                        }
                        let chunk = left.min(0.25);
                        py.detach(|| std::thread::sleep(std::time::Duration::from_secs_f64(chunk)));
                        left -= chunk;
                    }
                }
            } else if !opened {
                // Every page action is followed by a settle, the LAST one of
                // the batch included: whatever comes next — the next action,
                // or the scan — assumes the page has taken this one.
                self.settle_after(py, &result);
            }
            self.check_after_settle(py, &mut result)?;
            // A batch is a chain: each action assumes the page the previous
            // one left behind. Running on past a failure acts on a page that
            // never arrived, with ids resolved against a scan that is now
            // wrong.
            let ok = result.get("status").and_then(Value::as_str) == Some("success")
                && !(tool == "call_function" && result.get("operator_review_required").and_then(Value::as_bool) == Some(true));
            results.push(result);
            if !ok {
                failed_at = Some(n);
            }
            if opened {
                popup_at = Some(n);
            }
        }

        // "stopped" has to surface on the envelope too — the loop checks the
        // top-level status to decide whether the run was interrupted.
        let status = if results
            .iter()
            .any(|r| r.get("status").and_then(Value::as_str) == Some("stopped"))
        {
            "stopped"
        } else if failed_at.is_some() {
            "error"
        } else {
            "success"
        };
        Ok(json!({"status": status, "action": "multiple", "results": results}))
    }

    /// Run the tool, then tell the truth about what else happened.
    ///
    /// A dialog that blocked the page, a renderer that died — these arrive on
    /// the socket while a tool is running and used to go nowhere. The tool
    /// then answered "clicked [3]" and the model had no way to know why the
    /// page it saw next made no sense. Appending them here covers every tool
    /// at once, including the early-return branches inside `one_inner`.
    ///
    /// Also returns whether the action opened a popup (a JavaScript alert, confirm
    /// or prompt): the page is frozen behind it until the model answers it, which
    /// the next input shows as `<dialog>`.
    fn one(&self, py: Python<'_>, action: &Value) -> PyResult<(Value, bool)> {
        if action.get("type").and_then(Value::as_str) == Some("call_function") {
            if self.stopped(py)? {
                return Ok((json!({"status":"stopped", "tool":"call_function"}), false));
            }
            if let Some(mut failure) = self.platform_check(py, None)? {
                failure["tool"] = json!("call_function");
                return Ok((failure, false));
            }
            return Ok((self.call_business(py, action)?, false));
        }
        // All model tools, including unknown or bookkeeping calls, reach this
        // boundary before any browser side effect or completion result.
        if let Some(failure) = self.platform_check(py, Some(action))? {
            return Ok((failure, false));
        }
        // What the page did before this action — while the model was
        // thinking, or during an earlier action of the batch, a page load
        // included — is not this action's doing, and must not hold the scan.
        super::service::scan_op(py, &self.scanner, |s| {
            s.begin_action();
            Ok(())
        })
        .ok();
        let kind = action.get("type").map(py_str_of).unwrap_or_default().trim().to_string();
        // A popup holding the current tab freezes its page: an action on it would wait
        // for nothing, so it is refused, and the model answers the popup first.
        let held = super::service::scan_op(py, &self.scanner, |s| Ok(s.open_dialog()))
            .ok()
            .flatten();
        if held.is_some() && HELD_BY_POPUP.contains(&kind.as_str()) {
            let refused = json!({"status": "error", "tool": kind, "message": crate::browser::DIALOG_OPEN});
            return Ok((refused, false));
        }
        // A tab that got onto the Chrome Web Store anyway (a redirect, a script) takes
        // no page action and runs no script, in either mode (the owner's rule): it can
        // only be left. Where the tab is now is asked of the browser (one cheap call):
        // the last scan can be a step behind a page that moved since.
        let store = super::service::scan_op(py, &self.scanner, |s| {
            let tab = if ON_THE_PAGE.contains(&kind.as_str()) {
                s.current_target_id().ok()
            } else if kind == "run_script" {
                // The tab run_script will run in: its [n] read as the tool reads it.
                action
                    .get("id")
                    .and_then(|id| super::service::py_int_value(id).ok())
                    .and_then(|n| s.listed_tab(n))
            } else {
                None
            };
            Ok(tab.is_some_and(|id| web_store_url(&s.tab_url_now(&id))))
        })
        .unwrap_or(false);
        if store {
            let message = format!("{WEB_STORE_BLOCKED}. Leave it with navigate_tab back, update_tab or new_tab");
            return Ok((json!({"status": "error", "tool": kind, "message": message}), false));
        }
        let operation = if matches!(kind.as_str(),"click"|"hold_click") && *self.automatic_business.lock().unwrap() {
            let started = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default().as_nanos() as u64;
            let tab = self.scanner.lock().unwrap().current_target_id().ok();
            if let Some(tab) = tab {
                *self.download_operation.lock().unwrap() = Some((tab,started));
                if let Some(gate) = self.business.lock().unwrap().as_ref() { gate.begin_download(py,started)?; }
                Some(started)
            } else { None }
        } else { None };
        let mut result = self.one_inner(py, action, operation)?;
        // Where the tabs are now, in case the browser goes away before the
        // next scan (ScannerInner::revive reopens them).
        super::service::scan_op(py, &self.scanner, |s| {
            s.note_tabs();
            Ok(())
        })
        .ok();
        let notes: Vec<String> =
            super::service::scan_op(py, &self.scanner, |s| Ok(s.take_notices()))
                .unwrap_or_default();
        if !notes.is_empty() {
            let base = result
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                .to_string();
            let joined = notes.join(" ");
            let message = if base.is_empty() {
                joined
            } else {
                format!("{base} Note: {joined}")
            };
            if let Some(obj) = result.as_object_mut() {
                obj.insert("message".into(), Value::String(message));
            }
        }
        // A popup this action opened (a click on "Delete", an Enter on a form), one it
        // moved onto (switch_tab to a held tab), or the next one a page opened the
        // moment `dialog` answered the last: the action is done, and the page waits
        // for the model's answer. A tool cut short by it reads the same.
        let mut opened = false;
        // `dialog` looks only after an answer that went through: one that failed
        // (no such button) leaves the same popup open, which is no news.
        let answered = result.get("status").and_then(Value::as_str) == Some("success");
        let look = if kind == "dialog" { answered } else { held.is_none() };
        if look {
            let popup = super::service::scan_op(py, &self.scanner, |s| Ok(s.open_dialog()))
                .ok()
                .flatten();
            if let Some(popup) = popup {
                opened = true;
                let field = |k: &str| popup.get(k).and_then(Value::as_str).unwrap_or("").trim().to_string();
                let note = format!(
                    "A JavaScript {} saying \"{}\" is now open on the page, which is frozen \
                     until it is answered: the next input shows it as <dialog>, to answer with \
                     `dialog`.",
                    field("type"),
                    field("message")
                );
                let ok = result.get("status").and_then(Value::as_str) == Some("success");
                let base = result.get("message").and_then(Value::as_str).unwrap_or("").trim().to_string();
                let message = if ok && !base.is_empty() {
                    format!("{base}. {note}")
                } else {
                    format!("{kind} was cut short by a popup. {note}")
                };
                if let Some(obj) = result.as_object_mut() {
                    obj.insert("status".into(), json!("success"));
                    obj.insert("message".into(), Value::String(message));
                }
            }
        }
        // A value the vault typed can come back in any result (a script that
        // reads the form, a label that holds it): it reads as [vault]. Not in
        // `done`: that is the model's own answer to the user, not the page's.
        if kind != "done" {
            vault::service::hide_json(&mut result);
        }
        self.check_after_settle(py, &mut result)?;
        Ok((result, opened))
    }

    fn one_inner(&self, py: Python<'_>, action: &Value, operation: Option<u64>) -> PyResult<Value> {
        let kind = action
            .get("type")
            .filter(|v| truthy(v))
            .map(|v| py_str_of(v).trim().to_string())
            .unwrap_or_default();
        let elements = self.state.lock().unwrap().elements.clone();
        let get = |key: &str| action.get(key).cloned().unwrap_or(Value::Null);
        let sc = &self.scanner;

        // Single-tab agents have no tab lifecycle. The tools are already
        // absent from their registry; this arm catches non-strict providers
        // that emit the name anyway.
        if self.single_tab && matches!(kind.as_str(), "new_tab" | "switch_tab" | "close_tab") {
            return Ok(json!({
                "status": "error", "tool": kind,
                "message": "this session drives a single dedicated tab - there are no \
                            tab tools here. Navigate the current tab with `update_tab` \
                            (url) or `navigate_tab` (back/forward/reload) instead.",
            }));
        }

        let outcome = match kind.as_str() {
            // ------------------------------------------------- page actions
            "new_tab" => tab::service::open_new(py, sc, &get("value")),
            "switch_tab" => tab::service::switch(py, sc, &get("id")),
            "close_tab" => tab::service::close(py, sc, &get("id")),
            "update_tab" => tab::service::update(py, sc, &get("value")),
            "navigate_tab" => tab::service::navigate(py, sc, &get("value")),
            "click" => click::service::click(py, sc, &get("id"), &get("times"), &elements, operation),
            "hold_click" => {
                click::service::hold_click(py, sc, &get("id"), &get("time"), &elements, operation)
            }
            "input" => input::service::type_into(
                py, sc, &get("id"), &get("value"), &get("enter"), &elements,
            ),
            "vault" => vault::service::fill(py, sc, &get("id"), &get("value"), &elements),
            "keyboard" => keyboard::service::shortcut(py, sc, &get("value")),
            "dialog" => dialog::service::answer(py, sc, &get("id"), &get("value")),
            // run_script: each `type` goes to its own door in the run_script
            // folder. It arrives as `script_type`: the action's own `type` is
            // the tool's name (tool_calls_to_steps).
            "run_script" => match py_str_of_or_empty(&get("script_type")).trim().to_lowercase().as_str() {
                "action" => run_script::service::action(py, sc, &get("id"), &get("value")),
                "scrape" => run_script::service::scrape(py, sc, &get("id"), &get("value")),
                _ => Err(ActErr::Msg(
                    "run_script's `type` is \"action\" (do something in the page) or \"scrape\" (read data out of it)"
                        .to_string(),
                )),
            },
            // Scrape mode, which a run_script scrape opened: the next three
            // screens with the same script, the index that keeps a chunk, and
            // the way out. `index_read` brings a stored index back, on the
            // page steps.
            // A skill into <skills>, or out of it. Its `type` travels as
            // `script_type` like run_script's (tool_calls_to_steps).
            "skills" => skills::service::run(&get("script_type"), &get("id")),
            "more" => run_script::service::more(py, sc),
            "index" => run_script::service::index(py, sc, &get("title"), &get("pending"), &get("value")),
            "index_read" => run_script::service::index_read(&get("id")),
            "exit_scrape_mode" => run_script::service::exit_scrape_mode(&get("value")),
            "scroll" => scroll::service::scroll(py, sc, &get("id"), &get("direction"), &elements),
            "wait" => wait::service::wait(&get("value")),
            // -------------------------------------------------- bookkeeping
            "scratchpad" => {
                let value = py_str_of_or_empty(&get("value")).trim().to_string();
                if value.is_empty() {
                    Ok(json!({"status": "error", "tool": "scratchpad",
                              "message": "empty scratchpad entry"}))
                } else {
                    let ok = self.scratchpad_service.append_scratchpad(&value);
                    Ok(json!({
                        "status": if ok { "success" } else { "error" },
                        "tool": "scratchpad",
                        "message": if ok { "recorded" } else { "could not write the scratchpad" },
                    }))
                }
            }
            "todo_list" => {
                let value = py_str_of_or_empty(&get("value")).trim().to_string();
                let ok = self.todo_tracker.save_todo(&value);
                Ok(json!({
                    "status": if ok { "success" } else { "error" },
                    "action": if ok { json!("todo_created") } else { Value::Null },
                    "tool": "todo_list",
                    "message": if ok { "todo list saved" } else { "could not write the todo list" },
                }))
            }
            "update_todo" => {
                let raw = py_str_of_or_empty(&get("value")).trim().to_string();
                let digits: String = raw.chars().filter(|c| c.is_ascii_digit()).collect();
                if digits.is_empty() {
                    Ok(json!({"status": "error", "tool": "update_todo",
                              "message": format!("'{raw}' has no task number in it")}))
                } else {
                    let num: i64 = digits.parse().unwrap_or(i64::MAX);
                    // A ToDo has to exist before a task can be marked. Saying
                    // WHICH thing is missing turns a dead end into a step the
                    // model can recover from.
                    if !self.todo_tracker.todo_file.exists() {
                        Ok(json!({"status": "error", "tool": "update_todo",
                                  "message": format!(
                                      "no todo list exists yet, so there is no task \
                                       #{num} to mark - call `todo_list` first, \
                                       then update it.")}))
                    } else {
                        let ok = self.todo_tracker.update_task(num);
                        Ok(json!({
                            "status": if ok { "success" } else { "error" },
                            "action": if ok { json!("todo_updated") } else { Value::Null },
                            "tool": "update_todo",
                            "message": if ok {
                                format!("task #{num} marked complete")
                            } else {
                                format!("could not mark task #{num} complete")
                            },
                        }))
                    }
                }
            }
            // --------------------------------------------------- completion
            "done" => {
                // The agent is letting go of the browser, so the pointer that
                // says it is holding it comes off the page. Best-effort and
                // ignored on failure: the run has ENDED, and a cursor that
                // will not fade is no reason to fail the summary that tells
                // the user what happened.
                super::service::scan_op(py, sc, |s| {
                    s.cursor_hide();
                    Ok(())
                })
                .ok();
                done::service::finish(&get("value"))
            }
            _ => Ok(json!({"status": "error", "tool": kind,
                           "message": format!("no handler for action '{kind}'")})),
        };

        match outcome {
            Ok(v) => Ok(v),
            Err(ActErr::Msg(message)) => Ok(json!({
                "status": "error", "tool": kind, "message": message,
            })),
            Err(ActErr::Py(e)) => Err(e),
        }
    }
}

/// Python `str(x or "")`.
fn py_str_of_or_empty(v: &Value) -> String {
    if truthy(v) {
        py_str_of(v)
    } else {
        String::new()
    }
}

// ---------------------------------------------------------------------------
// Test hook — routes actions through a fresh ControllerView wired to an
// existing scanner, using that scanner's current element mapping. Exists so
// the controller can be exercised (and differentially tested) from Python
// without the whole agent loop.
// ---------------------------------------------------------------------------

#[pyfunction]
#[pyo3(signature = (scanner, actions, application_name=None))]
pub fn _route_action_debug<'py>(
    py: Python<'py>,
    scanner: Py<BrowserScanner>,
    actions: Bound<'py, PyAny>,
    application_name: Option<String>,
) -> PyResult<Bound<'py, PyAny>> {
    let web_dir = crate::web_dir(py)?.clone();
    let inner = scanner.get().inner.clone();
    let view = ControllerView::new(&web_dir, None, false, inner.clone(), None)
        .map_err(|e| pyo3::exceptions::PyIOError::new_err(e.to_string()))?;
    let mapping = {
        let guard = inner
            .lock()
            .map_err(|_| pyo3::exceptions::PyRuntimeError::new_err("scanner state poisoned"))?;
        guard.mapping.clone()
    };
    view.set_elements(mapping, application_name.as_deref().unwrap_or(""));
    let actions_val: Value = pythonize::depythonize(&actions)?;
    let result = view.route_action(py, &actions_val)?;
    pythonize::pythonize(py, &result).map_err(Into::into)
}

#[cfg(test)]
mod platform_tests {
    use super::*;
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicU64, Ordering};

    struct Fixture {
        root: PathBuf,
        view: ControllerView,
        scanner: Arc<Mutex<ScannerInner>>,
    }

    impl Fixture {
        fn new() -> Self {
            static NEXT: AtomicU64 = AtomicU64::new(0);
            let root = std::env::temp_dir().join(format!("saccade-controller-{}-{}-{}",
                std::process::id(),
                std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos(),
                NEXT.fetch_add(1, Ordering::Relaxed)));
            std::fs::create_dir(&root).unwrap();
            let mut inner = ScannerInner::new(&root.join("browser"), 0, Some(root.join("scans")), false);
            inner.set_platform_scope(crate::platform_scope::PlatformScope::from_value(&json!({
                "schema_version": 1, "platform_id": "dext", "execution_mode": "supervised",
                "browser_profile": "saccade-dext", "start_url": "https://app.dext.com/login",
                "allowed_hosts": ["app.dext.com"], "max_steps": 45, "config_revision": "a".repeat(64),
            })).unwrap());
            let scanner = Arc::new(Mutex::new(inner));
            let view = ControllerView::new(&root, None, false, scanner.clone(), None).unwrap();
            Self { root, view, scanner }
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            // Fresh synthetic roots only; no browser or user data is involved.
            let _ = std::fs::remove_dir_all(&self.root);
        }
    }

    #[test]
    fn controller_blocks_effects_before_any_browser_dispatch() {
        Python::initialize();
        Python::attach(|py| {
            for kind in ["click", "hold_click", "input", "vault", "keyboard", "scroll", "dialog",
                         "run_script", "more", "index", "navigate_tab", "close_tab", "download", "call_function", "unknown"] {
                let fixture = Fixture::new();
                let result = fixture.view.route_action(py, &json!({"type": kind, "id": 1, "value": "synthetic"})).unwrap();
                assert_eq!(result["status"], "error", "{kind}: {result}");
                assert_eq!(result["tool"], kind);
                assert_eq!(result["operator_review_required"], true);
                assert!(fixture.scanner.lock().unwrap().platform_violation().is_some());
            }
        });
    }

    #[test]
    fn denied_batch_keeps_one_result_per_call_and_never_reports_done() {
        Python::initialize();
        Python::attach(|py| {
            let fixture = Fixture::new();
            let result = fixture.view.route_action(py, &json!([
                {"type": "run_script", "value": "location='https://outside.test/'"},
                {"type": "wait", "value": "0"},
                {"type": "done", "value": "claim success"},
            ])).unwrap();
            assert_eq!(result["status"], "error");
            let results = result["results"].as_array().unwrap();
            assert_eq!(results.len(), 3);
            assert_eq!(results[0]["status"], "error");
            assert_eq!(results[1]["status"], "not_run");
            assert_eq!(results[2]["status"], "not_run");
            assert!(results.iter().all(|item| item.get("action") != Some(&json!("done"))));
        });
    }

    #[test]
    fn an_unverified_browser_cannot_complete_even_a_read_only_run() {
        Python::initialize();
        Python::attach(|py| {
            let fixture = Fixture::new();
            let result = fixture.view.route_action(py, &json!({"type": "done", "value": "unverified success"})).unwrap();
            assert_eq!(result["status"], "error");
            assert_eq!(result["operator_review_required"], true);
            assert!(result["message"].as_str().unwrap().contains("not been initialized"));
        });
    }

    #[test]
    fn generic_browser_activates_and_revokes_functions_from_native_url_observations() {
        Python::initialize();
        Python::attach(|py| {
            use pyo3::types::PyDict;
            use std::ffi::CString;
            let fixture = Fixture::new();
            let mut inner = ScannerInner::new(&fixture.root.join("generic"),0,None,false);
            inner.business_test_observations = Some(std::collections::VecDeque::new());
            inner.url = "https://example.com/".into();
            let scanner = Arc::new(Mutex::new(inner));
            let view = ControllerView::new(&fixture.root,None,false,scanner.clone(),None).unwrap();
            let locals = PyDict::new(py);
            py.import("sys").unwrap().getattr("path").unwrap().call_method1("insert",(0,
                std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").to_string_lossy().as_ref())).unwrap();
            py.run(&CString::new(r#"
from unittest.mock import patch
import AutoCua.saccade.automatic_platform as auto
created = []
class Run:
    def set_google_runtime(self, provider, model, key):
        assert provider == 'google' and model == 'gemini-3.8-flash' and key == 'synthetic-runtime-key'
    def begin_download(self, started):
        self.started = started
    def invalidate_download(self, started):
        assert started == self.started
    def note_download(self, path, started):
        from pathlib import Path
        from AutoCua.saccade.downloaded_pdf import resolve_download
        assert self.started == started and started > 0
        absolute, content = resolve_download(path, folder=Path(path).parent)
        assert Path(absolute).is_absolute() and content.startswith(b'%PDF-')
        downloads.append(absolute)
    def refresh(self):
        return {'name':'call_function','parameters':{'type':'object','properties':{}}}
    def prepare(self, action):
        raise AssertionError('A stale selection must not reach Python function authorization')
def factory(platform):
    created.append(platform)
    return Run()
replacement = patch.object(auto,'business_for_platform',factory)
replacement.start()
downloads = []
"#).unwrap(),Some(&locals),None).unwrap();
            // An authenticated synthetic extension peer exercises the actual
            // native request/reply transport. No Chrome or user profile runs.
            use tungstenite::client::IntoClientRequest;
            let source = fixture.root.join("bridge-source");
            std::fs::create_dir(&source).unwrap();
            std::fs::write(source.join("manifest.json"),r#"{"manifest_version":3,"name":"Synthetic bridge","version":"1.0","background":{"service_worker":"background.js"}}"#).unwrap();
            std::fs::write(source.join("background.js"),"// Synthetic test peer only.\n").unwrap();
            let bridge = crate::bridge::Bridge::open_test_peer(&source,&fixture.root.join("test-extension")).unwrap();
            let port = bridge.port();
            let token = bridge.token().to_owned();
            let origin = format!("chrome-extension://{}",bridge.extension_id());
            let download_path = fixture.root.join("Synthetic invoice (1).pdf");
            let peer_path = download_path.clone();
            let peer = std::thread::spawn(move || {
                let stream = std::net::TcpStream::connect(("127.0.0.1",port)).unwrap();
                stream.set_read_timeout(Some(std::time::Duration::from_secs(15))).unwrap();
                let mut handshake = format!("ws://127.0.0.1:{port}/bridge?token={token}").into_client_request().unwrap();
                handshake.headers_mut().insert("origin",origin.parse().unwrap());
                let (mut socket,_) = tungstenite::client(handshake,stream).unwrap();
                let mut received = Vec::new();
                let mut download = None;
                let mut observations = 0;
                loop {
                    let message = socket.read().unwrap();
                    let request: Value = serde_json::from_str(message.to_text().unwrap()).unwrap();
                    let kind = request["type"].as_str().unwrap();
                    let result = match kind {
                        "tabs" => json!([{"id":1,"url":"https://app.dext.com/receipts","title":"Synthetic invoice","type":"page"}]),
                        "click" => {
                            download = (request["rect"][1] == 60.0).then(||request["download_operation"].clone());
                            observations = 0;
                            json!({"download":{"state":"not_observed","operation":request["download_operation"]}})
                        },
                        "download_status" if download.as_ref() == Some(&request["download_operation"]) => {
                            observations += 1;
                            if observations < 2 {
                                json!({"download":{"state":"in_progress","operation":request["download_operation"]}})
                            } else {
                                std::fs::write(&peer_path,b"%PDF-1.4\nSynthetic invoice\n%%EOF").unwrap();
                                json!({"download":{"state":"complete","filename":"Synthetic invoice (1).pdf","absolute_path":peer_path,
                                    "operation":request["download_operation"]}})
                            }
                        },
                        "download_status" => json!({"download":{"state":"not_observed","operation":request["download_operation"]}}),
                        "scroll_probe" => json!({"probe":[0,0,0,received.len()]}),
                        "run_script" => json!({"result":{"value":"Synthetic page result"}}),
                        _ => json!({}),
                    };
                    socket.send(tungstenite::Message::Text(json!({"id":request["id"],"result":result}).to_string())).unwrap();
                    let finished = kind == "release";
                    received.push(request);
                    if finished { break }
                }
                received
            });
            {
                let mut browser = scanner.lock().unwrap();
                browser.set_bridge(Arc::new(Mutex::new(bridge)));
                browser.set_cursor_enabled(false);
            }
            assert!(super::super::service::scan_op(py,&scanner,|browser|browser.bind_tab("1")).is_ok());
            view.configure_google_runtime("google","gemini-3.8-flash",Some("synthetic-runtime-key"));
            assert!(view.refresh_business(py).unwrap().is_none());
            scanner.lock().unwrap().url = "https://app.dext.com/login".into();
            assert!(view.refresh_business(py).unwrap().is_some());
            view.set_elements(json!({
                "1":{"name":"Page","rect":[0,0,800,600]},
                "2":{"name":"Purchases","rect":[1,1,50,20],"line":"<button>Purchases</button>"},
                "3":{"name":"Search","rect":[1,30,50,20],"line":"<input>"},
                "4":{"name":"Exporter","rect":[1,60,50,20],"line":"<button>Exporter</button>"}
            }).as_object().unwrap().clone(),"");
            for action in [
                json!({"type":"click","id":2}),
                json!({"type":"click","id":2,"times":2}),
                json!({"type":"input","id":3,"value":"Synthetic query","enter":false}),
                json!({"type":"keyboard","value":"CTRL+A"}),
                json!({"type":"scroll","id":1,"direction":"down"}),
                json!({"type":"update_tab","value":"https://app.dext.com/receipts"}),
                json!({"type":"navigate_tab","value":"back"}),
                json!({"type":"navigate_tab","value":"reload"}),
                json!({"type":"click","id":4}),
            ] {
                let result = view.route_action(py,&action).unwrap();
                assert_eq!(result["status"],"success","{action}: {result}");
                assert!(result.get("operator_review_required").is_none(),"{result}");
                assert!(!result.to_string().contains("absolute_path"));
                if action["id"] == 4 {
                    assert_eq!(result["download"]["filename"],"Synthetic invoice (1).pdf");
                    assert_eq!(result["download"]["state"],"complete");
                }
            }
            let original_operation = view.download_operation.lock().unwrap().clone().unwrap();
            *view.download_operation.lock().unwrap() = Some(("2".into(),original_operation.1));
            let mut changed_tab = json!({});
            view.check_download(py,&mut changed_tab).unwrap();
            assert_eq!(changed_tab["download"]["state"],"observation_unavailable");
            assert!(!changed_tab.to_string().contains("absolute_path"));
            *view.download_operation.lock().unwrap() = Some(original_operation);
            // Existing generic geometry and destination checks still apply.
            for action in [json!({"type":"click","id":999}),
                           json!({"type":"update_tab","value":"https://chromewebstore.google.com/"})] {
                let result = view.route_action(py,&action).unwrap();
                assert_eq!(result["status"],"error");
                assert!(result.get("operator_review_required").is_none());
            }
            // The native bridge guard also permits the unchanged supported
            // script/dialog/tab command paths without imposing PR3's whitelist.
            for kind in ["run_script","dialog","activate","close_tab","new_tab"] {
                let result = super::super::service::scan_op(py,&scanner,|browser| {
                    browser.authorize_platform_action(&json!({"type":kind}))?;
                    browser.bridge_call(json!({"type":kind}))
                });
                assert!(result.is_ok(),"{kind} was blocked before native dispatch");
            }
            assert!(download_path.is_file());
            py.run(&CString::new("assert downloads and len(set(downloads)) == 1").unwrap(),Some(&locals),None).unwrap();
            scanner.lock().unwrap().url = "https://app.dext.com.evil.example/".into();
            let denied = view.call_business(py,&json!({"type":"call_function","version":1,"name":"dext.bank","arguments":{}})).unwrap();
            assert_eq!(denied["status"],"error");
            assert!(view.refresh_business(py).unwrap().is_none());
            scanner.lock().unwrap().url = "https://app.dext.com/receipts".into();
            assert!(view.refresh_business(py).unwrap().is_some());
            assert!(view.refresh_business(py).unwrap().is_some());
            py.run(&CString::new("replacement.stop()\nassert created == ['dext','dext']").unwrap(),Some(&locals),None).unwrap();
            scanner.lock().unwrap().url = "https://docs.google.com/spreadsheets/synthetic".into();
            assert!(view.refresh_business(py).unwrap().is_none());
            assert!(scanner.lock().unwrap().platform_violation().is_none());
            assert!(super::super::service::scan_op(py,&scanner,|browser|browser.bridge_request(json!({"type":"release"}))).is_ok());
            let received = py.detach(||peer.join()).unwrap();
            for kind in ["click","input","keyboard","scroll","navigate","history","reload","run_script","dialog","close_tab","new_tab"] {
                assert!(received.iter().any(|request|request["type"] == kind),"missing native dispatch: {kind}");
            }
            let clicks: Vec<_> = received.iter().filter(|request|request["type"] == "click").collect();
            assert_eq!(clicks.len(),3);
            assert!(clicks.iter().all(|request| request["download_operation"].is_string() && request.get("observe_download").is_none()));
            assert_eq!(clicks[1]["times"],2);
            assert!(clicks.windows(2).all(|pair|pair[0]["download_operation"] != pair[1]["download_operation"]));
            for request in received.iter().filter(|request|matches!(request["type"].as_str(),
                Some("click"|"input"|"keyboard"|"scroll"|"navigate"|"history"|"reload"|"run_script"|"dialog"))) {
                assert_eq!(request["tabId"],1,"{request}");
            }
        });
    }

    #[test]
    fn raw_browser_script_and_navigation_channels_cannot_bypass_scope() {
        for request in [json!({"type": "run_script", "code": "synthetic"}),
                        json!({"type": "close_tab", "tabId": 1}),
                        json!({"type": "navigate", "url": "https://app.dext.com.evil.test/"}),
                        json!({"type": "reload"})] {
            let fixture = Fixture::new();
            assert!(fixture.scanner.lock().unwrap().bridge_request(request).is_err());
            assert!(fixture.scanner.lock().unwrap().platform_violation().is_some());
        }
        let root = std::env::temp_dir();
        let mut generic = ScannerInner::new(&root, 0, None, false);
        assert!(generic.authorize_platform_action(&json!({"type": "run_script"})).is_ok());
        assert!(generic.platform_violation().is_none());
    }
}
