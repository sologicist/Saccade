//! The `skills` tool, the <skills> block and the <domain_knowledge> block,
//! both inside <persistent_memory>. Two different things:
//!
//! - skills (default_skills/web/skills): listed by id with their size, loaded
//!   into the input and removed again only when the agent asks (a run_script
//!   scrape loads the scraping skill when it opens scrape mode);
//! - domain knowledge (default_skills/web/domain_skill, tied to sites by
//!   skills.json: {"docs.google.com/spreadsheets": "google_sheets.md"}): no
//!   ids, no tool; it comes with the current tab's site and goes with it,
//!   on its own (`follow_url`).
//!
//! The state is the run's, not the history's: it survives scrape mode's
//! history retirement.

use std::collections::{BTreeMap, BTreeSet};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use serde::de::{self, Deserialize, Deserializer, MapAccess, Visitor};
use serde_json::{json, Value};
use url::Url;

use crate::agent::main_driver::view::py_str_of;
use crate::controller::service::{err, py_int_value, ActErr, ActResult};

/// The skill a scrape read needs, loaded as the mode opens (`load_named`).
pub const SCRAPING_SKILL: &str = "scraping.md";

const MAX_CONFIG_SIZE: u64 = 65_536;
const MAX_PROCEDURE_SIZE: u64 = 262_144;

struct Skill {
    name: String,
    path: PathBuf,
    /// About chars / 4, shown on the skill's line so the cost is known before a load.
    tokens: usize,
    loaded: bool,
}

struct Domain {
    name: String,
    root: PathBuf,
    canonical_root: PathBuf,
    /// Validated exact hosts and optional path scopes, without a scheme.
    sites: Vec<SiteScope>,
    /// The current tab is on one of its sites.
    on_site: bool,
}

static SKILLS: Mutex<Vec<Skill>> = Mutex::new(Vec::new());
static DOMAIN: Mutex<Vec<Domain>> = Mutex::new(Vec::new());

// Native-loop and domain contracts share the process-wide skill run state.
#[cfg(test)]
pub(crate) static STATE_TEST: Mutex<()> = Mutex::new(());

#[derive(Debug)]
struct SiteScope {
    key: String,
    host: String,
    path: Option<String>,
}

impl SiteScope {
    fn parse(key: &str) -> Option<Self> {
        let (host, path) = match key.split_once('/') {
            Some((host, path)) => (host, Some(format!("/{path}"))),
            None => (key, None),
        };
        if !valid_host(host) || path.as_deref().is_some_and(|p| !canonical_path(p)) {
            return None;
        }
        let path = path.and_then(|path| {
            let path = path.trim_end_matches('/');
            (!path.is_empty()).then(|| path.to_string())
        });
        Some(Self { key: key.to_string(), host: host.to_string(), path })
    }

    fn matches(&self, current: &CurrentSite) -> bool {
        if self.host != current.host {
            return false;
        }
        match &self.path {
            None => true,
            Some(scope) => {
                let Some(path) = current.path.as_deref() else { return false };
                path == scope.as_str() || path.starts_with(&format!("{scope}/"))
            }
        }
    }
}

fn valid_host(host: &str) -> bool {
    !host.is_empty()
        && host.len() <= 253
        && host.split('.').all(|label| {
            !label.is_empty()
                && label.len() <= 63
                && label.bytes().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'-')
                && !label.starts_with('-')
                && !label.ends_with('-')
        })
}

/// A manifest path must survive browser URL parsing unchanged. Encoded paths
/// and dot segments are ambiguous and cannot select a path-scoped procedure.
fn canonical_path(path: &str) -> bool {
    path.starts_with('/')
        && !path.contains("//")
        && path.bytes().all(|c| c.is_ascii_alphanumeric() || b"/-._~!$&'()+,;=:@".contains(&c))
        && !path.split('/').any(|part| part == "." || part == "..")
}

fn valid_skill_name(name: &str) -> bool {
    let Some(stem) = name.strip_suffix(".md") else { return false };
    !stem.is_empty()
        && stem.as_bytes()[0].is_ascii_alphanumeric()
        && stem.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
}

/// Deserialize directly from the JSON object so duplicate keys cannot be
/// silently overwritten before validation. Every invalid entry rejects it all.
struct DomainManifest(BTreeMap<String, String>);

impl<'de> Deserialize<'de> for DomainManifest {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct ManifestVisitor;
        impl<'de> Visitor<'de> for ManifestVisitor {
            type Value = DomainManifest;

            fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                f.write_str("an object mapping exact hosts and optional paths to Markdown filenames")
            }

            fn visit_map<M: MapAccess<'de>>(self, mut map: M) -> Result<Self::Value, M::Error> {
                let mut entries = BTreeMap::new();
                let mut scopes = BTreeSet::new();
                while let Some((site, file)) = map.next_entry::<String, String>()? {
                    if SiteScope::parse(&site).is_none() || !valid_skill_name(&file) {
                        return Err(de::Error::custom("invalid domain skill entry"));
                    }
                    if !scopes.insert(site.trim_end_matches('/').to_string()) || entries.insert(site, file).is_some() {
                        return Err(de::Error::custom("duplicate domain skill key"));
                    }
                }
                Ok(DomainManifest(entries))
            }
        }
        deserializer.deserialize_map(ManifestVisitor)
    }
}

struct CurrentSite {
    host: String,
    /// None for an ambiguous path; host-only skills remain available.
    path: Option<String>,
}

impl CurrentSite {
    fn parse(raw: &str) -> Option<Self> {
        if raw.chars().any(|c| c.is_whitespace() || c.is_control() || c == '\\') {
            return None;
        }
        let parsed = Url::parse(raw).ok()?;
        if !matches!(parsed.scheme(), "http" | "https")
            || !parsed.username().is_empty()
            || parsed.password().is_some()
            || parsed.port().is_some()
        {
            return None;
        }
        // Check the original authority too: URL parsing normalizes encoded
        // hosts, Unicode and extra slashes, none of which may widen a scope.
        let (scheme, rest) = raw.split_once("://")?;
        if !scheme.eq_ignore_ascii_case(parsed.scheme()) {
            return None;
        }
        let authority_end = rest.find(['/', '?', '#']).unwrap_or(rest.len());
        let authority = &rest[..authority_end];
        let (host, port) = match authority.split_once(':') {
            Some((host, port)) => (host, Some(port)),
            None => (authority, None),
        };
        let host = host.to_ascii_lowercase();
        if !valid_host(&host) || parsed.host_str()? != host {
            return None;
        }
        if let Some(port) = port {
            let default = if parsed.scheme() == "https" { "443" } else { "80" };
            if port != default {
                return None;
            }
        }
        let suffix = &rest[authority_end..];
        let path_end = suffix.find(['?', '#']).unwrap_or(suffix.len());
        let raw_path = &suffix[..path_end];
        let path = if raw_path.is_empty() { "/" } else { raw_path };
        let path = (canonical_path(path) && parsed.path() == path).then(|| path.to_string());
        Some(Self { host, path })
    }
}

fn link_or_reparse(meta: &std::fs::Metadata) -> bool {
    if meta.file_type().is_symlink() {
        return true;
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        // Directory junctions are reparse points too, but are not necessarily
        // reported as symlinks by FileType.
        if meta.file_attributes() & 0x400 != 0 {
            return true;
        }
    }
    false
}

fn safe_domain_root(root: &Path, canonical_root: &Path) -> bool {
    let absolute = if root.is_absolute() {
        root.to_path_buf()
    } else {
        let Ok(cwd) = std::env::current_dir() else { return false };
        cwd.join(root)
    };
    absolute.ancestors().all(|path| {
        std::fs::symlink_metadata(path).is_ok_and(|meta| meta.is_dir() && !link_or_reparse(&meta))
    }) && root.canonicalize().is_ok_and(|path| path == canonical_root)
}

/// Read only bounded, ordinary files below a directory with no symbolic or
/// reparse ancestors. Recheck at render time to refuse later replacements.
/// These checks do not make a hostile concurrent swap/revert race an atomic
/// filesystem security boundary; procedure files must stay operator controlled.
fn read_domain_file(root: &Path, canonical_root: &Path, name: &str, limit: u64) -> Option<String> {
    if !safe_domain_root(root, canonical_root) {
        return None;
    }
    let path = root.join(name);
    let expected = canonical_root.join(name);
    let meta = std::fs::symlink_metadata(&path).ok()?;
    if !meta.is_file() || link_or_reparse(&meta) || meta.len() > limit || path.canonicalize().ok()? != expected {
        return None;
    }
    let file = std::fs::File::open(&path).ok()?;
    let mut bytes = Vec::new();
    file.take(limit + 1).read_to_end(&mut bytes).ok()?;
    if bytes.len() as u64 > limit {
        return None;
    }
    let content = String::from_utf8(bytes).ok()?;
    // A replacement during a read also invalidates that render.
    let after = std::fs::symlink_metadata(&path).ok()?;
    if link_or_reparse(&after)
        || !after.is_file()
        || after.len() > limit
        || path.canonicalize().ok()? != expected
        || !safe_domain_root(root, canonical_root)
    {
        return None;
    }
    Some(content)
}

fn load_domains(root: &Path) -> Option<Vec<Domain>> {
    let canonical_root = root.canonicalize().ok()?;
    let manifest = read_domain_file(root, &canonical_root, "skills.json", MAX_CONFIG_SIZE)?;
    let DomainManifest(manifest) = serde_json::from_str(&manifest).ok()?;
    let mut by_file: BTreeMap<String, Vec<SiteScope>> = BTreeMap::new();
    for (site, file) in manifest {
        by_file.entry(file).or_default().push(SiteScope::parse(&site)?);
    }
    let mut domains = Vec::new();
    for (name, sites) in by_file {
        // Contents are checked only when this domain applies. A missing skill
        // for another site must not disable otherwise valid domain knowledge.
        domains.push(Domain { name, root: root.to_path_buf(), canonical_root: canonical_root.clone(), sites, on_site: false });
    }
    Some(domains)
}

/// A run starts with the skill files of `dir` (in name order), none loaded,
/// and the domain knowledge `domain_dir`/skills.json names, none on.
pub fn new_run(dir: &Path, domain_dir: &Path) {
    let mut paths: Vec<PathBuf> = std::fs::read_dir(dir)
        .map(|rd| {
            rd.flatten()
                .map(|e| e.path())
                .filter(|p| p.extension().is_some_and(|x| x == "md"))
                .collect()
        })
        .unwrap_or_default();
    paths.sort();
    let skills = paths
        .into_iter()
        .map(|path| {
            let name = file_name(&path);
            let chars = std::fs::read_to_string(&path).map(|s| s.chars().count()).unwrap_or(0);
            Skill { name, path, tokens: chars / 4, loaded: false }
        })
        .collect();
    if let Ok(mut s) = SKILLS.lock() {
        *s = skills;
    }
    // Invalid manifests fail closed together. Applicable skill files are
    // guarded at render time; generic skills remain independently available.
    let domain = load_domains(domain_dir).unwrap_or_default();
    if let Ok(mut d) = DOMAIN.lock() {
        *d = domain;
    }
}

fn file_name(path: &Path) -> String {
    path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default()
}

/// The current tab's url: the domain knowledge of its site comes on, the
/// rest goes off. Called every step before the blocks are rendered.
pub fn follow_url(url: &str) {
    let current = CurrentSite::parse(url);
    if let Ok(mut domain) = DOMAIN.lock() {
        for d in domain.iter_mut() {
            d.on_site = current.as_ref().is_some_and(|url| d.sites.iter().any(|site| site.matches(url)));
        }
    }
}

/// The `skills` tool: `kind` is "load" or "remove", `raw_id` the skill's [id].
pub fn run(kind: &Value, raw_id: &Value) -> ActResult<Value> {
    let kind = if kind.is_null() { String::new() } else { py_str_of(kind).trim().to_lowercase() };
    if kind != "load" && kind != "remove" {
        return err("skills' `type` is \"load\" (into <skills>) or \"remove\" (out of it)");
    }
    let id = match py_int_value(raw_id) {
        Ok(i) => i,
        Err(_) => return err(format!("'{}' is not a skill id", py_str_of(raw_id))),
    };
    let mut skills = SKILLS.lock().map_err(|_| ActErr::Msg("skills state poisoned".into()))?;
    if skills.is_empty() {
        return err("there are no skills to load");
    }
    let n = skills.len();
    let Some(skill) = (id >= 1).then(|| skills.get_mut((id - 1) as usize)).flatten() else {
        return err(format!("there is no skill [{id}] - <skills> lists [1] to [{n}]"));
    };
    let message = match (kind.as_str(), skill.loaded) {
        ("load", true) => format!("skill [{id}] {} is already loaded", skill.name),
        ("load", false) => {
            skill.loaded = true;
            format!(
                "skill [{id}] {} loaded ({}): its content is in <skills> from the next step on, until you remove it",
                skill.name,
                size(skill.tokens)
            )
        }
        ("remove", false) => format!("skill [{id}] {} is not loaded", skill.name),
        _ => {
            skill.loaded = false;
            format!("skill [{id}] {} removed from <skills>", skill.name)
        }
    };
    Ok(json!({"status": "success", "tool": "skills", "type": kind, "id": id, "message": message}))
}

/// Load the skill called `name`, if there is one and it is not loaded yet.
pub fn load_named(name: &str) {
    if let Ok(mut skills) = SKILLS.lock() {
        if let Some(s) = skills.iter_mut().find(|s| s.name == name) {
            s.loaded = true;
        }
    }
}

/// <skills>: one line per skill, [id] name (size), and under a loaded one its
/// content as the file holds it. Empty when there are no skill files.
pub fn block() -> String {
    let Ok(skills) = SKILLS.lock() else {
        return String::new();
    };
    if skills.is_empty() {
        return String::new();
    }
    let mut lines: Vec<String> = Vec::new();
    for (i, s) in skills.iter().enumerate() {
        let line = format!("[{}] {} ({})", i + 1, s.name, size(s.tokens));
        if s.loaded {
            let content = std::fs::read_to_string(&s.path).unwrap_or_default();
            lines.push(format!("{line} - loaded\n{}\n", content.trim()));
        } else {
            lines.push(line);
        }
    }
    format!("<skills>\n{}\n</skills>", lines.join("\n"))
}

/// <domain_knowledge>: the files of the current tab's site, each named with
/// its site and given in full. Empty when the tab is on no known site.
pub fn domain_block() -> String {
    domain_block_for(None)
}

/// Scoped sessions retain native URL matching while exposing only the selected
/// platform's procedure. A recognized URL does not activate another platform.
pub fn domain_block_for(selected: Option<&str>) -> String {
    let Ok(domain) = DOMAIN.lock() else {
        return String::new();
    };
    let mut shown = Vec::new();
    for d in domain.iter().filter(|d| d.on_site && selected.is_none_or(|name| d.name == name)) {
        // Fail closed across all procedures applying to the current URL. A
        // file for another domain is neither read nor required for this block.
        let Some(content) = read_domain_file(&d.root, &d.canonical_root, &d.name, MAX_PROCEDURE_SIZE) else {
            return String::new();
        };
        if !content.trim().is_empty() {
            let sites: Vec<&str> = d.sites.iter().map(|site| site.key.as_str()).collect();
            shown.push(format!("{} - {}\n{}", d.name, sites.join(", "), content.trim()));
        }
    }
    if shown.is_empty() {
        String::new()
    } else {
        format!("<domain_knowledge>\n{}\n</domain_knowledge>", shown.join("\n\n"))
    }
}

fn size(tokens: usize) -> String {
    format!("{:.1}k tokens", tokens as f64 / 1000.0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    // Only tests exercising the native run state need serialization. Pure
    // manifest and URL validation tests never touch the process-wide state.

    struct Fixture(PathBuf);

    impl Fixture {
        fn new() -> Self {
            static NEXT: AtomicU64 = AtomicU64::new(0);
            let root = std::env::temp_dir().join(format!(
                "saccade-domain-skills-{}-{}-{}",
                std::process::id(),
                std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            std::fs::create_dir(&root).unwrap();
            #[cfg(windows)]
            { Self(root) }
            #[cfg(not(windows))]
            { Self(root.canonicalize().unwrap()) }
        }

        fn write(&self, name: &str, text: &str) {
            std::fs::write(self.0.join(name), text).unwrap();
        }

        fn catalog(&self) {
            self.write("skills.json", r#"{
                "app.dext.com": "dext.md",
                "docs.google.com/spreadsheets": "google_sheets.md"
            }"#);
            self.write("dext.md", "Dext procedure: prepare a supervised draft.");
            self.write("google_sheets.md", "Google Sheets procedure.");
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            // Each fixture owns a fresh synthetic directory, never user data.
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    fn matches(scope: &str, url: &str) -> bool {
        let scope = SiteScope::parse(scope).unwrap();
        CurrentSite::parse(url).is_some_and(|url| scope.matches(&url))
    }

    #[test]
    fn domain_hosts_match_exactly_and_urls_are_parsed() {
        for url in [
            "https://app.dext.com/login",
            "https://APP.DEXT.COM/login?next=%2Finvoices#main",
            "http://app.dext.com/invoices",
            "https://app.dext.com:443/invoices/record%2Fid",
            "http://app.dext.com:80",
            "https://app.dext.com",
        ] {
            assert!(matches("app.dext.com", url), "{url}");
        }
        assert!(matches("app.dext.com/", "https://app.dext.com/record%2Fid"));
        for url in [
            "https://app.dext.com.evil.test/login",
            "https://evilapp.dext.com/login",
            "https://child.app.dext.com/login",
            "https://app.dext.com@evil.test/login",
            "https://user@app.dext.com/login",
            "https://:password@app.dext.com/login",
            "https://app.dext.com:8443/login",
            "https://app.dext.com:80/login",
            "https://app.dext.com:/login",
            "https://app.dext.com./login",
            "https://%61pp.dext.com/login",
            "https:///app.dext.com/login",
            "https://app.dext.com\\@evil.test/login",
            " https://app.dext.com/login",
            "https://app.dext.com/login\n",
            "https://app.dext.com/white space",
            "file://app.dext.com/login",
            "ftp://app.dext.com/login",
            "chrome://app.dext.com/login",
            "javascript:https://app.dext.com",
            "app.dext.com/login",
            "about:blank",
            "",
        ] {
            assert!(!matches("app.dext.com", url), "{url}");
        }
    }

    #[test]
    fn domain_path_scopes_respect_segment_boundaries() {
        for scope in ["docs.google.com/spreadsheets", "docs.google.com/spreadsheets/"] {
            for url in [
                "https://docs.google.com/spreadsheets",
                "https://docs.google.com/spreadsheets/",
                "https://docs.google.com/spreadsheets/d/synthetic-id/edit?gid=0#range=A1",
            ] {
                assert!(matches(scope, url), "{scope}: {url}");
            }
            for url in [
                "https://docs.google.com/spreadsheets-evil",
                "https://docs.google.com/spreadsheets2/",
                "https://docs.google.com/document/d/id",
                "https://sub.docs.google.com/spreadsheets",
                "https://docs.google.com.evil.test/spreadsheets",
                "https://docs.google.com/spreadsheets%2Fevil",
                "https://docs.google.com/spreadsheets/%2e%2e/document",
                "https://docs.google.com/document/../spreadsheets",
                "https://docs.google.com//spreadsheets",
                "https://docs.google.com/spreadsheets//d/id",
            ] {
                assert!(!matches(scope, url), "{scope}: {url}");
            }
        }
        assert!(matches("docs.google.com/", "https://docs.google.com/spreadsheets"));
    }

    #[test]
    fn manifest_accepts_only_canonical_hosts_paths_and_simple_markdown_names() {
        let valid = r#"{"app.dext.com":"dext.md","docs.google.com/spreadsheets/":"google_sheets.md","other.test/path-one/v2":"Procedure-2.md"}"#;
        assert_eq!(serde_json::from_str::<DomainManifest>(valid).unwrap().0.len(), 3);
        assert!(serde_json::from_str::<DomainManifest>("{}").is_ok());
        for key in [
            "", "App.dext.com", "https://app.dext.com", "http://app.dext.com",
            "*.dext.com", "app.dext.com:443", "user@app.dext.com", "app.dext.com?x=1",
            "app.dext.com#fragment", "app.dext.com/path?x=1", "app.dext.com/path#part",
            "app.dext.com/with space", "app.dext.com/path\\other", "app.dext.com/path%2fother",
            "app.dext.com//path", "app.dext.com/a/../b", "app.dext.com/./path",
            "app.dext.com/path/*", "app.dext.com.", ".app.dext.com", "app..dext.com",
            "-app.dext.com", "app-.dext.com", "äpp.dext.com", "app.dext.com\n",
        ] {
            let manifest = json!({key: "dext.md"}).to_string();
            assert!(serde_json::from_str::<DomainManifest>(&manifest).is_err(), "{key}");
        }
        for file in [
            "", "../secret.md", "/secret.md", "C:\\secret.md", "nested/dext.md",
            "nested\\dext.md", ".hidden.md", "dext.MD", "dext.txt", "a.b.md",
            "dext md", "dext.md/", "dext.md\n", "_dext.md", "-dext.md",
        ] {
            let manifest = json!({"app.dext.com": file}).to_string();
            assert!(serde_json::from_str::<DomainManifest>(&manifest).is_err(), "{file}");
        }
        assert!(!valid_host(&format!("{}.test", "a".repeat(64))));
        let longest = format!("{}.{}.{}.{}", "a".repeat(63), "b".repeat(63), "c".repeat(63), "d".repeat(61));
        assert!(valid_host(&longest));
        assert!(!valid_host(&format!("{longest}e")));
    }

    #[test]
    fn manifest_rejects_duplicates_types_and_partial_valid_catalogs() {
        for invalid in [
            r#"{"app.dext.com":"dext.md","app.dext.com":"other.md"}"#,
            r#"{"app.dext.com":"dext.md","app\u002edext.com":"other.md"}"#,
            r#"{"app.dext.com":"dext.md","app.dext.com/":"other.md"}"#,
            r#"{"docs.google.com/spreadsheets":"sheets.md","docs.google.com/spreadsheets/":"other.md"}"#,
            r#"{"app.dext.com":"dext.md","other.test":"../outside.md"}"#,
            r#"{"app.dext.com":null}"#,
            r#"{"app.dext.com":["dext.md"]}"#,
            r#"{"app.dext.com":{"file":"dext.md"}}"#,
            r#"{"app.dext.com":1}"#,
            r#"[]"#,
            r#"null"#,
            r#""text""#,
            "{",
        ] {
            assert!(serde_json::from_str::<DomainManifest>(invalid).is_err(), "{invalid}");
        }
    }

    #[test]
    fn native_domain_block_follows_current_url_and_preserves_generic_skills() {
        let _state = STATE_TEST.lock().unwrap();
        let domain = Fixture::new();
        let generic = Fixture::new();
        domain.catalog();
        generic.write("scraping.md", "Generic scraping procedure.");
        new_run(&generic.0, &domain.0);
        assert!(domain_block().is_empty());
        assert!(block().contains("[1] scraping.md"));
        assert!(!block().contains("Generic scraping procedure."));
        assert!(run(&json!("load"), &json!(1)).is_ok());
        assert!(block().contains("Generic scraping procedure."));

        follow_url("https://app.dext.com/invoices");
        let dext = domain_block();
        assert!(dext.starts_with("<domain_knowledge>\n"));
        assert!(dext.contains("dext.md - app.dext.com"));
        assert!(dext.contains("Dext procedure: prepare a supervised draft."));
        assert!(!dext.contains("Google Sheets procedure."));

        follow_url("https://docs.google.com/spreadsheets/d/synthetic-id/edit");
        let sheets = domain_block();
        assert!(sheets.contains("Google Sheets procedure."));
        assert!(!sheets.contains("Dext procedure"));
        for url in ["https://unrelated.test/", "https://app.dext.com.evil.test/", "about:blank"] {
            follow_url(url);
            assert!(domain_block().is_empty(), "{url}");
        }
        assert!(block().contains("Generic scraping procedure."));
        assert!(run(&json!("remove"), &json!(1)).is_ok());
        assert!(!block().contains("Generic scraping procedure."));
        load_named(SCRAPING_SKILL);
        assert!(block().contains("Generic scraping procedure."));
        new_run(&generic.0, &domain.0);
        assert!(domain_block().is_empty());
        assert!(!block().contains("Generic scraping procedure."));
    }

    #[test]
    fn selected_platform_keeps_native_url_matching_without_other_domain_procedures() {
        let _state = STATE_TEST.lock().unwrap();
        let domain = Fixture::new();
        let generic = Fixture::new();
        domain.catalog();
        domain.write("skills.json", r#"{
            "app.dext.com":"dext.md",
            "app.dext.com/shared":"google_sheets.md"
        }"#);
        new_run(&generic.0, &domain.0);
        follow_url("https://app.dext.com/shared");
        assert!(domain_block().contains("Google Sheets procedure."));
        let selected = domain_block_for(Some("dext.md"));
        assert!(selected.contains("Dext procedure"));
        assert!(!selected.contains("Google Sheets procedure."));
        domain.write("dext.md", "");
        assert!(domain_block_for(Some("dext.md")).is_empty());
        follow_url("https://app.dext.com.evil.test/shared");
        assert!(domain_block_for(Some("dext.md")).is_empty());
    }

    #[test]
    fn invalid_or_missing_domain_catalog_does_not_disable_generic_skills() {
        let _state = STATE_TEST.lock().unwrap();
        let domain = Fixture::new();
        let generic = Fixture::new();
        generic.write("scraping.md", "Generic scraping procedure.");
        for manifest in [
            r#"{"app.dext.com":"dext.md","other.test":"../outside.md"}"#,
            r#"{"app.dext.com":"dext.md","app.dext.com":"dext.md"}"#,
        ] {
            domain.write("skills.json", manifest);
            domain.write("dext.md", "Dext procedure.");
            new_run(&generic.0, &domain.0);
            follow_url("https://app.dext.com/login");
            assert!(domain_block().is_empty(), "{manifest}");
            load_named(SCRAPING_SKILL);
            assert!(block().contains("Generic scraping procedure."));
        }
        new_run(&generic.0, &domain.0.join("missing"));
        follow_url("https://app.dext.com/login");
        assert!(domain_block().is_empty());
    }

    #[test]
    fn empty_or_removed_skills_do_not_render_broken_domain_blocks() {
        let _state = STATE_TEST.lock().unwrap();
        let domain = Fixture::new();
        let generic = Fixture::new();
        domain.catalog();
        domain.write("dext.md", " \n\t");
        new_run(&generic.0, &domain.0);
        follow_url("https://app.dext.com/login");
        assert!(domain_block().is_empty());
        domain.write("dext.md", "Updated procedure.");
        assert!(domain_block().contains("Updated procedure."));
        std::fs::remove_file(domain.0.join("google_sheets.md")).unwrap();
        assert!(domain_block().contains("Updated procedure."));
        std::fs::remove_file(domain.0.join("dext.md")).unwrap();
        assert!(domain_block().is_empty());
        domain.write("dext.md", "Restored procedure.");
        assert!(domain_block().contains("Restored procedure."));
    }

    #[test]
    fn unrelated_missing_files_do_not_disable_the_active_domain() {
        let _state = STATE_TEST.lock().unwrap();
        let domain = Fixture::new();
        let generic = Fixture::new();
        domain.catalog();
        new_run(&generic.0, &domain.0);
        follow_url("https://app.dext.com/login");
        assert!(domain_block().contains("Dext procedure"));

        std::fs::remove_file(domain.0.join("google_sheets.md")).unwrap();
        assert!(domain_block().contains("Dext procedure"));
        follow_url("https://docs.google.com/spreadsheets/d/synthetic-id/edit");
        assert!(domain_block().is_empty());
        domain.write("google_sheets.md", "Restored Sheets procedure.");
        assert!(domain_block().contains("Restored Sheets procedure."));

        // Startup validates the manifest independently of other sites' files.
        std::fs::remove_file(domain.0.join("google_sheets.md")).unwrap();
        new_run(&generic.0, &domain.0);
        follow_url("https://app.dext.com/login");
        assert!(domain_block().contains("Dext procedure"));
        follow_url("https://docs.google.com/spreadsheets/d/synthetic-id/edit");
        assert!(domain_block().is_empty());
        domain.write("google_sheets.md", "Sheets restored after startup.");
        assert!(domain_block().contains("Sheets restored after startup."));
    }

    #[test]
    fn unsafe_content_is_rejected_only_when_its_domain_applies() {
        let _state = STATE_TEST.lock().unwrap();
        let domain = Fixture::new();
        let generic = Fixture::new();
        domain.catalog();
        for bytes in [vec![0xff], vec![b'x'; MAX_PROCEDURE_SIZE as usize + 1]] {
            std::fs::write(domain.0.join("google_sheets.md"), bytes).unwrap();
            new_run(&generic.0, &domain.0);
            follow_url("https://app.dext.com/login");
            assert!(domain_block().contains("Dext procedure"));
            follow_url("https://docs.google.com/spreadsheets/d/synthetic-id/edit");
            assert!(domain_block().is_empty());
        }
        std::fs::remove_file(domain.0.join("google_sheets.md")).unwrap();
        std::fs::create_dir(domain.0.join("google_sheets.md")).unwrap();
        new_run(&generic.0, &domain.0);
        follow_url("https://app.dext.com/login");
        assert!(domain_block().contains("Dext procedure"));
        follow_url("https://docs.google.com/spreadsheets/d/synthetic-id/edit");
        assert!(domain_block().is_empty());
    }

    #[test]
    fn all_applicable_procedures_fail_closed_if_one_is_unavailable() {
        let _state = STATE_TEST.lock().unwrap();
        let domain = Fixture::new();
        let generic = Fixture::new();
        domain.catalog();
        domain.write("skills.json", r#"{
            "app.dext.com": "dext.md",
            "app.dext.com/invoices": "invoice_safety.md",
            "docs.google.com/spreadsheets": "google_sheets.md"
        }"#);
        new_run(&generic.0, &domain.0);
        follow_url("https://app.dext.com/login");
        assert!(domain_block().contains("Dext procedure"));
        follow_url("https://app.dext.com/invoices/synthetic-id");
        assert!(domain_block().is_empty());
        domain.write("invoice_safety.md", "Synthetic invoice safety procedure.");
        let restored = domain_block();
        assert!(restored.contains("Dext procedure"));
        assert!(restored.contains("Synthetic invoice safety procedure."));
        std::fs::remove_file(domain.0.join("dext.md")).unwrap();
        assert!(domain_block().is_empty());
        follow_url("https://docs.google.com/spreadsheets/d/synthetic-id/edit");
        assert!(domain_block().contains("Google Sheets procedure."));
    }

    #[test]
    fn domain_reads_enforce_size_limits_and_utf8_at_load_and_render() {
        let _state = STATE_TEST.lock().unwrap();
        let domain = Fixture::new();
        let generic = Fixture::new();
        let manifest = format!("{{}}{}", " ".repeat(MAX_CONFIG_SIZE as usize - 2));
        domain.write("skills.json", &manifest);
        assert!(load_domains(&domain.0).is_some());
        domain.write("skills.json", &format!("{manifest} "));
        assert!(load_domains(&domain.0).is_none());
        std::fs::write(domain.0.join("skills.json"), [0xff]).unwrap();
        assert!(load_domains(&domain.0).is_none());

        domain.write("skills.json", r#"{"app.dext.com":"dext.md"}"#);
        let largest = "p".repeat(MAX_PROCEDURE_SIZE as usize);
        domain.write("dext.md", &largest);
        assert!(load_domains(&domain.0).is_some());
        new_run(&generic.0, &domain.0);
        follow_url("https://app.dext.com/login");
        assert!(domain_block().contains(&largest));
        domain.write("dext.md", &format!("{largest}p"));
        assert!(domain_block().is_empty());
        new_run(&generic.0, &domain.0);
        follow_url("https://app.dext.com/login");
        assert!(domain_block().is_empty());
        std::fs::write(domain.0.join("dext.md"), [0xff]).unwrap();
        assert!(domain_block().is_empty());
        new_run(&generic.0, &domain.0);
        follow_url("https://app.dext.com/login");
        assert!(domain_block().is_empty());
    }

    #[cfg(any(unix, windows))]
    fn link_file(target: &Path, link: &Path) -> std::io::Result<()> {
        #[cfg(unix)]
        { std::os::unix::fs::symlink(target, link) }
        #[cfg(windows)]
        { std::os::windows::fs::symlink_file(target, link) }
    }

    #[cfg(any(unix, windows))]
    fn link_dir(target: &Path, link: &Path) -> std::io::Result<()> {
        #[cfg(unix)]
        { std::os::unix::fs::symlink(target, link) }
        #[cfg(windows)]
        { std::os::windows::fs::symlink_dir(target, link) }
    }

    #[cfg(any(unix, windows))]
    fn symlink_available(result: std::io::Result<()>) -> bool {
        match result {
            Ok(()) => true,
            // Windows may deny symlink creation without Developer Mode. The
            // same tests run fully on Unix and on Windows with that privilege.
            Err(error) if cfg!(windows) && error.raw_os_error() == Some(1314) => {
                eprintln!("Skipping symlink assertions: Windows symlink privilege is unavailable.");
                false
            }
            Err(error) => panic!("could not create a synthetic symlink: {error}"),
        }
    }

    #[cfg(any(unix, windows))]
    #[test]
    fn symlinked_skills_manifests_and_roots_fail_closed() {
        let _state = STATE_TEST.lock().unwrap();
        let domain = Fixture::new();
        let outside = Fixture::new();
        let generic = Fixture::new();
        domain.catalog();
        outside.write("private.md", "Synthetic private content, never inject.");
        new_run(&generic.0, &domain.0);
        follow_url("https://app.dext.com/login");
        assert!(domain_block().contains("Dext procedure"));
        std::fs::remove_file(domain.0.join("dext.md")).unwrap();
        if !symlink_available(link_file(&outside.0.join("private.md"), &domain.0.join("dext.md"))) {
            return;
        }
        assert!(domain_block().is_empty());
        new_run(&generic.0, &domain.0);
        follow_url("https://app.dext.com/login");
        assert!(domain_block().is_empty());
        std::fs::remove_file(domain.0.join("dext.md")).unwrap();
        domain.write("dext.md", "Dext procedure.");
        std::fs::remove_file(domain.0.join("google_sheets.md")).unwrap();
        link_file(&outside.0.join("private.md"), &domain.0.join("google_sheets.md")).unwrap();
        new_run(&generic.0, &domain.0);
        follow_url("https://app.dext.com/login");
        assert!(domain_block().contains("Dext procedure."));
        follow_url("https://docs.google.com/spreadsheets/d/synthetic-id/edit");
        assert!(domain_block().is_empty());
        std::fs::remove_file(domain.0.join("google_sheets.md")).unwrap();
        domain.write("google_sheets.md", "Google Sheets procedure.");
        outside.write("manifest.json", r#"{"app.dext.com":"dext.md"}"#);
        std::fs::remove_file(domain.0.join("skills.json")).unwrap();
        link_file(&outside.0.join("manifest.json"), &domain.0.join("skills.json")).unwrap();
        assert!(load_domains(&domain.0).is_none());

        let root_link = outside.0.join("linked-domain");
        link_dir(&domain.0, &root_link).unwrap();
        assert!(load_domains(&root_link).is_none());
        // Remove the synthetic link explicitly; never recurse through it.
        std::fs::remove_dir(&root_link).or_else(|_| std::fs::remove_file(&root_link)).unwrap();

        let alias = outside.0.join("linked-parent");
        link_dir(&domain.0, &alias).unwrap();
        let nested = domain.0.join("nested-domain");
        std::fs::create_dir(&nested).unwrap();
        std::fs::write(nested.join("skills.json"), "{}").unwrap();
        assert!(load_domains(&nested).is_some());
        assert!(load_domains(&alias.join("nested-domain")).is_none());
        std::fs::remove_dir(&alias).or_else(|_| std::fs::remove_file(&alias)).unwrap();

        let holder = Fixture::new();
        let root = holder.0.join("catalog");
        std::fs::create_dir(&root).unwrap();
        std::fs::write(root.join("skills.json"), r#"{"app.dext.com":"dext.md"}"#).unwrap();
        std::fs::write(root.join("dext.md"), "Dext procedure.").unwrap();
        new_run(&generic.0, &root);
        follow_url("https://app.dext.com/login");
        assert!(domain_block().contains("Dext procedure."));
        std::fs::rename(&root, holder.0.join("saved-catalog")).unwrap();
        link_dir(&outside.0, &root).unwrap();
        assert!(domain_block().is_empty());
        std::fs::remove_dir(&root).or_else(|_| std::fs::remove_file(&root)).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn junction_ancestors_fail_closed() {
        let holder = Fixture::new();
        let target = holder.0.join("real-parent");
        let nested = target.join("domain");
        std::fs::create_dir_all(&nested).unwrap();
        std::fs::write(nested.join("skills.json"), "{}").unwrap();
        assert!(load_domains(&nested).is_some());
        let link = holder.0.join("junction-parent");
        // mklink is a cmd builtin. Refuse shell metacharacters in either
        // synthetic argument rather than interpreting a configured temp path.
        if [&link, &target].iter().any(|path| {
            path.to_str().is_none_or(|text| text.chars().any(|c| "&|<>^%!\"\r\n".contains(c)))
        }) {
            return;
        }
        let output = std::process::Command::new("cmd")
            .args(["/d", "/c", "mklink", "/J"])
            .arg(&link)
            .arg(&target)
            .output()
            .unwrap();
        assert!(output.status.success(), "could not create a synthetic junction");
        assert!(load_domains(&link.join("domain")).is_none());
        std::fs::remove_dir(link).unwrap();
    }
}
