//! Bounded, memory-only CDP download evidence. Never a receipt or an allow rule.

use std::collections::{BTreeMap, VecDeque};
use ring::digest::{digest, SHA256};
use serde_json::Value;

const EVENT_LIMIT: usize = 256;
const DOWNLOAD_LIMIT: usize = 32;

#[derive(Clone, Debug, PartialEq)]
pub enum DownloadEvent {
    Begin { sequence: u64, guid: String, frame: String, url_digest: String },
    Progress { sequence: u64, guid: String, total: u64, received: u64, state: String },
}

struct DownloadState {
    received: u64,
    total: u64,
    terminal: bool,
}

#[derive(Default)]
pub struct DownloadEvents {
    events: VecDeque<DownloadEvent>,
    downloads: BTreeMap<String, DownloadState>,
    sequence: u64,
    failure: Option<&'static str>,
}

fn identifier(value: Option<&Value>) -> Result<String, &'static str> {
    let value = value.and_then(Value::as_str).ok_or("download_event_invalid")?;
    if value.is_empty() || value.len() > 128 || !value.bytes().all(|c| c.is_ascii_graphic()) {
        return Err("download_event_invalid");
    }
    Ok(value.to_owned())
}

fn bytes(value: Option<&Value>) -> Result<u64, &'static str> {
    let value = value.and_then(Value::as_f64).ok_or("download_event_invalid")?;
    if !value.is_finite() || !(0.0..=9_007_199_254_740_991.0).contains(&value) || value.fract() != 0.0 {
        return Err("download_event_invalid");
    }
    Ok(value as u64)
}

impl DownloadEvents {
    /// Consume only Browser events on the existing private browser-level pipe.
    /// URL bytes are hashed; suggested filenames and local file paths are never
    /// retained, logged, opened or used to authorize anything.
    pub fn observe(&mut self, value: &Value) -> bool {
        let Some(method) = value.get("method").and_then(Value::as_str) else { return false };
        if !method.starts_with("Browser.download") { return false }
        if self.failure.is_some() { return true }
        if let Err(code) = self.record(method, value.get("params").unwrap_or(&Value::Null)) {
            self.failure = Some(code);
        }
        true
    }

    fn record(&mut self, method: &str, params: &Value) -> Result<(), &'static str> {
        if self.events.len() >= EVENT_LIMIT { return Err("download_event_overflow") }
        self.sequence = self.sequence.checked_add(1).ok_or("download_event_overflow")?;
        let guid = identifier(params.get("guid"))?;
        let event = match method {
            "Browser.downloadWillBegin" => {
                if self.downloads.contains_key(&guid) { return Err("download_event_replayed") }
                if self.downloads.len() >= DOWNLOAD_LIMIT { return Err("download_event_overflow") }
                let frame = identifier(params.get("frameId"))?;
                let url = params.get("url").and_then(Value::as_str).ok_or("download_event_invalid")?;
                if url.is_empty() || url.len() > 8192 || url.chars().any(char::is_control) {
                    return Err("download_event_invalid");
                }
                let url_digest = digest(&SHA256, url.as_bytes()).as_ref().iter().map(|b| format!("{b:02x}")).collect();
                self.downloads.insert(guid.clone(), DownloadState { received: 0, total: 0, terminal: false });
                DownloadEvent::Begin { sequence: self.sequence, guid, frame, url_digest }
            },
            "Browser.downloadProgress" => {
                let total = bytes(params.get("totalBytes"))?;
                let received = bytes(params.get("receivedBytes"))?;
                let state = params.get("state").and_then(Value::as_str).ok_or("download_event_invalid")?;
                if !matches!(state, "inProgress" | "completed" | "canceled") { return Err("download_event_invalid") }
                let previous = self.downloads.get_mut(&guid).ok_or("download_progress_without_begin")?;
                if previous.terminal { return Err("download_event_replayed") }
                if received < previous.received || (previous.total != 0 && total != previous.total)
                    || (total != 0 && received > total) {
                    return Err("download_progress_inconsistent");
                }
                if state == "completed" && (total == 0 || received != total) {
                    return Err("download_completion_unverified");
                }
                previous.received = received;
                previous.total = total;
                previous.terminal = state != "inProgress";
                DownloadEvent::Progress { sequence: self.sequence, guid, total, received, state: state.to_owned() }
            },
            _ => return Err("download_event_unsupported"),
        };
        self.events.push_back(event);
        Ok(())
    }

    /// Default-DENY scoped runs reject even canceled attempts. A CDP completed
    /// event cannot establish a file, Dext record identity or receipt authority.
    pub fn require_no_activity(&self) -> Result<(), &'static str> {
        if let Some(code) = self.failure { return Err(code) }
        if !self.events.is_empty() { return Err("scoped_download_attempt_observed") }
        Ok(())
    }

    pub fn events(&self) -> &VecDeque<DownloadEvent> { &self.events }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn begin(guid: &str, frame: &str) -> Value {
        json!({"method":"Browser.downloadWillBegin", "params":{"guid":guid,"frameId":frame,
            "url":"https://app.dext.com/synthetic-document?private-token=never-retain",
            "suggestedFilename":"never-retain-private-name.pdf"}})
    }
    fn progress(guid: &str, total: f64, received: f64, state: &str) -> Value {
        json!({"method":"Browser.downloadProgress", "params":{"guid":guid,"totalBytes":total,
            "receivedBytes":received,"state":state,"filePath":"never-retain-private-path"}})
    }

    #[test]
    fn ordered_lifecycle_preserves_frame_and_guid_but_never_authorizes_downloads() {
        let mut events = DownloadEvents::default();
        assert!(events.observe(&begin("synthetic-a", "frame-a")));
        events.observe(&progress("synthetic-a", 100.0, 50.0, "inProgress"));
        events.observe(&progress("synthetic-a", 100.0, 100.0, "completed"));
        assert_eq!(events.events.len(), 3);
        assert!(matches!(&events.events[0], DownloadEvent::Begin { frame, guid, .. } if frame == "frame-a" && guid == "synthetic-a"));
        assert_eq!(events.require_no_activity(), Err("scoped_download_attempt_observed"));
        assert!(!format!("{:?}", events.events).contains("never-retain"));
    }

    #[test]
    fn foreign_guid_duplicates_and_invalid_progress_are_sticky_failures() {
        for event in [begin("synthetic-a", "other-frame"), progress("other-guid", 1.0, 1.0, "completed"),
            progress("synthetic-a", 2.0, 3.0, "completed"), progress("synthetic-a", 2.0, 1.5, "inProgress"),
            progress("synthetic-a", 0.0, 0.0, "completed"), progress("synthetic-a", 2.0, 1.0, "unknown")] {
            let mut events = DownloadEvents::default();
            events.observe(&begin("synthetic-a", "frame-a"));
            events.observe(&event);
            assert!(events.failure.is_some());
            events.observe(&progress("synthetic-a", 2.0, 2.0, "completed"));
            assert!(events.require_no_activity().is_err());
        }
    }

    #[test]
    fn cancelled_interrupted_and_replayed_downloads_cannot_be_success() {
        let mut events = DownloadEvents::default();
        events.observe(&begin("synthetic-a", "frame-a"));
        assert!(events.require_no_activity().is_err());
        events.observe(&progress("synthetic-a", 0.0, 0.0, "canceled"));
        assert!(events.failure.is_none());
        assert!(events.require_no_activity().is_err());
        events.observe(&progress("synthetic-a", 100.0, 100.0, "completed"));
        assert_eq!(events.failure, Some("download_event_replayed"));
    }

    #[test]
    fn queue_overflow_is_bounded_and_cannot_be_cleared_by_a_later_good_event() {
        let mut events = DownloadEvents::default();
        events.observe(&begin("synthetic-a", "frame-a"));
        for _ in 0..EVENT_LIMIT { events.observe(&progress("synthetic-a", 0.0, 0.0, "inProgress")); }
        assert_eq!(events.events.len(), EVENT_LIMIT);
        assert_eq!(events.failure, Some("download_event_overflow"));
    }
}
