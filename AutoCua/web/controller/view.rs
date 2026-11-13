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
    dext_control: Mutex<Option<Py<PyAny>>>,
    learning_control: Mutex<Option<Py<PyAny>>>,
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
            dext_control: Mutex::new(None),
            learning_control: Mutex::new(None),
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
        let gate = match context {
            Some(context) => {
                if py.import("AutoCua.saccade.business_run")?.call_method1("supports_legacy", (context,))?.extract::<bool>()? {
                    Some(crate::tool_registry::business::BusinessGate::new(py, context)?)
                } else { None }
            }
            None => None,
        };
        *self.business.lock().unwrap() = gate;
        Ok(())
    }

    pub fn refresh_business(&self, py: Python<'_>) -> PyResult<Option<Value>> {
        let mut definition = self.business.lock().unwrap().as_ref().map(|gate| gate.refresh(py)).transpose()?;
        let learning = self.learning_control.lock().unwrap().as_ref().map(|c| c.clone_ref(py));
        let supervised = learning.as_ref().map(|c| c.bind(py).getattr("context")?.get_item("execution_mode")?.extract::<String>()).transpose()?.is_some_and(|mode|mode == "supervised");
        if let Some(learning) = learning {
            let generic = learning.bind(py).call_method0("execution_tools")?;
            if !generic.is_none() {
                let merged = py.import("AutoCua.saccade.capabilities")?.getattr("merge_tools")?
                    .call1((pythonize::pythonize(py, &definition)?, generic))?;
                definition = Some(pythonize::depythonize(&merged)?);
            }
        }
        let control = self.dext_control.lock().unwrap().as_ref().map(|c| c.clone_ref(py));
        if let Some(control) = control { control.bind(py).call_method0("freeze_decision")?; }
        let mut definitions: Vec<Value> = definition.into_iter().collect();
        if supervised { definitions.push(crate::tool_registry::service::download_tool()); }
        if self.dext_control.lock().unwrap().is_some() {
            let tool: Value = pythonize::depythonize(&py.import("AutoCua.saccade.dext_control")?.getattr("NAVIGATION_TOOL")?)?;
            definitions.push(tool);
        }
        Ok(if definitions.is_empty() { None } else { Some(json!(definitions)) })
    }

    pub fn configure_dext_control(&self, py: Python<'_>, control: Option<&Bound<'_, PyAny>>, context: Option<&Bound<'_, PyAny>>) -> PyResult<()> {
        let checked = match control {
            Some(control) if !control.is_none() => {
                let context = context.ok_or_else(|| pyo3::exceptions::PyValueError::new_err("operator_channel_required"))?;
                Some(py.import("AutoCua.saccade.dext_control")?.getattr("validate_control")?
                    .call1((control, context))?.unbind())
            },
            _ => None,
        };
        self.configure_learning_control(py, control, context)?;
        *self.dext_control.lock().unwrap() = checked;
        Ok(())
    }

    pub fn configure_learning_control(&self, py: Python<'_>, control: Option<&Bound<'_, PyAny>>, context: Option<&Bound<'_, PyAny>>) -> PyResult<()> {
        let checked = match control {
            Some(control) if !control.is_none() => {
                let context = context.ok_or_else(|| pyo3::exceptions::PyValueError::new_err("operator_channel_required"))?;
                Some(py.import("AutoCua.saccade.platform_learning")?.getattr("validate_learning_control")?
                    .call1((control, context))?.unbind())
            },
            _ => None,
        };
        *self.learning_control.lock().unwrap() = checked;
        Ok(())
    }

    pub fn procedure_overlay(&self, py: Python<'_>) -> PyResult<String> {
        let control = self.learning_control.lock().unwrap().as_ref().map(|c| c.clone_ref(py));
        match control { Some(control) => control.bind(py).call_method0("overlay")?.extract(), None => Ok(String::new()) }
    }

    pub fn procedure_overlay_for(&self, py: Python<'_>, selected: &str) -> PyResult<String> {
        let control = self.learning_control.lock().unwrap().as_ref().map(|c| c.clone_ref(py));
        if let Some(control) = control {
            let platform: String = control.bind(py).getattr("context")?.get_item("platform_id")?.extract()?;
            if selected != format!("{platform}.md") {
                return Err(pyo3::exceptions::PyValueError::new_err("learning_platform_mismatch"));
            }
        }
        self.procedure_overlay(py)
    }

    pub fn conversational_intervention(&self, py: Python<'_>) -> PyResult<Option<Value>> {
        let control = self.learning_control.lock().unwrap().as_ref().map(|c| c.clone_ref(py));
        let Some(control) = control else { return Ok(None) };
        let control = control.bind(py);
        if !control.getattr("conversational")?.extract::<bool>()? { return Ok(None) }
        control.call_method0("freeze_decision")?;
        let (elements, stamp) = super::service::scan_op(py, &self.scanner, |scanner| {
            Ok((scanner.mapping.clone(), scanner.platform_learning_stamp()?))
        }).map_err(|error| match error {
            ActErr::Py(error) => error,
            ActErr::Msg(message) => pyo3::exceptions::PyValueError::new_err(message),
        })?;
        control.call_method1("observe_native", (pythonize::pythonize(py, &elements)?, pythonize::pythonize(py, &stamp)?))?;
        let teaching = control.getattr("teaching")?;
        if !teaching.is_none() && !teaching.getattr("source")?.is_none() {
            // The corrected public control is visible. Let the SAME model and
            // controller execute it (with targeted approval when necessary).
            return Ok(None);
        }
        let request = control.call_method0("learning_intervention")?;
        if request.is_none() { Ok(None) } else { pythonize::depythonize(&request).map(Some).map_err(Into::into) }
    }

    fn request_dext_navigation(&self, py: Python<'_>, action: &Value) -> PyResult<Value> {
        let control = self.dext_control.lock().unwrap().as_ref().map(|c| c.clone_ref(py));
        let Some(control) = control else {
            return Ok(json!({"status":"error", "tool":"dext_navigation", "code":"operator_channel_required", "operator_review_required":true}));
        };
        // This path never dispatches input. Native observation proves scope and
        // download DENY, not unimplemented Dext target/frame/record semantics.
        let stamp = match super::service::scan_op(py, &self.scanner, |s| s.dext_navigation_stamp()) {
            Ok(stamp) => stamp,
            Err(ActErr::Py(error)) => return Err(error),
            Err(ActErr::Msg(_)) => return Ok(json!({"status":"error", "tool":"dext_navigation", "code":"unverified_navigation_observation", "operator_review_required":true})),
        };
        let elements = self.state.lock().unwrap().elements.clone();
        let result = control.bind(py).call_method1("observe_native", (pythonize::pythonize(py, &elements)?, pythonize::pythonize(py, &stamp)?))
            .and_then(|_| control.bind(py).call_method1("propose_navigation", (pythonize::pythonize(py, action)?,)))
            .and_then(|_| control.bind(py).call_method0("wait_navigation_review"));
        match result {
            Ok(value) => pythonize::depythonize(&value).map_err(Into::into),
            Err(_) => Ok(json!({"status":"error", "tool":"dext_navigation", "code":"navigation_preview_unavailable", "operator_review_required":true})),
        }
    }

    #[cfg(test)]
    pub fn business_fixture(&self, run: Py<PyAny>) {
        *self.business.lock().unwrap() = Some(crate::tool_registry::business::BusinessGate::from_fixture(run));
    }

    fn call_business(&self, py: Python<'_>, action: &Value) -> PyResult<Value> {
        let business = self.business.lock().unwrap();
        let Some(gate) = business.as_ref() else { return Ok(crate::tool_registry::business::denied()) };
        let permit = match gate.authorize(py, action) {
            Ok(permit) => permit,
            Err(error) => return Ok(crate::tool_registry::business::denied_error(py, &error)),
        };
        if let Err(error) = super::service::scan_op(py, &self.scanner, |scanner| scanner.authorize_business_action(action, &permit)) {
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

    fn operator_execution(&self, py: Python<'_>, action: &Value) -> PyResult<Option<Value>> {
        let kind = action["type"].as_str().unwrap_or_default();
        if !matches!(kind, "click" | "hold_click" | "input" | "keyboard" | "dialog" | "call_function" | "download") { return Ok(None) }
        let control = self.learning_control.lock().unwrap().as_ref().map(|c| c.clone_ref(py));
        let Some(control) = control else { return Ok(None) };
        let observed = self.state.lock().unwrap().elements.clone();
        let refresh = matches!(kind, "click" | "hold_click" | "input" | "keyboard" | "dialog" | "download");
        let (elements, stamp) = super::service::scan_op(py, &self.scanner, |scanner| {
            if refresh { scanner.scan_core()?; }
            let mut stamp = scanner.platform_learning_stamp()?;
            if kind == "keyboard" { stamp["focus"] = scanner.bridge_call(json!({"type":"execution_focus"}))?; }
            if kind == "dialog" { stamp["dialog"] = scanner.open_dialog().unwrap_or(Value::Null); }

            let page = ring::digest::digest(&ring::digest::SHA256, scanner.url.as_bytes());
            stamp["page"] = json!(page.as_ref().iter().map(|b| format!("{b:02x}")).collect::<String>());
            Ok((scanner.mapping.clone(), stamp))
        })
            .map_err(|e| match e { ActErr::Py(e) => e, ActErr::Msg(s) => pyo3::exceptions::PyValueError::new_err(s) })?;
        if refresh && observed != elements {
            return Ok(Some(json!({"status":"waiting_operator","tool":kind,"executed":false,
                "intervention":{"category":"confirmation","reason":"condition_confirmation",
                "request":"The page changed before the action could run. May I reobserve it and select the correct target again? No action was executed."}})));
        }
        let decision = control.bind(py).call_method1("authorize_execution", (pythonize::pythonize(py, action)?,
            pythonize::pythonize(py, &stamp)?, pythonize::pythonize(py, &elements)?))?;
        let decision: Value = pythonize::depythonize(&decision)?;
        if decision["unavailable"] == true {
            if kind == "call_function" && self.business.lock().unwrap().is_none() {
                return Ok(Some(json!({"status":"error","tool":kind,"code":"unregistered_capability","executed":false,
                    "message":"No such capability is installed for this platform. Use only the installed registry, not browser searches."})));
            }
            return Ok(None)
        }
        if decision["allowed"] != true {
            return Ok(Some(json!({"status":"waiting_operator","tool":kind,"executed":false,
                "intervention":{"category":"confirmation","reason":"condition_confirmation",
                "request":"Please review the exact proposed operation below. May I execute this action once? This is separate from saving a procedure."}})));
        }
        if kind == "call_function" {
            let result = control.bind(py).call_method1("execute_capability", (pythonize::pythonize(py, action)?,))?;
            return Ok(Some(pythonize::depythonize(&result)?));
        }
        if kind == "download" {
            let result = super::service::scan_op(py, &self.scanner, |scanner| scanner.download_observed(action))
                .map_err(|e| match e { ActErr::Py(e) => e, ActErr::Msg(s) => pyo3::exceptions::PyValueError::new_err(s) })?;
            let receipt = control.bind(py).call_method1("save_download", (pythonize::pythonize(py, &result)?,))?;
            return Ok(Some(pythonize::depythonize(&receipt)?));
        }
        Ok(Some(json!({"operator_authorized":true})))
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
            Err(ActErr::Msg(message)) => {
                let undispatched = message == crate::platform_scope::APPROVAL_UNAVAILABLE;
                Ok(Some(json!({"status":"error", "tool":tool, "message":message,
                    "code": if undispatched { "unsupported_navigation" } else { "platform_scope_mismatch" },
                    "executed": if undispatched { Some(false) } else { None }, "operator_review_required":true})))
            },
            Err(ActErr::Py(error)) => Err(error),
        }
    }

    fn check_after_settle(&self, py: Python<'_>, result: &mut Value) -> PyResult<()> {
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

        if actions.len() > 1 && actions.iter().any(|a| a["type"] == "call_function" || a["type"] == "dext_navigation") && actions.iter().any(|a| a["type"] == "done") {
            return Ok(json!({"status":"error", "action":"multiple", "results": actions.iter().map(|a|
                json!({"status":"not_run", "tool":a["type"], "code":"done_must_be_alone"})).collect::<Vec<_>>()}));
        }
        if let Some(ask) = actions.iter().find(|a| a["type"] == "ask_operator") {
            let mut request = ask.clone(); request.as_object_mut().unwrap().remove("type");
            let checked = py.import("AutoCua.saccade.operator_requests")?.getattr("validate_request")?
                .call1((pythonize::pythonize(py, &request)?,));
            let result = match checked {
                Ok(value) => json!({"status":"waiting_operator","tool":"ask_operator","intervention":pythonize::depythonize::<Value>(&value)?}),
                Err(_) => json!({"status":"waiting_operator","tool":"ask_operator","intervention":{"category":"blocked","reason":"unsafe_or_blocked","request":"The intervention request could not be safely displayed. Review the task privately."}}),
            };
            if actions.len() == 1 { return Ok(result); }
            return Ok(json!({"status":"waiting_operator","action":"multiple","results":actions.iter().map(|a|
                if a["type"] == "ask_operator" { result.clone() } else { json!({"status":"not_run","tool":a["type"],"code":"operator_suspension_preempts_batch"}) }).collect::<Vec<_>>()}));
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
        if self.stopped(py)? {
            return Ok((json!({"status":"stopped", "tool":action["type"]}), false));
        }
        if action.get("type").and_then(Value::as_str) == Some("dext_navigation") {
            if self.stopped(py)? { return Ok((json!({"status":"stopped", "tool":"dext_navigation"}), false)); }
            return Ok((self.request_dext_navigation(py, action)?, false));
        }
        let execution = match self.operator_execution(py, action) {
            Ok(result) => result,
            Err(error) if error.is_instance_of::<pyo3::exceptions::PyKeyboardInterrupt>(py) => return Err(error),
            Err(_) => {
                // Preserve the owned browser for a supported alternative. A
                // lost security boundary still takes the existing hard-failure
                // path; an unsupported download must never become success.
                if let Some(failure) = self.platform_check(py, None)? { return Ok((failure, false)); }
                if let Some(control) = self.learning_control.lock().unwrap().as_ref() {
                    control.bind(py).call_method0("fail_execution")?;
                }
                return Ok((json!({"status":"waiting_operator", "tool":action["type"], "code":"execution_not_verified",
                    "intervention":{"category":"blocked", "reason":"unsafe_or_blocked",
                    "request":"I could not verify this operation under the current authorization and document rules. No successful effect is claimed. Please choose a supported alternative or cancel; an uncertain effect must not be replayed."}}), false));
            }
        };
        let operator_authorized = execution.as_ref().is_some_and(|v| v["operator_authorized"] == true);
        if let Some(result) = execution.as_ref().filter(|v| v["operator_authorized"] != true) { return Ok((result.clone(), false)); }
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
        if let Some(failure) = self.platform_check(py, if operator_authorized { None } else { Some(action) })? {
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
        let mut result = self.one_inner(py, action)?;
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

    fn one_inner(&self, py: Python<'_>, action: &Value) -> PyResult<Value> {
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
            "click" => click::service::click(py, sc, &get("id"), &get("times"), &elements),
            "hold_click" => {
                click::service::hold_click(py, sc, &get("id"), &get("time"), &elements)
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
            for kind in ["click", "hold_click", "input", "vault", "keyboard", "dialog",
                         "run_script", "more", "index", "navigate_tab", "close_tab", "download", "call_function", "unknown"] {
                let fixture = Fixture::new();
                fixture.scanner.lock().unwrap().business_test_observations = Some(std::collections::VecDeque::from(vec![json!({
                    "schema_version":1, "observer_id":"synthetic-observer", "failure":"", "overflow":false,
                    "downloads_denied":true, "tabs":[{"id":"1", "url":"https://app.dext.com/login"}], "events":[]
                }); 8]));
                let result = fixture.view.route_action(py, &json!({"type": kind, "id": 1, "value": "synthetic"})).unwrap();
                assert_eq!(result["status"], "error", "{kind}: {result}");
                assert_eq!(result["tool"], kind);
                assert_eq!(result["operator_review_required"], true);
                assert!(fixture.scanner.lock().unwrap().platform_violation().is_none());
                if result["code"] == "unsupported_navigation" { assert_eq!(result["executed"], false); }
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
