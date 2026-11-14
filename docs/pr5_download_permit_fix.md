# PR5 native download permit correction

Branch: `feat/dext-live-navigation-learning`. Starting commit: `8535cb2`.
The initial working tree was clean. No commit, push, merge, client-data access,
API-key access or real Chrome/profile operation was performed.

## Confirmed cause

`ControllerView::operator_execution` consumed the operator's download decision
and called `ScannerInner::download_observed`, but did not arm a native gesture
permit. `bridge_request` did not recognize `download_observed` as a permitted
scoped command. It returned `APPROVAL_UNAVAILABLE`, which the controller reduced
to the generic `execution_not_verified` diagnostic.

The native integration fixture also returned `business_test_download` before
calling `bridge_request`, so it could pass while the production gate rejected
every download. The fixture response now occurs only after that real gate.

## Correction and boundaries

- The existing gesture permit now maps `download` to `download_observed`.
  Download authority binds the command, owned/current tab, page URL, observed
  element ID and exact element metadata, resolved resource URL and label.
- The controller requires the host decision ID to match a consumed download
  approval. It arms the native permit immediately before dispatch and clears it
  on both success and every normal error return. Failed arming clears prior
  authority before validation; it cannot leave an older permit usable.
- `bridge_request` takes the permit before validation/dispatch, including failed
  target or tab comparisons. Missing or mismatched authority never reaches the
  WebSocket. Raw `download_observed` requests without a platform context are
  refused as well. A failed transport never restores the permit.
- Existing HTTPS/exact-host scope checks, unique live DOM-link matching,
  same-origin/redirect rejection, size/MIME limits, byte verification and
  browser-wide download DENY are preserved. No arbitrary script, new debugging
  connection, browser relaunch or alternate orchestrator was introduced.
- Known failures now retain safe codes: `APPROVAL_UNAVAILABLE`,
  `download_requires_observed_link`, `download_target_changed`, invalid target/
  URL/receipt, response denial, origin denial, size/empty/fetch failure and
  bridge unavailable/poisoned/disconnected/timeout. Unexpected download failures
  use `download_failed`, without exposing exception payloads or private URLs.

## Approval presentation and ordinary clicks

The UI renders the exact operation and arguments, target, effect and destination
before showing the approval phrase. Invalid presentations cannot be approved;
changing the displayed summary or phrase invalidates the client-side matching
check in addition to the existing host presentation seal.

An ordinary `click` still returns an interaction authorization through the normal
AutoCua controller. It neither creates nor consumes a download decision. Explicit
downloads and external Scribe disclosure retain their independent approvals.
An ordinary click that triggers a site's download is still subject to browser
DENY; it does not manufacture a protected-download grant.

The referenced capture was not attached in this turn, so the historical triggering
tool cannot be established from it. In current code, the execution presentation
shows `operation.type` and arguments explicitly; an actual download approval
must identify `download`, rather than implying a navigation click.

## Regression evidence

- New native WebSocket test uses the real `bridge_request` gate and
  `Bridge::request` framing against a local synthetic peer, without Chrome.
  It proves refusal without a permit, one successful dispatch, consumption,
  refusal of reuse, changed requested URL/tab, changed cached tab, changed DOM
  target/page and rejection after a bridge error. The peer receives only the
  explicitly armed requests. Test-only socket setup bypasses Chrome startup;
  existing separate tests cover bridge authentication/profile ownership.
- The existing native agent-loop integration now exercises protected download
  through that gate, saves its actual synthetic bytes, uses the resulting receipt
  with `dext.scribe_pdf`, requires separate disclosure authority and validates a
  private accounting proposal with `posted_to_dext: false`. Only Chrome I/O and
  the Gemini/worker transport boundary are stubbed in this particular chain;
  other existing tests exercise the real bounded worker and provider envelope.
- A Python regression proves ordinary clicks do not create/consume a download
  approval. Existing real-client-policy, receipt, wrong-client/direction, provider
  failure, accounting and cross-platform tests remain active.
- UI tests cover exact operation/target/destination extraction, an unshown
  approval and refusal of malformed presentations.

Final results:

- Python full rebuilt-artifact suite: **280 discovered, 269 passed, 11 skipped**,
  zero failures/errors, 92.026 seconds. Skips require unavailable Windows symlink
  privileges. Includes eight production-Scribe tests and four packaging tests.
- Rust: `cargo check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml`
  passed; `cargo test --locked --offline --manifest-path AutoCua/web/Cargo.toml`
  **54 passed, 2 ignored** (internal pipe child helper and opt-in real Chrome).
- JavaScript bridge/selection/operator/composer suites: **50 passed**.
- UI typecheck/build passed; tracked bundle rebuilt. Wheel/sdist rebuilt and
  inspected. After the final rebuild, all **14 packaging/native-entry tests**
  passed again. `git diff --check` passed with the generated-bundle CRLF notice.
- Linux and real Chrome/Dext/Gemini were not executed. No real client or provider
  success is inferred from synthetic tests.

## Remaining real-Dext acceptance

This fixes the deterministic native authorization failure. Actual current Dext
PDF download mechanics cannot be established without a current observed control
or sanitized DOM/network evidence. None was supplied, and real profiles, keys and
client documents were kept untouched as requested. No unverified Dext-specific
button/blob/iframe adapter was invented. A non-link control now produces the
specific `download_requires_observed_link` error instead of apparent success or
a generic permission failure.

Real acceptance still requires observing that control, verifying a supported
resource or implementing an evidence-based fixed adapter if necessary, approving
the exact download and separate provider disclosure in the configured application,
and reviewing the resulting proposal. Production Scribe's client/reference
isolation, operator consent and prohibition on automatic accounting writes remain.

## Changed files

```text
AutoCua/web/browser/browser.rs
AutoCua/web/browser/bridge.rs
AutoCua/web/controller/view.rs
AutoCua/web/agent/main_driver/service.rs
AutoCua/ui/platform_session/operator_chat.ts
AutoCua/ui/platform_session/operator_review.tsx
AutoCua/ui/platform_session/operator_review.test.mjs
AutoCua/ui/index.js
tests/test_scribe_pdf.py
docs/pr5_download_permit_fix.md
```

Proposed commit: `fix(web): bind protected downloads to one-use native permits`.
