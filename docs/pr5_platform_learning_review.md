# PR5 shared platform learning: implementation and security review

Date: 2026-11-13. Branch: `feat/dext-live-navigation-learning`.
Starting worktree: clean. No branch change, staging, commit, push, PR creation,
merge, reset or user-data migration/deletion was performed.

## Implementation

The existing native Web loop, continuation/conversation service, operator
broker, browser ownership and profile leases remain authoritative. Shared
learning now consists of a session-bound `PlatformLearningControl`, a trusted
declarative `LearningAdapter`, the existing bounded correction/evidence engine
and the parameterized immutable `ProcedureStore`. Dext is a subclass consumer;
its business registry and preview authorization are not generalized.

Every installed Web platform receives the same host/chat/native integration.
Its optional public landmark configuration enables manual transition learning;
missing or unsupported vocabulary produces clarification. A second synthetic
platform requires only platform/domain metadata and its vocabulary, with no
copied orchestration code. See [the integration contract](pr5_platform_learning.md)
for configuration, schema, persistence, migration, boundaries and the manual
Dext/second-platform validation protocol.

New proposals use platform-neutral schema-2 landmark/verification steps, scoped
to the platform and adapter revision. Legacy Dext schema-1 hashes, snapshots,
Markdown and pins remain valid and immutable. Existing identity/review cautions
are preserved by immutable revision reference where they cannot truthfully be
converted to heading-transition evidence. No real learning data was migrated.

The native prompt uses the correct exact-host baseline plus only that platform's
checked pinned overlay. The same native checkpoint runs before model dispatch
for both platforms. The UI composer, spontaneous corrections, safe handoff,
exact approval and same-chat continuation share the existing code paths.

## Exact changed files

Existing files modified:

```text
AutoCua/saccade/dext_control.py
AutoCua/saccade/navigation_correction.py
AutoCua/saccade/operator_language.py
AutoCua/saccade/operator_requests.py
AutoCua/saccade/procedure_store.py
AutoCua/ui/chat_input/chat_input.js
AutoCua/ui/chat_input/correction.test.mjs
AutoCua/ui/platform_session/operator_review.test.mjs
AutoCua/ui/service.py
AutoCua/web/agent/main_driver/service.rs
AutoCua/web/browser/browser.rs
AutoCua/web/controller/view.rs
pyproject.toml
tests/test_packaging.py
tests/test_platform_session_native.py
tests/test_platform_sessions.py
```

New files:

```text
AutoCua/saccade/dext_learning.py
AutoCua/saccade/learning_adapter.py
AutoCua/saccade/platform_learning.py
docs/pr5_platform_learning.md
docs/pr5_platform_learning_review.md
tests/platform_learning_fixtures.py
tests/test_platform_learning.py
```

The UI bundle was rebuilt and is unchanged after Git line-ending normalization.
No tracked baseline skill, platform manifest, accounting reference, Chrome pipe,
bridge transport or Windows/Linux/macOS/Android/iOS engine file changed.
Build/test logs and artifacts remain excluded under `.cache/`.

## Commands and actual results

Commands ran locally with cached tools/dependencies, without external providers.
Python: `.cache/pr1-tools/python/python.exe` (3.12.10), with the repository and
`.cache/pr4-test-deps/site-packages` on its import path. Rust/Cargo: cached 1.97.1
GNU toolchain and MinGW; `CARGO_HOME=.cache/pr1-tools/cargo-home`.
`SACCADE_TEST_PYTHON` points to that Python interpreter.

| Command/check | Actual final result |
| --- | --- |
| `.cache/pr1-tools/python/python.exe .cache/operator-validation/run_python.py` | 243 discovered; **232 passed, 11 skipped**, zero failures/errors; 77.914 seconds |
| `cargo check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml` | Passed |
| `cargo test --locked --offline --manifest-path AutoCua/web/Cargo.toml` | **50 passed, 2 ignored**, zero failures |
| `node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs AutoCua/ui/platform_session/selection.test.mjs AutoCua/ui/platform_session/operator_review.test.mjs AutoCua/ui/chat_input/correction.test.mjs` | **43 passed**, zero failures/skips |
| `npm.cmd --prefix AutoCua/ui run typecheck` | Passed |
| `npm.cmd --prefix AutoCua/ui run build` | Passed, Vite 8.3.5 |
| `.cache/pr2-review/maturin/maturin-1.16.0.data/scripts/maturin.exe build --locked --offline --profile dev --out .cache/operator-wheels` | Built Windows abi3 wheel |
| `.cache/pr2-review/maturin/maturin-1.16.0.data/scripts/maturin.exe sdist --out .cache/operator-sdist` | Built source archive; exit 0 |
| Wheel/sdist inspection and isolated installation tests | All four packaging tests passed within the Python suite |
| Actual compiled PyO3 constructor tests | All ten passed within the Python suite; no Chrome/model-provider request |
| `git diff --check` | Passed; informational UI bundle LF/CRLF warning only |

The validation runner sets `SACCADE_TEST_NATIVE` to the freshly built
`AutoCua/web/target/debug/agent_native.dll`, `SACCADE_TEST_WHEEL` to
`.cache/operator-wheels/saccade-0.1.9-cp310-abi3-win_amd64.whl` and
`SACCADE_TEST_SDIST` to `.cache/operator-sdist/saccade-0.1.9.tar.gz`, and uses
`unittest.defaultTestLoader.discover('tests', top_level_dir=repository)`.

The 11 Python skips are existing symlink privilege requirements: one account
capability skip and ten Windows symlink privilege skips. The new synthetic
platform directory junction test actually ran on Windows and passed.
The two Rust ignored entries are the inherited-pipe child helper (exercised by
its parent test) and the explicitly opt-in real Chrome test. Chrome, Dext and
external model/accounting services were not launched.

The sdist command emits an existing nonfatal root `Cargo.toml` discovery probe,
Python-platform warning and missing Cargo package metadata warning before
successfully building with the configured Web manifest. These are not test
failures; the resulting archive passed inspection.

## Evidence and security review

- Fifteen new shared-learning tests cover both platform lifecycles, exact chat
  approval/replay rejection, independent Markdown/pins/rollback/locks, rejection,
  projection-crash recovery, unknown IDs, traversal, wrong profiles/stamps,
  cross-platform snapshots/proposals with matching baselines, metadata changes,
  ambiguous/unsafe adapter metadata, private qualifiers and legacy Dext data.
- The actual HTTP launcher test demonstrates the second platform's active
  correction, safe pause, retained browser ownership, manual evidence, exact
  chat approval, unchanged objective/chat binding and future guidance. Its fake
  provider counter stays zero throughout the pause/manual-learning steps.
  Existing Dext handoff, failed reattachment, cleanup and anti-replay tests pass.
- The real Rust `process_request` test verifies Dext guidance and the distinct
  second-platform baseline/approved overlay in actual native prompt composition.
  It checks absence of Dext guidance/business navigation exposure on the second
  platform, and no provider call at either platform's manual-learning checkpoint.
  Scanner/provider boundaries are synthetic; the production loop is unchanged.
- The compiled constructor rejects forged/foreign learning controls before model
  initialization or Chrome startup, and accepts the second platform's correct
  shared control up to the deliberate synthetic startup failure boundary.
- Native scope, observer, tab, dedicated profile and configuration are checked
  before evidence is accepted. Changing observer/tab invalidates source evidence.
  Exact proposal presentation includes full platform context, adapter, pin,
  session/run and request identity. Binding/pin checks run before persistence
  and resume. Existing single-use tokens and full-pointer CAS remain in place.
- Only declared public labels and closed verification steps enter new learned
  Markdown. No raw page text, private client/record values, URLs, scripts,
  selectors, secrets, gestures or expanded permissions are learned. Review is
  publication authority only; the current conversation keeps its old pin.
- Baseline Markdown is unchanged. Existing strict path checks, per-directory OS
  lock, immutable hashes, projection journal and atomic publication remain.
  Existing exclusions protect all `platforms/*/data/` directories in Git and
  packages. Packaging tests confirm local data/reference material is absent.
- No private MPH/FRT references or real accounting/client files were copied,
  read for development, disclosed or uploaded. All new fixture data is synthetic.

## Remaining limitations and risks

This completes the shared learning integration; it does not establish real Dext
automation readiness. No real Chrome/Dext/manual authentication test was run.
Synthetic tests establish contracts, not browser reliability or semantic proof.

The generic verifier corroborates manually demonstrated public section
transitions only. Visible labels do not prove frame, workspace, client or record
identity. Unsupported vocabulary requires clarification. Automatic gestures,
live PDF/download receipts, bank/scribe disclosure and accounting writes retain
their existing independent restrictions. No simulated result substitutes for a
real Dext validation.

Installed adapter declarations must contain public labels only; their trusted
configuration author is responsible for that classification. Adapter changes
fail closed for incompatible existing revisions and need deployment review,
not silent migration. The optional metadata file is packaged when present;
the second platform itself remains a disposable fixture, not a shipped platform.

Pending interventions and passive browser ownership remain process-local as
before. A process restart does not safely reconstruct a retained Chrome session.
Immutable procedures/pins/projection recovery remain durable, while lost runtime
ownership requires operator review. Windows power-loss guarantees still depend
on the filesystem/volume. The build used the cached GNU development toolchain,
not a signed production release. Follow the two-platform manual protocol in the
architecture document before making real-browser readiness claims.

## Proposed PR description

Title: `Generalize conversational navigation learning across installed platforms`

Navigation learning previously depended on Dext-specific controls, grammar,
storage paths and native prompt conditions. Extract the shared session-bound
learning control and declarative public-landmark adapter, and use the existing
chat broker/native checkpoint for every verified installed Web platform. Keep
Dext business/preview permissions isolated and preserve its historical revisions
and conversation pins. New platform-scoped procedures describe corroborated
manual heading transitions and require exact operator approval before publishing
their private canonical `learning.md`.

Validate the same lifecycle with Dext and a distinct synthetic platform through
storage, HTTP/chat continuation, the actual native loop/prompt and compiled entry.
Validation: Python 232 passed/11 privilege skips; Rust 50 passed/2 ignored;
JavaScript 43 passed; Rust check, TypeScript, UI build, wheel/sdist build and
inspection passed. Real Chrome/Dext behavior remains unvalidated and unverified
navigation/business effects remain blocked.

Proposed commit message (not executed):

`feat: share supervised navigation learning across installed platforms`
