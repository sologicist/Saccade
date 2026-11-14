# PR5: supervised navigation and authentication continuation

Date: 2026-11-13. Branch: `feat/dext-live-navigation-learning`.
Starting commit: `4bbee3086cfb9c4b8b075c80292a8ff92a8b78cd`; worktree initially clean.
No staging, commit, push, branch change, PR creation, merge or private-data
migration/deletion was performed. No real Chrome, Dext or external provider ran.

## Verified root cause and incident uncertainty

The source at the starting commit has a deterministic failure chain matching
the reported sequence:

1. `operator_language.reply_intent()` does not recognize `c'est connecté`.
   The authentication branch in `OperatorRequests.chat()` therefore asks for
   another confirmation. This is a classifier defect, not failed login proof.
2. `PlatformScope.validate_action()` refuses generic clicks and Dext model URL
   navigation with `APPROVAL_UNAVAILABLE`. These actions never dispatch.
3. `ScannerInner.authorize_platform_action()` nevertheless passes that refusal
   to `platform_failure()`, which calls `PlatformScope.fail()` and permanently
   latches it as a browser scope violation.
4. The run pauses and retains its private transport, but the next native
   constructor refuses `operator_session` because its scanner has a latched
   violation. A forbidden, undispatched action has incorrectly made a perfectly
   retained browser impossible to resume.
5. The broad resumed-run exception handler in `ui/service.py` labels every
   constructor or execution failure as browser reattachment failure. The broker
   then permits blocked-state informational clarification, causing the loop.

Current evidence locations: `browser/browser.rs::authorize_platform_action`,
`platform_scope.rs::validate_action`,
`agent/main_driver/service.rs::reclaim_scanner`,
`ui/service.py::_start_agent_run_locked` and
`operator_requests.py::chat/block_recovery`. The compiled regression now proves
that a denied click has no dispatched effect, leaves a healthy scope intact
and permits reclaiming the same scanner. Genuine host/observer violations remain
sticky and prevent continuation.

The previous run provided no underlying exception or lifecycle correlation log.
Consequently this verifies a sufficient source-level cause and reproduces its
repair; it does not establish that no additional physical Chrome/pipe problem
occurred in that exact manual incident. New process/pipe/lease/checkpoint codes
make that distinction observable during the next operator-controlled test.

The first authentication pause itself is expected on a dedicated profile opened
at the installed login URL. Generic Web may already have the operator's logged-in
personal Chrome session. Its success neither authorizes copying that session
nor demonstrates equivalent authentication or business permission.

## Ownership, scope and continuation changes

- A pre-dispatch approval refusal returns `unsupported_navigation` and
  `executed: false` without poisoning the browser. An uncertain post-action
  failure does not assert `executed: false`. The native loop requests a focused
  manual action rather than claiming an effect needs reconciliation when none
  was executed. It does not automatically retry the forbidden action.
- `reclaim_scanner()` is the constructor's single native ownership boundary:
  exact lease object, live registered lease, same platform/profile/context,
  inactive execution owner, valid native handoff and no sticky scope violation.
  It returns the existing scanner Arc. It creates neither Chrome nor a private
  connection. The shared execution mutex prevents competing resumes.
- UI and native resumed execution validate the existing OS lease; they no longer
  use `ensure_held()` to silently reacquire a lost lease. The native constructor
  rejects absent/unpaired retained-session history before model startup.
  Fresh controllers and stop events replace closed execution controls, while
  the task, paired history, scanner, profile lease and learning pin persist.
- Resume remembers the controlled tab. Multiple authorized tabs do not require
  guessing when that original tab still exists. If the remembered tab is missing,
  another tab cannot silently replace it. Without a remembered target, the
  existing exactly-one-authorized-page rule remains in force. All tabs and
  pending URLs still pass exact-host policy before selection.
- The bridge retains a synchronization-only handle to the exact launched Chrome
  process, avoiding PID reuse ambiguity. Process exit and an unavailable CDP
  transport have different diagnostic codes. Download denial must still receive
  a fresh browser-level acknowledgment before scoped work.
- Explicit cancellation can clean up an exited owned process without pretending
  a dead websocket acknowledged cleanup. Only a signaled exact process handle
  proves death; missing/unknown handles do not. If ownership of a live process
  cannot be reconciled, the lease remains reserved for operator review.
- Native observation generations are refreshed on handoff. A separate native
  retained-session identity lets manual learning corroborate before/after
  observations in that same browser across those generations. A replacement
  session, wrong tab/profile/platform/configuration cannot supply that evidence.
  Legacy stamps without the session field retain strict observer identity.

## Authentication, intentional waiting and permitted navigation

`intervention_intent()` recognizes the requested French/English variants in the
context of a pending authentication request, including `c'est connecté`,
`je suis bien connecté`, `la connexion est faite` and `I've signed in`.
Existing yes/ok/done handling is preserved. The continuation explicitly records
an operator claim, not verified login, and requires fresh observation of the
same browser. No model request is needed to interpret a simple confirmation.
The claim grants no navigation, download or business authority.

The existing native agent sees the fresh supported page observation and must
ask a focused follow-up if the required authentication state is not observable.
No generic host-side authentication/record-identity verifier is invented.

`ask_operator` gains the bounded reason `awaiting_instructions`. The native prompt
uses it when the task requests reaching a page and waiting. The ordinary chat
then accepts the next non-sensitive instruction in the same conversation, with
the retained browser and no model polling during the pause. The UI labels this
as intentional waiting, independently of login, failure and learning approval.

Supervised mode continues using the existing native scanner, action registry,
controller and tab handlers. It does not introduce another navigator. Verified
tab selection remains available. Returning the current Dext tab to its exact
trusted installed bootstrap URL now uses the ordinary `update_tab` handler and
the same policy as initial bootstrap. This grants no new tab or arbitrary URL.

**Automatic Purchases/review-queue/invoice clicks remain blocked.** Current
element mappings expose index/tag/role/name/line, not an independently verified
navigation-only target/effect, stable frame semantics or business record identity.
A label alone cannot prove that a button/link has no business effect. Arbitrary
same-host URLs may also invoke effects. The agent therefore asks for manual
navigation and reobserves. Dext preview, downloads, bank/scribe disclosure and
accounting write gates remain independent and unchanged. Internal business
functions must come from the trusted registry, never unrelated websites/tabs.

This repairs the reproducible pause/resume regression. It does **not** claim the
full real-world autonomous invoice-navigation success criterion is established.
That requires a verified navigation-effect/frame adapter and real validation.

## Bounded source-checkout diagnostics and hard recovery

`operator_diagnostics.py` records at most 128 process-local events, containing
only a closed event code, phase and hashed session/run correlation identifiers.
Standard Python logging works in a source checkout; compilation is not required.
The authenticated local `GET /api/operator/diagnostics?session_id=<current-chat>`
returns those bounded events with `Cache-Control: no-store`.

Codes distinguish conversation/configuration mismatch, process unavailable,
pipe disconnected, lost/foreign lease/ownership, invalid native checkpoint,
unpaired history, scope/observer failure, control lifecycle mismatch, unsupported
navigation, unverified effect and unexpected internal exception. Unknown
exceptions are never echoed into this diagnostic stream. No credentials,
cookies, access tokens, raw DOM, private URLs, records, storage or provider keys
are logged. Native lifecycle cleanup/execution errors also avoid printing raw
scoped exception payloads in the changed paths.

`resume_attached` means constructor ownership checks passed; `resume_observed`
is emitted only after the native fresh-scan flag is true. HTTP `started` remains
the existing asynchronous worker acknowledgment, not proof of successful resume.
Constructor failures and later execution failures use different phases instead
of both being labeled Chrome reattachment failure.

A hard ownership/checkpoint failure marks the pending request `cancel_restart`
and makes its checkpoint unavailable. Replies cannot become generic clarification
or start another run. Cancel remains allowed; after verified cleanup, a new
conversation is a separate operator operation. No implicit replacement Chrome
or automatic retry loop is added. If a live window cannot be cleaned up safely,
the operator must review/close it and retry cancellation; an unknown live process
does not lose its protection or lease merely to make recovery convenient.

## Exact changed-file list

```text
AutoCua/saccade/operator_diagnostics.py                 (new)
AutoCua/saccade/operator_language.py
AutoCua/saccade/operator_requests.py
AutoCua/saccade/platform_learning.py
AutoCua/ui/index.js                                    (rebuilt)
AutoCua/ui/platform_session/operator_chat.ts
AutoCua/ui/platform_session/operator_review.test.mjs
AutoCua/ui/platform_session/operator_review.tsx
AutoCua/ui/service.py
AutoCua/web/agent/main_driver/service.rs
AutoCua/web/browser/bridge.rs
AutoCua/web/browser/browser.rs
AutoCua/web/controller/view.rs
AutoCua/web/platform_scope.rs
AutoCua/web/tool_registry/service.rs
docs/pr5_platform_learning.md
docs/pr5_supervised_resume_review.md                    (new)
tests/test_operator_resume.py                          (new)
tests/test_packaging.py
tests/test_platform_sessions.py
```

`chrome_pipe.rs`, CreateProcess startup flags/handle inheritance, Dext business
implementations, platform manifests, tracked baseline skills and immutable
learning storage formats are unchanged. No Windows/Linux/macOS/Android/iOS engine
file changed. No dependency or separate orchestrator was added.

## Safe manual validation protocol — not executed

1. Fully stop the old Saccade process; an already loaded native module cannot
   acquire these fixes by editing Python alone. Start from the freshly built
   wheel in a disposable environment, or let the source checkout's existing
   native build loader refresh its extension. Confirm the loaded module path
   and the new `operator_resume_observed`/`operator_diagnostic_code` properties.
2. Use a disposable Dext account and non-sensitive records in a new Dext /
   Supervised Web conversation. Request a harmless section and then a wait.
   Do not request downloads, scribe, exports, accounting writes or disclosure.
3. Let the native agent request authentication. Verify the dedicated window
   stays usable and model-call/token counters remain unchanged while paused.
4. Sign in privately in that window. Reply `c'est connecté` through normal chat.
   Verify no redundant confirmation, no second Chrome/private connection, the
   same profile/lease, the original task and paired history. Check the bounded
   lifecycle codes for attachment followed by fresh observation.
5. Permit only verified navigation. If a section click lacks effect/frame proof,
   expect a focused manual request. Perform that navigation manually and confirm.
   Do not call a blocked click automatic success or approve business effects.
6. At the requested visible page, verify the intentional instructions pause.
   Give a spontaneous public-section correction and verify same-chat/browser
   continuity and exact independent approval before any learning publication.
7. Repeat with the distinct disposable registered platform. Confirm its own
   profile, baseline, pin and `learning.md`, without Dext business capabilities.
8. Test a hard ownership loss only in the disposable session. Expect a specific
   bounded code, no implicit replacement, no clarification loop and Cancel/new
   conversation recovery. Verify live unknown ownership keeps the lease until
   cleanup is proven. Record real results separately from the synthetic suite.

Real Chrome authentication, real Dext semantic navigation and production release
behavior remain unverified. The bounded diagnostic ring and pending browser
broker are process-local; process restart does not reconstruct a lost passive
browser. Existing immutable procedure/pin/recovery durability remains intact.

## Actual validation results

Cached Python 3.12.10, Rust 1.97.1 GNU/MinGW, Node 26.13.0 and maturin 1.16.0
were used. Rust commands used the cached offline `CARGO_HOME` and
`SACCADE_TEST_PYTHON` pointing to `.cache/pr1-tools/python/python.exe`.

| Command/check | Actual result |
| --- | --- |
| `.cache/pr1-tools/python/python.exe .cache/operator-validation/run_python.py` | **252 discovered; 241 passed, 11 skipped**, no failures/errors; 84.539 seconds |
| `cargo check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml` | Passed |
| `cargo test --locked --offline --manifest-path AutoCua/web/Cargo.toml` | **52 passed, 2 ignored**, no failures; 8.08 seconds |
| `node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs AutoCua/ui/platform_session/selection.test.mjs AutoCua/ui/platform_session/operator_review.test.mjs AutoCua/ui/chat_input/correction.test.mjs` | **45 passed**, no failures/skips |
| `npm.cmd --prefix AutoCua/ui run typecheck` | Passed |
| `npm.cmd --prefix AutoCua/ui run build` | Passed; tracked bundle rebuilt |
| `.cache/pr2-review/maturin/maturin-1.16.0.data/scripts/maturin.exe build --locked --offline --profile dev --out .cache/operator-wheels` | Built Windows abi3 wheel |
| `.cache/pr2-review/maturin/maturin-1.16.0.data/scripts/maturin.exe sdist --out .cache/operator-sdist` | Built source archive; exit 0 |
| Wheel/sdist inspection and isolated installation tests | All **4** passed within the full Python suite |
| Compiled PyO3 constructor entry tests | All **10** passed within the full Python suite |
| Final rebuilt-artifact check: `python -m unittest tests.test_platform_session_native tests.test_packaging` with the native/wheel/sdist environment above | **14 passed**, no skips/failures; 9.944 seconds |
| `git diff --check` | Passed; informational LF/CRLF warning for the generated UI bundle only |
| Linux Rust check/tests | **Not run locally**; see environment limitation below |
| Real Chrome/Dext tests | **Not run**, reserved for the operator-controlled protocol |

The full Python runner performs `unittest` discovery with the repository and
`.cache/pr4-test-deps/site-packages` on `sys.path`. It sets:

```text
SACCADE_TEST_NATIVE=AutoCua/web/target/debug/agent_native.dll
SACCADE_TEST_WHEEL=.cache/operator-wheels/saccade-0.1.9-cp310-abi3-win_amd64.whl
SACCADE_TEST_SDIST=.cache/operator-sdist/saccade-0.1.9.tar.gz
```

All new resume tests and existing Dext/shared learning tests ran. The 11 Python
skips are existing Windows symlink privilege requirements; junction regressions
did run. The two ignored Rust entries are the internal inherited-pipe child
helper (exercised by its parent test) and the opt-in real Chrome test.

The native test uses the actual compiled `AgentService` constructor, validates
an unpaired checkpoint rejection, constructs a new execution around the same
scanner/ownership mutex and real synthetic-profile OS lease, then reobserves and
pauses for instructions. Provider and compression boundaries are synthetic.
The bridge regression uses authenticated synthetic websocket/CDP peers on both
Dext and the second platform, preserves the protected transport, rejects an
undispatched click without poisoning scope and executes the existing native tab
handler for trusted bootstrap. An exited synthetic `cmd.exe` child tests exact
process-object death detection and cancellation; it is not Chrome evidence.
The Python-entering bridge test shares the native fixture lock to avoid overlap
with process-wide module patches in the full native-loop test.

The new HTTP regressions exercise both platforms' authentication claim, retained
window/lease/profile, fresh stop event, paired transcript, same objective,
instructions pause, hard-failure recovery and distinction between constructor
and runtime errors. Provider counters stay unchanged during paused status reads.
Diagnostic tests verify bounded size, fixed fields and absence of private input.
The last Rust-only privacy/diagnostic-state changes were followed by the complete
Rust check/test suite, another wheel/sdist rebuild and the 14 compiled-entry and
packaging checks. Scoped reasoning, completion and action-error payloads are no
longer printed by the changed native logging paths; they remain in the existing
local conversation where required. A rejected competing run cannot reset the
accepted run's fresh-observation diagnostic state.

Linux availability was checked with `wsl.exe --list --quiet`, then
`wsl.exe -d docker-desktop --exec sh -lc 'command -v cargo && cargo --version'`.
Only Docker Desktop is installed; Cargo is absent there (exit 1, no executable
reported). The cached Rust toolchain is Windows-only. No Linux distribution,
toolchain or system configuration was installed/changed. Existing Windows/Linux
CI configuration is unchanged; this uncommitted work was not pushed or run in
remote CI, so Linux results must not be reported as passing.

The source-archive build emits the existing nonfatal root `Cargo.toml` probe,
Python-platform and Cargo package-metadata warnings, then builds successfully;
archive inspection passed. Build logs/artifacts remain local and Git-excluded
under `.cache/operator-validation`, `.cache/operator-wheels` and
`.cache/operator-sdist`. No private MPH/FRT accounting references, invoices or
provider credentials were used or packaged.

Proposed commit message, not executed:

`fix: preserve supervised browser continuation after operator intervention`
