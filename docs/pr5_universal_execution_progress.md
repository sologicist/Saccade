# PR5 universal execution: partial implementation checkpoint

This is an incomplete checkpoint on `feat/dext-live-navigation-learning`, not an
acceptance report. The complete requested execution/authorization integration is
not implemented. No real Chrome/Dext or external provider validation is claimed.

## Source findings and implemented changes

The native scanner/controller already powers both modes. The mismatch comes
from `PlatformScope.validate_action`, which denied interaction tools globally
and applied an extra URL-navigation prohibition to Dext. The business gate,
catalogue, worker and schemas still contain legacy Dext contracts. Download
events currently prove lifecycle observations only, not an authorized document
receipt; browser-level download denial is reapplied during scoped observations.

The current change removes the Dext-specific URL-navigation branch. All selected
platforms now use the same explicit HTTPS/exact-host contract for `new_tab` and
`update_tab`, through the existing native tab controller. Scroll is available in
Supervised mode through the normal observed-region/native wheel implementation.
Auto mode's scroll permissions were not broadened. No effect permissions are
derived from learned Markdown or platform names. Foreign hosts, download and
business-function grants remain independently gated.

The synthetic installation helper now accepts a platform ID, host and landmark
configuration. A new test installs three independent platforms and verifies
separate publication, immutable conversation pins and loading approved guidance
in future conversations, without changing any shared learning code. Another
native test compares URL-navigation policy on Dext and three other identities.
These tests do not establish three-platform business execution or download parity.

## Exact changed files at this checkpoint

```text
AutoCua/web/platform_scope.rs
AutoCua/web/controller/view.rs
tests/platform_learning_fixtures.py
tests/test_platform_learning.py
docs/pr5_universal_execution_progress.md
```

The initial worktree already contained the first two files' scroll change; it
was preserved. No baseline Markdown, private accounting/client data or approved
`learning.md` was edited. No commit, staging, push or merge was performed.

## Remaining implementation required for acceptance

- A shared operator authorization contract, separate from learning approval,
  binding an exact operation, verified target, destination/function, policy
  revision, session/run and one-use decision. Unknown high-impact interactions
  need a focused approval, not a wholesale manual-navigation fallback.
- Native enforcement of that authority on ordinary clicks and supported form
  interactions, including stale target and uncertain-effect handling. Browser
  Back must check the destination before dispatch, in both native and bridge
  history implementations; post-navigation host checks alone are insufficient.
- An authorized download state machine on the existing transport, with exact
  document/frame/operation binding, verified completion and local destination,
  rejection of unrelated downloads and restoration of denial. Simply relaxing
  `Browser.setDownloadBehavior` is not the required contract.
- A generic installed capability catalogue/dispatch interface and worker path.
  Keep current Dext business implementation behind a compatibility adapter;
  do not expose its synthetic receipt or accounting assumptions as universal
  permissions. Actual downloaded-PDF Scribe integration remains unavailable.
- A common correction-to-execution flow with exact learning approval, followed
  by end-to-end tests on three platforms with different registered functions
  and approval requirements, not only different learning vocabularies.

The existing baseline + checked immutable pinned overlay loading, atomic
`platforms/<id>/data/navigation/learning.md` projection, revisions, recovery,
cross-platform isolation, natural authentication replies and retained-browser
continuation remain the implementation to extend. There is no new orchestrator,
browser driver, editable `platform.md` or parallel conversation service.

## Actual checks for this checkpoint

- Full Python discovery via `.cache/operator-validation/run_python.py`: 253
  tests, **242 passed, 11 existing Windows symlink-privilege skips**, no failures.
  This includes ten compiled native-entry and four wheel/sdist integration tests.
- `cargo check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml`: passed.
- `cargo test --locked --offline --manifest-path AutoCua/web/Cargo.toml`:
  **53 passed, 2 ignored** (internal pipe child helper and opt-in real Chrome).
- Existing bridge/selection/operator/composer JavaScript suites: **45 passed**.
- `npm.cmd --prefix AutoCua/ui run typecheck` and `run build`: passed.
- Maturin offline development wheel and source distribution rebuilt successfully
  under `.cache/operator-wheels` and `.cache/operator-sdist` and inspected by the
  Python suite. Existing nonfatal sdist metadata/probe warnings remain.
- `git diff --check`: passed, with the existing generated-bundle LF/CRLF warning.
- Linux Rust was not run; the previously checked local WSL environment contains
  Docker Desktop without Cargo. No remote CI was started and no Linux success
  is claimed. No real browser, Dext session or external provider was exercised.

These results establish regression safety for this limited change. They do not
establish the requested universal execution, authorization or download workflow.
