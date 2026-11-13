//! Immutable platform run metadata and fail-closed browser scope policy.
//!
//! This policy does not grant accounting approval or business-tool rights.
//! The existing scanner supplies live tab and navigation observations; the
//! existing controller checks actions before reaching its normal tool handlers.

use std::collections::{BTreeMap, BTreeSet};

use serde_json::Value;
use url::Url;

pub const APPROVAL_UNAVAILABLE: &str =
    "approval_required: This platform action requires operator approval. Approval handling is not available in this phase; complete it manually in visible Chrome.";

#[derive(Clone, Debug)]
pub struct PlatformScope {
    pub platform_id: String,
    pub execution_mode: String,
    pub browser_profile: String,
    pub start_url: String,
    pub allowed_hosts: Vec<String>,
    pub max_steps: i64,
    pub config_revision: String,
    initial_blanks: BTreeMap<String, String>,
    observed: bool,
    violation: Option<String>,
}

fn valid_id(id: &str) -> bool {
    let bytes = id.as_bytes();
    !bytes.is_empty()
        && bytes.len() <= 64
        && bytes[0].is_ascii_lowercase()
        && bytes.iter().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == b'_' || *c == b'-')
}

fn valid_host(host: &str) -> bool {
    !host.is_empty()
        && host.len() <= 253
        && host.split('.').all(|label| {
            !label.is_empty()
                && label.len() <= 63
                && !label.starts_with('-')
                && !label.ends_with('-')
                && label.bytes().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-')
        })
}

fn identifier(value: Option<&Value>) -> Option<String> {
    match value? {
        Value::String(id) if !id.is_empty() => Some(id.clone()),
        Value::Number(id) => id.as_u64().map(|n| n.to_string()),
        _ => None,
    }
}

fn scope_error(reason: &str) -> String {
    format!("scope_violation: {reason} Stop and request operator review before starting another run.")
}

impl PlatformScope {
    /// Decode the versioned, backend-validated run context again at the native
    /// execution boundary. Calling code must first compare trusted Python
    /// platform metadata rather than accepting an arbitrary allowlist.
    pub fn from_value(value: &Value) -> Result<Self, String> {
        let data = value.as_object().ok_or("Platform context must be an object.")?;
        let expected: BTreeSet<&str> = [
            "schema_version", "platform_id", "execution_mode", "browser_profile",
            "start_url", "allowed_hosts", "max_steps", "config_revision",
        ].into_iter().collect();
        if data.keys().map(String::as_str).collect::<BTreeSet<_>>() != expected {
            return Err("Platform context has missing or unknown fields.".into());
        }
        if data["schema_version"].as_u64() != Some(1) {
            return Err("Unsupported platform context schema version.".into());
        }
        let text = |key: &str| -> Result<String, String> {
            data[key].as_str().map(str::to_string)
                .ok_or_else(|| format!("Platform context {key} must be a string."))
        };
        let platform_id = text("platform_id")?;
        if !valid_id(&platform_id) {
            return Err("Invalid platform identifier in native context.".into());
        }
        let execution_mode = text("execution_mode")?;
        if !matches!(execution_mode.as_str(), "supervised" | "auto") {
            return Err("Platform execution mode must be supervised or auto.".into());
        }
        let browser_profile = text("browser_profile")?;
        if browser_profile != format!("saccade-{platform_id}") {
            return Err("Platform runs require their dedicated Chrome profile.".into());
        }
        let max_steps = data["max_steps"].as_i64().filter(|n| (1..=1000).contains(n))
            .ok_or("Platform max_steps must be an integer between 1 and 1000.")?;
        let config_revision = text("config_revision")?;
        if config_revision.len() != 64
            || !config_revision.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        {
            return Err("Platform configuration revision must be a SHA-256 digest.".into());
        }
        let hosts = data["allowed_hosts"].as_array().filter(|hosts| !hosts.is_empty())
            .ok_or("Platform allowed_hosts must be a nonempty array.")?;
        let mut allowed_hosts = Vec::new();
        for host in hosts {
            let host = host.as_str().filter(|host| valid_host(host))
                .ok_or("Platform allowed_hosts must contain canonical exact hostnames.")?;
            if allowed_hosts.iter().any(|other| other == host) {
                return Err("Duplicate platform allowed_hosts are not permitted.".into());
            }
            allowed_hosts.push(host.to_string());
        }
        let scope = Self {
            platform_id,
            execution_mode,
            browser_profile,
            start_url: text("start_url")?,
            allowed_hosts,
            max_steps,
            config_revision,
            initial_blanks: BTreeMap::new(),
            observed: false,
            violation: None,
        };
        scope.validate_url(&scope.start_url)?;
        Ok(scope)
    }

    pub fn violation(&self) -> Option<&str> {
        self.violation.as_deref()
    }

    /// Once an execution observation is uncertain or outside scope, no model
    /// action, site content, or later allowed URL can authorize continuation.
    pub fn fail(&mut self, message: impl Into<String>) -> String {
        self.violation.get_or_insert_with(|| message.into()).clone()
    }

    /// The only authorized remote scheme is HTTPS, on an explicitly named
    /// hostname and its default port. Browser normalization cannot expand it.
    pub fn validate_url(&self, raw: &str) -> Result<(), String> {
        if let Some(message) = self.violation() {
            return Err(message.to_string());
        }
        if raw.chars().any(|c| c.is_whitespace() || c.is_control() || c == '\\') {
            return Err(scope_error("The browser URL contains unsafe syntax."));
        }
        let parsed = Url::parse(raw).map_err(|_| scope_error("The browser URL cannot be parsed."))?;
        if parsed.scheme() != "https"
            || !parsed.username().is_empty()
            || parsed.password().is_some()
            || parsed.port().is_some()
        {
            return Err(scope_error("Only HTTPS URLs without credentials or nondefault ports are authorized."));
        }
        let host = parsed.host_str().ok_or_else(|| scope_error("The browser URL has no hostname."))?;
        if !valid_host(host) || !self.allowed_hosts.iter().any(|allowed| allowed == host) {
            return Err(scope_error("The browser hostname is outside the selected platform."));
        }
        let (scheme, rest) = raw.split_once("://")
            .ok_or_else(|| scope_error("The browser URL must include an explicit HTTPS origin."))?;
        let authority = rest.split(['/', '?', '#']).next().unwrap_or_default();
        if !scheme.eq_ignore_ascii_case("https")
            || !(authority.eq_ignore_ascii_case(host)
                || authority.eq_ignore_ascii_case(&format!("{host}:443")))
        {
            return Err(scope_error("The browser URL authority is not canonical."));
        }
        Ok(())
    }

    /// Scope validation is separate from approval: selecting Auto never grants
    /// mutation, credential, script, download, or unclassified capabilities.
    pub fn validate_action(&self, action: &Value) -> Result<(), String> {
        if let Some(message) = self.violation() {
            return Err(message.to_string());
        }
        let kind = action.get("type").and_then(Value::as_str).unwrap_or_default();
        match kind {
            "done" | "wait" | "todo_list" | "update_todo" | "scratchpad" | "skills" => Ok(()),
            "new_tab" | "update_tab" => {
                // An exact hostname does not classify a GET/navigation as safe.
                // Dext bootstrap uses its fixed installed start URL directly;
                // An explicit return of the existing tab to that exact installed
                // bootstrap is the same trusted navigation contract, not a
                // grant for arbitrary same-host URLs or new tabs.
                if self.platform_id == "dext" {
                    if kind == "update_tab" && action.get("value").and_then(Value::as_str) == Some(self.start_url.as_str()) {
                        return self.validate_url(&self.start_url);
                    }
                    return Err(APPROVAL_UNAVAILABLE.to_string());
                }
                let url = action.get("value").and_then(Value::as_str)
                    .ok_or_else(|| scope_error("Platform navigation requires an explicit HTTPS URL."))?;
                self.validate_url(url)
            }
            // The controller must resolve this index from its existing stable
            // listing, then validate the target's live committed and pending URL.
            "switch_tab" => Ok(()),
            _ => Err(APPROVAL_UNAVAILABLE.to_string()),
        }
    }

    /// Separate native authorization; JSON flags can never manufacture a permit.
    pub fn validate_business_action(&self, action: &Value, permit: &crate::tool_registry::business::BusinessPermit) -> Result<(), String> {
        if self.violation().is_some() || self.platform_id != "dext" || self.execution_mode != "supervised"
            || permit.platform != self.platform_id || permit.context_revision != self.config_revision
            || !matches!(permit.effect.as_str(), "read" | "compute")
            || !matches!(permit.name.as_str(), "dext.bank" | "dext.scribe")
            || permit.action != *action || action.get("type").and_then(Value::as_str) != Some("call_function") {
            return Err(APPROVAL_UNAVAILABLE.to_string());
        }
        Ok(())
    }

    /// Untouched startup blank tabs may remain in Chrome, but are never valid
    /// action targets. New blank tabs, changed tabs, and browser-internal pages
    /// do not gain an exemption from this bootstrap-only registration.
    pub fn allow_initial_blank(&mut self, id: &str, url: &str) -> Result<(), String> {
        if self.observed || id.is_empty()
            || !matches!(url, "about:blank" | "chrome://newtab/" | "chrome://new-tab-page/")
        {
            return Err("Only known initial blank Chrome tabs can be exempted before observation.".into());
        }
        self.initial_blanks.insert(id.to_string(), url.to_string());
        Ok(())
    }

    /// The existing bridge can briefly leave its own wake tab open after its
    /// authenticated connection arrives. Only that exact extension resource,
    /// identified from the native bridge, can remain as an undriven startup tab.
    pub fn allow_initial_bridge_wake(&mut self, id: &str, extension_id: &str) -> Result<(), String> {
        if self.observed || id.is_empty() || extension_id.len() != 32
            || !extension_id.bytes().all(|c| (b'a'..=b'p').contains(&c)) {
            return Err("Invalid initial bridge wake tab identity.".into());
        }
        self.initial_blanks.insert(id.to_string(), format!("chrome-extension://{extension_id}/wake.html"));
        Ok(())
    }

    /// Called only for an about:blank target the native scanner just created
    /// after validating an explicit destination. This is not a tab-list based
    /// exemption: unexpected page-created blank tabs still stop the run.
    pub fn allow_created_blank(&mut self, id: &str) -> Result<(), String> {
        if let Some(message) = self.violation() {
            return Err(message.to_string());
        }
        if id.is_empty() {
            return Err("The created browser tab has no identity.".into());
        }
        self.initial_blanks.insert(id.to_string(), "about:blank".to_string());
        Ok(())
    }

    fn observe_url(&mut self, id: &str, url: &str, current: Option<&str>) -> Result<(), String> {
        if self.initial_blanks.get(id).is_some_and(|blank| blank == url) && current != Some(id) {
            return Ok(());
        }
        self.initial_blanks.remove(id);
        self.validate_url(url)
    }

    /// Consume real browser observations. Event history catches a disallowed
    /// redirect even if the tab returns to an allowed host before the next scan.
    /// Missing observations, queue overflow and malformed targets fail closed.
    pub fn observe_tabs(
        &mut self,
        tabs: &[Value],
        current: Option<&str>,
        navigation_events: &[Value],
        overflow: bool,
    ) -> Result<(), String> {
        if let Some(message) = self.violation() {
            return Err(message.to_string());
        }
        self.observed = true;
        let observed = (|| {
            if overflow {
                return Err(scope_error("Browser navigation observations overflowed; scope cannot be established."));
            }
            let current = current.filter(|id| !id.is_empty())
                .ok_or_else(|| scope_error("The controlled browser tab cannot be identified."))?;
            for event in navigation_events {
                let id = identifier(event.get("tabId").or_else(|| event.get("id")))
                    .ok_or_else(|| scope_error("A navigation observation has no tab identity."))?;
                let url = event.get("url").and_then(Value::as_str)
                    .ok_or_else(|| scope_error("A navigation observation has no URL."))?;
                // A browser-created bootstrap document can be reported as an
                // event before the trusted navigation. Its active snapshot is
                // checked separately below and must already be authorized.
                self.observe_url(&id, url, None)?;
            }
            let mut seen = BTreeSet::new();
            for tab in tabs {
                let id = identifier(tab.get("id").or_else(|| tab.get("targetId")))
                    .ok_or_else(|| scope_error("A browser tab observation has no identity."))?;
                if !seen.insert(id.clone()) {
                    return Err(scope_error("Browser tab identities are ambiguous."));
                }
                let url = tab.get("url").and_then(Value::as_str)
                    .ok_or_else(|| scope_error("A browser tab URL is unavailable."))?;
                self.observe_url(&id, url, Some(current))?;
                if let Some(pending) = tab.get("pendingUrl") {
                    let pending = pending.as_str()
                        .ok_or_else(|| scope_error("A browser pending URL is malformed."))?;
                    if !pending.is_empty() {
                        self.observe_url(&id, pending, Some(current))?;
                    }
                }
            }
            if !seen.contains(current) {
                return Err(scope_error("The controlled browser tab is missing from live observations."));
            }
            Ok(())
        })();
        observed.map_err(|message| self.fail(message))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn context() -> Value {
        json!({
            "schema_version": 1,
            "platform_id": "dext",
            "execution_mode": "supervised",
            "browser_profile": "saccade-dext",
            "start_url": "https://app.dext.com/login",
            "allowed_hosts": ["app.dext.com"],
            "max_steps": 45,
            "config_revision": "a".repeat(64),
        })
    }

    fn scope() -> PlatformScope {
        PlatformScope::from_value(&context()).unwrap()
    }

    fn tabs(url: &str) -> Vec<Value> {
        vec![json!({"id": "1", "url": url})]
    }

    #[test]
    fn context_schema_and_dedicated_profile_are_validated() {
        let accepted = scope();
        assert_eq!(accepted.platform_id, "dext");
        assert_eq!(accepted.max_steps, 45);
        for (key, invalid) in [
            ("schema_version", json!(true)),
            ("schema_version", json!(1.0)),
            ("schema_version", json!(2)),
            ("platform_id", json!("../dext")),
            ("platform_id", json!("Dext")),
            ("browser_profile", json!("default")),
            ("browser_profile", json!("saccade-other")),
            ("execution_mode", json!("AUTO")),
            ("max_steps", json!(0)),
            ("max_steps", json!(1001)),
            ("max_steps", json!(45.0)),
            ("max_steps", json!(true)),
            ("config_revision", json!("unverified")),
            ("config_revision", json!("A".repeat(64))),
            ("allowed_hosts", json!([])),
            ("allowed_hosts", json!(["app.dext.com", "app.dext.com"])),
            ("allowed_hosts", json!(["*.dext.com"])),
            ("allowed_hosts", json!(["APP.DEXT.COM"])),
            ("allowed_hosts", json!(["app.dext.com."])),
            ("allowed_hosts", json!(["app.dext.com:443"])),
            ("start_url", json!("https://unapproved.test/login")),
        ] {
            let mut data = context();
            data[key] = invalid;
            assert!(PlatformScope::from_value(&data).is_err(), "{key}: {data}");
        }
        let mut missing = context();
        missing.as_object_mut().unwrap().remove("config_revision");
        assert!(PlatformScope::from_value(&missing).is_err());
        let mut extra = context();
        extra["allow_all"] = json!(true);
        assert!(PlatformScope::from_value(&extra).is_err());
        assert!(PlatformScope::from_value(&Value::Null).is_err());
    }

    #[test]
    fn only_exact_authorized_https_origins_are_accepted() {
        let scope = scope();
        for url in [
            "https://app.dext.com/login",
            "https://APP.DEXT.COM:443/records/encoded%2Fid?filter=all#row",
            "https://app.dext.com",
        ] {
            assert!(scope.validate_url(url).is_ok(), "{url}");
        }
        for url in [
            "https://app.dext.com.evil.test/login", "https://evilapp.dext.com/",
            "https://child.app.dext.com/", "https://app.dext.com./",
            "https://app.dext.com:8443/", "https://app.dext.com:0443/",
            "https://user:secret@app.dext.com/", "https://@app.dext.com/",
            "https://app.dext.com@evil.test/", "https://%61pp.dext.com/",
            "https:///app.dext.com/", " https://app.dext.com/",
            "https://app.dext.com/white space", "https://app.dext.com/\n",
            "https://app.dext.com\\@evil.test/", "app.dext.com/login",
            "http://app.dext.com/", "blob:https://app.dext.com/identifier",
            "data:text/html,content", "file:///local.pdf", "about:blank",
            "chrome://downloads/", "chrome-extension://extension-id/page.html",
            "javascript:location='https://app.dext.com'", "",
        ] {
            assert!(scope.validate_url(url).is_err(), "{url}");
        }
    }

    #[test]
    fn auto_does_not_grant_effectful_or_script_actions() {
        for mode in ["supervised", "auto"] {
            let mut data = context();
            data["execution_mode"] = json!(mode);
            let scope = PlatformScope::from_value(&data).unwrap();
            for kind in [
                "click", "hold_click", "input", "vault", "keyboard", "scroll",
                "dialog", "run_script", "more", "index", "index_read",
                "exit_scrape_mode", "navigate_tab", "close_tab", "download",
                "call_function", "unknown", "",
            ] {
                let result = scope.validate_action(&json!({"type": kind, "value": "https://app.dext.com/"}));
                assert_eq!(result, Err(APPROVAL_UNAVAILABLE.to_string()), "{mode}: {kind}");
            }
            for kind in ["done", "wait", "todo_list", "update_todo", "scratchpad", "skills", "switch_tab"] {
                assert!(scope.validate_action(&json!({"type": kind})).is_ok(), "{kind}");
            }
            for kind in ["new_tab", "update_tab"] {
                assert!(scope.validate_action(&json!({"type": kind, "value": "https://app.dext.com/"})).is_err());
                assert!(scope.validate_action(&json!({"type": kind, "value": "https://app.dext.com.evil.test/"})).is_err());
                assert!(scope.validate_action(&json!({"type": kind})).is_err());
            }
        }
    }

    #[test]
    fn committed_pending_redirect_and_popup_urls_are_observed() {
        assert!(scope().observe_tabs(&tabs("https://app.dext.com/login"), Some("1"), &[], false).is_ok());
        for observed in [
            vec![json!({"id": "1", "url": "https://login.identity.test/"})],
            vec![json!({"id": "1", "url": "https://app.dext.com/", "pendingUrl": "https://app.dext.com.evil.test/"})],
            vec![json!({"id": "1", "url": "https://app.dext.com/"}), json!({"id": "2", "url": "https://popup.test/"})],
            vec![json!({"id": "1", "url": "https://app.dext.com/"}), json!({"id": "2", "url": "about:blank"})],
        ] {
            let mut policy = scope();
            assert!(policy.observe_tabs(&observed, Some("1"), &[], false).is_err());
            assert!(policy.violation().is_some());
        }
        let mut policy = scope();
        let transient = [
            json!({"tabId": 1, "url": "https://unexpected.identity.test/login"}),
            json!({"tabId": 1, "url": "https://app.dext.com/"}),
        ];
        assert!(policy.observe_tabs(&tabs("https://app.dext.com/"), Some("1"), &transient, false).is_err());
    }

    #[test]
    fn scope_violation_is_sticky_and_observation_failures_are_closed() {
        let mut policy = scope();
        let first = policy.observe_tabs(&tabs("https://outside.test/"), Some("1"), &[], false).unwrap_err();
        assert_eq!(policy.observe_tabs(&tabs("https://app.dext.com/"), Some("1"), &[], false), Err(first.clone()));
        assert_eq!(policy.validate_action(&json!({"type": "done"})), Err(first.clone()));
        assert_eq!(policy.fail("later message"), first);
        for (observed, current, events, overflow) in [
            (vec![], Some("1"), vec![], false),
            (tabs("https://app.dext.com/"), None, vec![], false),
            (tabs("https://app.dext.com/"), Some("missing"), vec![], false),
            (tabs("https://app.dext.com/"), Some("1"), vec![], true),
            (vec![json!({"id": "1"})], Some("1"), vec![], false),
            (vec![json!({"id": "1", "url": "https://app.dext.com/", "pendingUrl": 1})], Some("1"), vec![], false),
            (vec![json!({"id": "1", "url": "https://app.dext.com/"}); 2], Some("1"), vec![], false),
            (tabs("https://app.dext.com/"), Some("1"), vec![json!({"url": "https://app.dext.com/"})], false),
        ] {
            let mut policy = scope();
            assert!(policy.observe_tabs(&observed, current, &events, overflow).is_err());
            assert!(policy.violation().is_some());
        }
    }

    #[test]
    fn initial_blank_exemptions_are_narrow_and_never_action_targets() {
        let mut policy = scope();
        policy.allow_initial_blank("initial", "chrome://newtab/").unwrap();
        assert!(policy.allow_initial_blank("internal", "chrome://settings/").is_err());
        let mut observed = tabs("https://app.dext.com/");
        observed.push(json!({"id": "initial", "url": "chrome://newtab/"}));
        assert!(policy.observe_tabs(&observed, Some("1"), &[], false).is_ok());
        assert!(policy.allow_initial_blank("new", "about:blank").is_err());
        assert!(policy.observe_tabs(&observed, Some("initial"), &[], false).is_err());

        let mut policy = scope();
        policy.allow_initial_blank("2", "about:blank").unwrap();
        let allowed = vec![json!({"id": "1", "url": "https://app.dext.com/"}), json!({"id": "2", "url": "https://app.dext.com/"})];
        assert!(policy.observe_tabs(&allowed, Some("1"), &[], false).is_ok());
        let returned_blank = vec![json!({"id": "1", "url": "https://app.dext.com/"}), json!({"id": "2", "url": "about:blank"})];
        assert!(policy.observe_tabs(&returned_blank, Some("1"), &[], false).is_err());
    }

    #[test]
    fn only_the_known_bridge_wake_resource_can_be_an_undriven_startup_tab() {
        let mut policy = scope();
        let extension = "a".repeat(32);
        policy.allow_initial_bridge_wake("wake", &extension).unwrap();
        assert!(policy.allow_initial_bridge_wake("other", "invalid-extension").is_err());
        let mut observed = tabs("https://app.dext.com/");
        observed.push(json!({"id": "wake", "url": format!("chrome-extension://{extension}/wake.html")}));
        assert!(policy.observe_tabs(&observed, Some("1"), &[], false).is_ok());
        assert!(policy.observe_tabs(&observed, Some("wake"), &[], false).is_err());

        let mut policy = scope();
        policy.allow_initial_bridge_wake("wake", &extension).unwrap();
        observed[1]["url"] = json!(format!("chrome-extension://{extension}/settings.html"));
        assert!(policy.observe_tabs(&observed, Some("1"), &[], false).is_err());
    }

    #[test]
    fn native_created_blank_events_do_not_authorize_blank_snapshots() {
        let mut policy = scope();
        assert!(policy.observe_tabs(&tabs("https://app.dext.com/"), Some("1"), &[], false).is_ok());
        policy.allow_created_blank("2").unwrap();
        let events = [json!({"tabId": "2", "url": "about:blank"})];
        let allowed = vec![json!({"id": "1", "url": "https://app.dext.com/"}), json!({"id": "2", "url": "https://app.dext.com/login"})];
        assert!(policy.observe_tabs(&allowed, Some("2"), &events, false).is_ok());

        let mut policy = scope();
        policy.allow_created_blank("1").unwrap();
        let initial_event = [json!({"tabId": "1", "url": "about:blank"})];
        assert!(policy.observe_tabs(&tabs("about:blank"), Some("1"), &initial_event, false).is_err());
    }
}
