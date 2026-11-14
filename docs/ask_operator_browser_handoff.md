# Operator browser handoff: implementation and review

Date: 2026-11-13. Branch: `feat/dext-live-navigation-learning`.

## Findings and correction

The previous `ScannerInner::end_platform_scope()` called
`Bridge::finish_scoped_download_session()`, which restored downloads and dropped
`scoped_download_transport`. The UI worker then released the profile lease and
discarded the native scanner. Resume constructed an independent browser service
through the normal scoped Chrome launch path. It could not retain the previous
page through that path. The reported missing authorized page follows from that
lifecycle, rather than from a defective authentication page.

The operator observed Chrome exiting when the private transport was dropped.
The existing ignored real-Chrome pipe test also expects Chrome to exit on pipe
closure. That test was not run for this change. The relationship is supported by
the code and the operator's observation; this implementation session did not
independently reproduce Chrome's process behavior.

The correction keeps the existing native Rust agent, host launcher, conversation
service and operator broker. There is no second agent loop or conversation store.
An internal execution wrapper can change on continuation; the objective, chat,
transcript, browser scanner, private pipe and profile ownership remain continuous.

## Ownership lifecycle

1. The native agent pairs the intervention tool result with its call, releases
   inputs, ends its observer and detaches extension tab control. A handoff flag
   keeps the browser-level private CDP transport alive and requires a fresh DENY
   acknowledgment instead of restoring downloads. The current page is preserved.
2. The host atomically saves the normal conversation checkpoint and transfers the
   native agent reference plus its exact profile lease into a private broker
   resource table. These objects never enter checkpoint JSON or API responses.
   No agent execution thread, model polling or background compression remains
   active while waiting. The existing UI polls host status only.
3. An authenticated, exact-Origin Resume consumes the existing one-use event.
   The ordinary launcher restores the same conversation and saved settings. It
   retrieves the retained resource from the host broker, never from request JSON.
   An absent resource is an error, with no fallback Chrome launch.
4. A fresh native wrapper verifies the installed context, exact lease identity,
   profile and headless setting, inactive shared execution owner, handoff state
   and absence of sticky security violations. UI-managed continuations require a
   host-owned lease. It borrows the same scanner inner state and bridge; it does
   not create another Chrome or browser-level debugging connection. A shared
   native run guard covers construction, execution and terminal cleanup across
   both old and new wrappers.
5. Native initialization installs a new observer identity, validates committed and
   pending URLs for all tabs, requires exactly one authorized page, verifies
   browser-level download DENY, reestablishes tab observation and takes a fresh
   scope observation before any model request. Existing narrow bootstrap blank
   and bridge-wake rules remain. No queued external effect is replayed.
6. Reattachment errors keep the task waiting, rotate its continuation identity,
   and preserve the available resource. Sticky violations are not cleared. No
   alternative browser is launched. Existing business approvals, trusted-client
   bindings and independent policy gates still apply.
7. Terminal completion or Cancel closes the retained transport only after verified
   observer/tab release and policy restoration, then releases the profile lease.
   Cancel during execution sets the existing stop event; the completed worker
   performs cleanup. Checkpoint publication and cleanup are serialized with
   Resume/Cancel. Process shutdown attempts to clean all suspended resources.

Unverified cleanup retains ownership and disables Resume. A new event may retry
Cancel after review. Some sticky failures, a dead Chrome, or a broken private
pipe cannot be repaired automatically: cleanup may remain blocked until reviewed
backend shutdown. The code does not bypass a live profile lock or guess that an
unknown browser has released ownership.

## UI and security review

- `waiting_operator` uses a normal pause lifecycle and preserves pending
  milestones. Live replies and reopened conversation outcomes say "Paused".
- Resume forwards the server's explicit platform binding through the existing
  chat lifecycle. Missing, malformed or foreign-session payloads cannot silently
  restore Generic AutoCua. Explicit `null` still represents a generic Web chat.
- Browser-level download denial stays enabled during manual work. Download
  attempts observed through the retained pipe can still block continuation.
- The operator can authenticate privately in the dedicated window after tab
  control is released. Passwords, MFA codes and secrets are never requested or
  accepted through the operator chat answer field.
- Host authentication, exact Origin, session/run/intervention/revision/token
  checks, anti-replay behavior, transcript pairing and checkpoint checks remain.
- The reserved profile blocks competing ordinary runs during the pause. The
  shared native run guard also prevents concurrent execution or cleanup through
  an older wrapper referring to the same browser.
- No host allowlist, download gate, profile-lock implementation, OS engine,
  business tool authority or shipped `dext.md` procedure was weakened or changed.
- Development used synthetic data. No private accounting references, Dext
  credentials, live client records or live provider requests were used.

## Exact changed files

- `.github/workflows/ci.yml`: run the operator UI regression tests in CI.
- `AutoCua/agent_conversation/service.py`: persist a normal paused outcome.
- `AutoCua/saccade/operator_requests.py`: private passive browser ownership,
  guarded access, ordered cleanup and fail-closed cleanup errors.
- `AutoCua/ui/service.py`: transfer/retain the native browser and lease, resume
  through the existing launcher, serialize checkpoint publication and cleanup,
  handle cancellation and show normal pauses.
- `AutoCua/ui/platform_session/operator_review.tsx`: forward validated resume
  state through the current chat lifecycle.
- `AutoCua/ui/platform_session/operator_resume.ts`: validate the resume payload
  and retain its explicit platform context.
- `AutoCua/ui/platform_session/operator_review.test.mjs`: platform restoration,
  malformed/foreign payload refusal and actual reply-renderer pause semantics.
- `AutoCua/ui/script.js`: pause without marking pending milestones interrupted.
- `AutoCua/ui/container/agent/run_reply.js`: render waiting as a normal reply.
- `AutoCua/ui/index.js`: rebuilt shipping UI bundle.
- `AutoCua/web/agent/main_driver/service.rs`: borrow the retained scanner, share
  execution ownership, validate reattachment and expose guarded terminal cleanup.
- `AutoCua/web/browser/browser.rs`: distinguish manual handoff from terminal
  cleanup, preserve the pipe and keep unverified release fail-closed.
- `AutoCua/web/browser/bridge.rs`: explicit transport cleanup and synthetic native
  lifecycle/reattachment/failed-release tests.
- `AutoCua/web/browser/chrome_pipe.rs`: test-only CDP policy peer using real Windows
  pipes; production process flags, inheritance and framing are unchanged.
- `tests/test_operator_requests.py`: resource privacy, ownership, cleanup ordering
  and cleanup-failure contracts.
- `tests/test_platform_sessions.py`: full host pause/resume, same-chat/context,
  retained lease, failed reattachment, no fresh-browser fallback and cancellation.
- `tests/test_packaging.py`: verify current operator UI sources and shipping bundle
  are included unchanged in the built wheel.
- `docs/ask_operator.md`: correct the previous lifecycle description and identify
  its initial test record as historical.
- `docs/ask_operator_browser_handoff.md`: this report and live validation protocol.

## Validation

Current Windows validation uses repository-cached Python 3.12.10, Rust 1.97.1,
maturin 1.16.0 and Node 26.13.0. Exact final counts and commands are recorded below.
The native policy peer and authenticated WebSocket peer are synthetic; no Chrome
is launched by those regression tests.

| Check | Result |
| --- | --- |
| Python full discovery with fresh native DLL, wheel and sdist | 185 tests: 175 passed, 10 skipped, 0 failures/errors |
| Windows Rust unit tests, default parallel execution | 52 tests: 50 passed, 2 ignored, 0 failures |
| Windows Rust all-target compilation check | Passed |
| JavaScript observer/selector/operator/composer tests | 32 passed |
| UI TypeScript check | Passed |
| UI production build | Passed; shipping bundle rebuilt |
| Fresh development wheel and sdist construction/inspection | Passed; isolated installed-wheel/native-worker contracts executed |
| Git whitespace check | Passed |

The ten Python skips require Windows symlink privileges unavailable to this
account. The two Rust ignores are the internal inherited-pipe child helper
(invoked by its parent test) and the opt-in real-Chrome test. Linux execution,
live Chrome handoff, live Dext authentication, provider SDK/network behavior and
interactive UI behavior were not tested. Synthetic success is not evidence of
successful real Dext authentication.

```powershell
cargo test --locked --offline --manifest-path AutoCua/web/Cargo.toml
cargo check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml
node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs AutoCua/ui/platform_session/selection.test.mjs AutoCua/ui/platform_session/operator_review.test.mjs AutoCua/ui/chat_input/correction.test.mjs
npm.cmd --prefix AutoCua/ui run typecheck
npm.cmd --prefix AutoCua/ui run build
maturin build --locked --offline --profile dev --out .cache/operator-wheels
maturin sdist --out .cache/operator-sdist
```

Python discovery used `.cache/operator-validation/run_python.py`, with cached
Flask/Pillow dependencies and `SACCADE_TEST_NATIVE`, `SACCADE_TEST_WHEEL`,
`SACCADE_TEST_SDIST`. Its normal equivalent is
`python -m unittest discover -s tests -t . -v` with those paths set. Logs and
machine-readable counts are in ignored `.cache/operator-validation/handoff-*`
and `python-results.json`. Maturin's sdist command emits the existing nonfatal
root-Cargo-manifest probe warning before building the configured source archive.

## Remaining limitations and decisive live validation

This is same-backend-process continuation. Restart loses the in-memory browser
resource and review tokens; saved waiting conversations cannot silently relaunch.
Do not close the dedicated Chrome window during an intended handoff. Native
download denial remains active, which can block authentication flows requiring
downloads. SSO finishing outside the installed exact-host scope, multiple
authorized pages, lost observation or a broken pipe keeps the task blocked.
Existing long-context/background-compression limitations are unchanged.

The decisive live check is an operator-controlled Windows run using an isolated,
non-sensitive profile, followed by explicitly authorized Dext testing:

1. Record the dedicated browser process/profile and current authorized page.
   Trigger `ask_operator(authentication_required)` and confirm the same window
   remains usable. Confirm its observer/debugger control was released and its
   browser-level DENY policy was acknowledged without opening another pipe.
2. Wait at least 60 seconds and refresh/reopen the same chat. Model request count
   and token usage must stay fixed. The operator card must show a normal pause,
   and Dext must remain the bound platform.
3. Authenticate privately in that same dedicated window; put no credentials or
   codes in chat or test logs. Leave exactly one authorized page. Click Resume
   once. Verify the same browser/profile/page, same chat and original objective,
   preserved call/result history, a new observer and fresh scope observation
   before the first resumed model call. Confirm no competing Chrome/private
   connection appeared. Replaying the old Resume must fail.
4. In a separate disposable synthetic run, close the dedicated browser during
   the pause or leave two authorized pages. Resume must remain blocked without
   a fresh browser or model retry. Sticky failures require review, not bypass.
5. Cancel while waiting and during revalidation. Verify cleanup occurs only after
   execution stops and the profile lease is released only after verified native
   cleanup. A deliberately unverified cleanup must retain ownership and disable
   Resume. Do not simulate success or weaken security to make this step pass.

These live steps have not been executed in this implementation session.

## Proposed commit and PR description

Commit: `fix(web): preserve protected browser across operator pause and resume`

Proposed PR update:

Keep the dedicated protected Chrome and its profile lease usable during
`ask_operator` manual/authentication pauses. Resume the same conversation through
the existing launcher by borrowing the retained scanner and private CDP transport,
with shared native ownership, fresh observer/page/policy checks and no replacement
Chrome fallback. Render operator waiting as a normal pause and restore the saved
platform binding. Cover handoff, reattachment failures, anti-replay, cancellation,
cleanup and packaged UI assets with synthetic regressions. State explicitly that
live Chrome/Dext validation and process-restart recovery remain unverified.

No commit, push, PR creation, merge, branch switch or user-data deletion was done.
