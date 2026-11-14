# Generic Web operator suspension and continuation

Date: 2026-11-13. Branch: `feat/dext-live-navigation-learning`.

The browser lifetime correction and current validation results are documented in
[Operator browser handoff](ask_operator_browser_handoff.md). The initial
validation record below is historical; its original cleanup behavior is superseded.
The ordinary-chat interface, contextual replies and Markdown learning integration
are described in [PR5 conversational assistance](pr5_conversational_operator.md).

## Architecture and state machine

`ask_operator(category, reason, request)` is a native tool in quality, fast,
Claude and scrape registries, using the existing provider converters/parser.
Categories are question, manual_action, authentication, confirmation and blocked.
Arguments are bounded and closed; no module/path/script/authority fields exist.
The pre-existing local Gemini schema normalization edit was preserved.

The existing controller preempts the entire batch when an intervention is present:
other calls receive correlated not-run results. The existing agent records all
call/result IDs and returns `waiting_operator` immediately without another model
turn. This is not success. Cleanup releases held input, ends the old observer and
detaches tab control. The host broker retains the same scanner, private CDP pipe
and profile lease so the dedicated window stays available for manual work.
Browser-level download denial remains active. Failed cleanup requires review.

The UI host saves the normal conversation checkpoint and retains a minimal
in-memory continuation bound to conversation, originating run, intervention ID,
revision, settings digest and a random review token. It never keeps an execution
thread waiting for a person. UI status polling reads host state only, with zero
model calls. A refresh within the same backend process restores the pending card.

The lifecycle is `running → waiting_operator → resuming → running`, or waiting/
resuming → cancelled. Failed launch/resource verification returns to waiting with
a fresh revision/token and explicit error. Replayed/foreign responses are denied.
An unavailable conversation checkpoint cannot resume.

Resume invokes the existing launcher with fixed saved settings and the same chat
ID, original task and saved history. It creates a fresh native execution instance
as a controlled checkpoint restart, not a second orchestrator or parallel agent.
Normal platform-context validation, exact retained-lease validation, shared native
execution ownership, fresh scope initialization and fresh observation precede the
next model call. Resume borrows the existing protected scanner and transport;
it cannot replace a missing browser with a fresh launch or another private pipe.
No pending action queue is replayed. Informational answers are explicitly labeled
as granting no permissions. Approval/effect systems remain independent.

This is same-process continuation only. Backend restart loses the in-memory
intervention; a saved waiting conversation is refused rather than silently resumed
without its trusted checkpoint. Recovery after process restart is not implemented.

## No progress and background work

An explicit intervention suspends on the first call. An error or independent
review result suspends without model retries. Three identical observed page/tree
states with reasoning-only turns or wait-only results trigger a specific blocked
intervention. Actual observed changes reset that detector. Model claims of progress
do not reset it. This supplements the explicit tool, not a fixed reasoning limit.

Web background memory compression is disabled because its independent provider
retries cannot currently be safely cancelled when an intervention arrives. This
ensures a waiting Web task starts no background model calls. Existing context
limits remain, so very long Web tasks can reach context limits sooner. Cancellable
compression is required before restoring that background feature. Other engines
are unchanged. Repeated malformed/unsupported model replies also suspend after
their existing bounded retry budget instead of silently exhausting the task.
Legacy free-text replies containing no tool call can still end with the existing
bounded `incomplete` outcome; that termination is not an operator continuation.

## Trusted UI and privacy

The existing chat displays the validated request as an assistant reply and a
subtle paused indicator. The ordinary composer routes contextual replies to the
trusted broker. It also handles exact procedure review separately from assistance;
advanced technical review remains optional.
Authentication requests use fixed private-intervention wording and accept no text.
Manual/confirmation/blocked events accept only completion, never textual secrets.
The composer instructs the operator to send only non-sensitive answers; the host
requires the UI's non-sensitive assertion, size limits and defensive secret-pattern
rejection. This is not a general DLP classifier: an
operator must not submit obfuscated secrets or private credentials. Approved
non-sensitive informational answers enter the ordinary task/history/model context.

`/api/operator` retains the app's token/Host protections; mutations additionally
require an exact local Origin and the precise session/run/intervention/revision/
review-token tuple. JSON is duplicate-key rejecting and bounded. GET is no-store.
Ordinary chat messages cannot consume a pending intervention. Requests are rendered
as React text, not HTML, scripts or authorization instructions. Suspended state,
tokens and answers are not written to a new journal or telemetry sink.

No private account, Dext data, external authentication or live model was used in
testing. This mechanism does not enable real Dext gestures, downloads, provider
disclosure or accounting writes. Keep the dedicated Chrome window open during
manual authentication. Closing it loses the private transport; automatic browser
replacement is forbidden and the task remains blocked for operator review.

## Initial implementation changed files (historical)

- `AutoCua/saccade/operator_requests.py`
- `AutoCua/ui/platform_session/operator_review.tsx`
- `AutoCua/ui/chat_input/chat_input.tsx`
- `AutoCua/ui/index.js`
- `AutoCua/ui/service.py`
- `AutoCua/web/agent/main_driver/service.rs`
- `AutoCua/web/controller/view.rs`
- `AutoCua/web/tool_registry/service.rs` (pre-existing Gemini edit retained)
- `tests/test_operator_requests.py`
- `tests/test_platform_sessions.py`
- `tests/test_packaging.py`
- `docs/ask_operator.md`

No desktop/mobile engine, browser transport, host allowlist, download policy,
dependency or lockfile changed. No Git staging/publication was performed.

## Initial verification and readiness (historical)

Final results: Python 178 total, 168 passed and 10 Windows symlink-privilege skips;
Rust 49 total, 47 passed and two intentional ignores (internal pipe child helper
and real Chrome); JavaScript 30 passed; TypeScript/build and Windows all-target
check passed. Fresh wheel/native-worker and sdist integration contracts passed.
The default parallel Rust command passed earlier but a later identical rerun
failed once in the existing `bridge::scoped_profile_tests::another_profiles_extension_cannot_authenticate_even_with_the_current_token`
fixture (`NotFound` opening its staged bridge). A final complete run with
`-- --test-threads=1` passed all 47 tests. Concurrency is a suspected factor, not
a diagnosed root cause; this intermittent failure remains a review risk. No
test was disabled or changed to conceal it.
Linux, real browser/UI handoff and live providers were not tested. The native fake-provider
test exercises explicit suspension (one request only), batch preemption, paired
history, three observed-stall reasoning/wait turns, and unchanged security gates.
Host tests cover same-chat resume through the real launcher route, prior history,
profile selection, Origin/authentication, replay, cancellation and failed-resume
revision rotation. These tests use fake browser/model boundaries and real workers;
they do not establish live browser or SDK/network compatibility.

Commands used with repository-cached Python 3.12/Rust 1.97.1/maturin 1.16:

```powershell
cargo test --locked --offline --manifest-path AutoCua/web/Cargo.toml
cargo test --locked --offline --manifest-path AutoCua/web/Cargo.toml -- --test-threads=1
cargo check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml
node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs AutoCua/ui/platform_session/selection.test.mjs AutoCua/ui/chat_input/correction.test.mjs
npm.cmd --prefix AutoCua/ui run typecheck
npm.cmd --prefix AutoCua/ui run build
maturin build --locked --offline --profile dev --out .cache/operator-wheels
maturin sdist --out .cache/operator-sdist
```

Local embedded-Python discovery used `.cache/operator-validation/run_python.py`
with cached Flask/Pillow prerequisites, fresh native DLL, wheel and sdist flags.
The normal equivalent is `python -m unittest discover -s tests -t . -v` with
`SACCADE_TEST_NATIVE`, `SACCADE_TEST_WHEEL`, `SACCADE_TEST_SDIST` set. Build logs and
machine-readable counts are under ignored `.cache/operator-validation/`.

An expanded native test initially exposed an outdated call-count assertion after
adding two additional stall scenarios. Moving the one-call assertion immediately
after explicit suspension resolved it; the final test separately verifies three
calls for each no-progress scenario and complete paired history. An early Python
run without native/wheel/sdist flags skipped those optional contracts; the final
flag-enabled run above executes them all. The final wheel was rebuilt after the
UI continuation hook changed and its isolated packaging contracts rerun.

Manual protocol, not executed:

1. In a non-sensitive Web test chat ask the agent to request a choice. Verify the
   paused card, completed tool pairing and unchanged model/token count while idle
   and after UI refresh. Answer through the dedicated field and Resume.
2. Verify the same original objective/history, fresh scan and ownership validation.
   Request manual action/authentication; complete it privately, enter no secrets,
   then Resume. A page claim or ordinary "yes" must not resume the task.
3. Force ownership/observer failure and verify a waiting error, no model retry,
   and a new continuation revision. Reconcile unknown effects manually before retry.
4. Cancel waiting and resuming tasks. Verify no stale events can restart them and
   original scope/approval restrictions remain. Close the backend and confirm that
   automatic restart recovery is refused, not falsely advertised.

Readiness: reviewable synthetic implementation, not certified for live manual
handoff, all provider SDKs or application restart. Long-context compression and
legacy termination limitations above need explicit acceptance/follow-up.

Suggested commit: `feat(web): add operator suspension and same-chat continuation`

Proposed existing-PR description update: add generic native `ask_operator`, exact
authenticated continuation events and operator UI; checkpoint/restart the same
task with fresh resource validation; stop observed no-progress loops; retain all
platform/business approval boundaries. State same-process-only recovery and the
Web background-compression tradeoff explicitly. No new PR or publication performed.
