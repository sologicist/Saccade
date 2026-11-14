//! Per-controller Python business gate. A permit never travels through model JSON.

use pyo3::prelude::*;
use serde_json::{json, Value};

pub struct BusinessGate {
    run: Py<PyAny>,
}

pub struct BusinessPermit {
    ticket: Py<PyAny>,
    pub(crate) platform: String,
    pub(crate) context_revision: String,
    pub(crate) effect: String,
    pub(crate) name: String,
    pub(crate) action: Value,
}

impl BusinessGate {
    pub fn configure_google(&self, py: Python<'_>, provider: &str, model: &str, key: Option<&str>) -> PyResult<()> {
        self.run.bind(py).call_method1("set_google_runtime",(provider,model,key))?;
        Ok(())
    }
    pub fn automatic(run: Py<PyAny>) -> Self { Self { run } }
    #[cfg(test)]
    pub fn from_fixture(run: Py<PyAny>) -> Self { Self { run } }
    pub fn new(py: Python<'_>, context: &Bound<'_, PyAny>) -> PyResult<Self> {
        let run = py.import("AutoCua.saccade.business_run")?.getattr("BusinessRun")?.call1((context,))?;
        Ok(Self { run: run.unbind() })
    }

    pub fn refresh(&self, py: Python<'_>) -> PyResult<Value> {
        pythonize::depythonize(&self.run.bind(py).call_method0("refresh")?).map_err(Into::into)
    }

    pub fn note_download(&self, py: Python<'_>, path: &str, operation: u64) -> PyResult<()> {
        self.run.bind(py).call_method1("note_download", (path,operation))?;
        Ok(())
    }

    pub fn invalidate_download(&self, py: Python<'_>, operation: u64) -> PyResult<()> {
        self.run.bind(py).call_method1("invalidate_download", (operation,))?;
        Ok(())
    }

    pub fn begin_download(&self, py: Python<'_>, started: u64) -> PyResult<()> {
        self.run.bind(py).call_method1("begin_download", (started,))?;
        Ok(())
    }

    pub fn authorize(&self, py: Python<'_>, action: &Value) -> PyResult<BusinessPermit> {
        let ticket = self.run.bind(py).call_method1("prepare", (pythonize::pythonize(py, action)?,))?;
        let value: Value = pythonize::depythonize(&ticket)?;
        let text = |key: &str| value.get(key).and_then(Value::as_str).unwrap_or_default().to_string();
        Ok(BusinessPermit { platform: text("platform_id"), context_revision: text("context_revision"),
            effect: text("effect"), name: text("name"), action: value["action"].clone(), ticket: ticket.unbind() })
    }

    pub fn execute(&self, py: Python<'_>, permit: BusinessPermit, stop: Option<&Py<PyAny>>) -> PyResult<Value> {
        let result = self.run.bind(py).call_method1("execute", (permit.ticket.bind(py),
            stop.map(|s| s.clone_ref(py)).unwrap_or_else(|| py.None())))?;
        pythonize::depythonize(&result).map_err(Into::into)
    }
}

pub fn denied() -> Value {
    json!({"status": "error", "tool": "call_function", "code": "business_gate_denied",
           "message": "The trusted business gate refused this request. Check the observed website, installed function contract, active registered client and local PDF.",
           "operator_review_required": true})
}

pub fn denied_error(py: Python<'_>, error: &PyErr) -> Value {
    let mut result = denied();
    // Only stable enumerated codes may cross this boundary; never exception
    // strings which can contain reference text, credentials or local paths.
    if let Ok(code) = error.value(py).str().and_then(|s| s.extract::<String>()) {
        if matches!(code.as_str(), "business_revision_changed" | "unapproved_callable"
            | "schema_mismatch" | "unauthorized_client" | "operator_argument_required"
            | "verified_download_receipt_required" | "real_client_privacy_gate_closed"
            | "invalid_business_request" | "business_decision_required" | "business_client_scope_changed" | "unsafe_path"
            | "download_file_missing" | "download_incomplete" | "download_stale" | "download_outside_folder"
            | "invalid_download_path" | "invalid_download_filename" | "invalid_download_pdf"
            | "download_file_changed"
            | "chrome_confirmed_download_required" | "download_operation_changed"
            | "downloads_folder_unavailable" | "downloads_configuration_invalid" | "invalid_client_registration") {
            result["code"] = json!(code);
        }
    }
    result
}
