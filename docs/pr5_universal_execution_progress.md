# PR5 universal supervised execution

Implementation report for `feat/dext-live-navigation-learning`. This replaces
the incomplete checkpoint. Common infrastructure is implemented; real
Chrome/Dext acceptance remains unperformed. Synthetic results never stand in
for production integration validation.

## Implementation checklist

- [x] Platform-agnostic, session-bound execution authorization, separate from
  procedure approval, retained by the existing broker across continuation.
- [x] Normal Web clicks, holds, input, renderer keyboard shortcuts, dialogs,
  scrolling and scoped navigation use the existing controller. Installed public
  navigation policy permits normal clicks; unclassified effects receive an exact
  action review. Auto permissions and Generic's normal registry are preserved.
- [x] Explicit downloads use the owned bridge and fixed top-frame same-origin
  fetch with redirect/status/MIME/size checks, atomic private publication and
  SHA-256 verification. Browser-wide download DENY stays enabled throughout.
- [x] A platform-local installed capability registry provides static schemas,
  source revisions, effects and existing-worker dispatch. The version-1 Dext
  catalogue/worker remain the compatibility path.
- [x] Spontaneous corrections use the existing teaching/checkpoint/continuation
  path. The agent can execute visible corrected controls. Changed, scoped
  control-to-heading observations ground separately approved learning. Back
  checks its history destination before dispatch and never undoes a business effect.
- [x] Three independent registered platforms exercise different functions,
  private outputs, navigation policies, exact approvals, native continuation,
  actual child workers, verified file receipts and independently pinned learning.

## One existing engine

`AgentService.process_request`, scanner, `ControllerView.one`/`one_inner`, native
click/input/keyboard/dialog/tab dispatch, provider registry, conversation
persistence and operator browser handoff remain the execution path. No LangGraph,
second loop, new browser driver or parallel conversation system was added.
Per-run tool additions retain the selected fast/quality and single-tab base
registry rather than reconstructing a different set of core tools.

Before a gesture, the controller refreshes the existing scanner, compares its
mapping, obtains host-side authority and calls normal native dispatch. Model JSON
cannot manufacture authority. Existing pre/post scope checks enforce the browser,
profile lease, observer and host boundary. Cancellation is checked before action
authorization. Capability/download results use the same paired tool-result path.
Unsupported or uncertain operations pause without claiming success or replaying
an effect; hard scope/ownership failures retain their recovery gate.

## Installed contracts

Optional `platforms/<id>/execution.json` is trusted installed policy:

```json
{"schema_version":1,"navigation":[{"name":"Public section","role":"link"}]}
```

An absent policy grants no automatic gestures, while targeted approval remains
available. Short public labels are installed as permissions by a trusted
operator; learned Markdown cannot add them. A declaration must be reviewed:
visible labels alone cannot prove that a website control has no business effect.

Optional `platforms/<id>/capabilities.json` registers only that platform's own
names and sources under `platforms/<id>/functions/`:

```json
{
  "schema_version":1,
  "platform_id":"example",
  "functions":[{
    "id":"example.summarize",
    "source":"summary.py",
    "symbol":"summarize",
    "effect":"compute",
    "destination":"local processing",
    "description":"Summarize public operator-provided text",
    "output_visibility":"public"
  }]
}
```

Callable annotations use the existing schema grammar. Effects are `read`,
`compute`, `disclosure`, `mutation` or `delete`; the last three require a declared
`verify` callable returning exactly `True` after execution. A failed verification
is never successful completion or permission to retry. The verifier itself is
part of the trusted installed implementation.

`output_visibility: "operator"` keeps results out of model tool results and
stores them locally for the authenticated UI. Optional `document_input` names a
string argument accepting only `receipt:<id>` from this platform/conversation.
The worker verifies the private path, size and SHA-256 before substituting the
local file path. Document outputs must be operator-only.
`requires_verified_record: true` blocks until record identity is independently
established; a download proves neither Dext client/record identity nor disclosure
permission.

Discovery never imports source and fingerprints policy/source. The existing
isolated child rechecks revisions before and after invocation. Per-function
validation remains strict despite combined provider argument schemas. Unknown
functions, foreign namespaces, traversal, unsafe files and Dext legacy overrides
fail closed. Current generic bundles are self-contained Python sources: explicit
imports and dynamic execution entrypoints are rejected. External dependency
bundles are unsupported. This trusted-code contract is **not an OS/Python
sandbox**: installed code requires review and retains the user's filesystem
privileges, as existing Dext implementations do. Model arguments cannot select
another platform's module or callable.

## Authorization and security review

- Decisions bind platform/configuration, profile, conversation, retained native
  browser session, tab, page digest, exact action, observed target/focus/dialog,
  effect, destination and installed policy/capability revision. The origin run is
  sealed into the chat presentation. A fresh observer may revalidate the same
  browser; a replacement browser cannot reuse approval.
- Exact action phrases are required, with distinct disclosure/mutation/deletion
  wording. Informational Yes, authentication claims and procedure approval
  confer no execution permission. Chat never requests passwords or MFA secrets.
- Decisions expire after five minutes and are consumed before dispatch. Duplicate
  responses/resumes, changed targets, foreign chats/platforms and failed effects
  cannot replay them. Expiration offers fresh observation and a new decision.
- Pauses use the existing broker/retained Chrome ownership, with no model calls
  while waiting. Continuation preserves history and revalidates ownership. No
  competing browser or debugging transport is introduced.
- Private outputs/downloads stay under the selected platform's excluded
  `data/navigation/` directory. Results API checks local authentication/origin,
  saved platform binding and result session. The UI hides a previous
  conversation's private results when switching chats.
- Every platform retains its own functions, clients, policies, profiles,
  baseline, canonical `learning.md`, snapshots, history and pins. There is no
  global merged store or silent migration. Dext bank/scribe, client binding and
  the three accounting references are preserved; no `comptable.md` was added.
- Shipped `dext.md`, private reference/client files and approved learning were
  not edited. Fixtures are synthetic. No staging, commit, push, PR, merge,
  profile reset or deletion of user data was performed.

## Production limitations and real acceptance

The download tool supports unique observed top-frame same-origin HTTPS links,
status 200, PDF/octet-stream/plain MIME, nonempty bodies up to 8 MiB and a
20-second fetch deadline. Blob links, redirects, cross-origin storage, custom
buttons and iframe resources remain blocked. No browser-wide allow window is
opened. A file hash verifies bytes, not authenticity or accounting correctness.

Current real Dext link/frame/record semantics and downloaded-PDF Scribe/OCR have
not been verified. The existing live-Scribe guard remains; no synthetic receipt
is substituted for a client document. Generic receipt-to-installed-function
dispatch is implemented and tested separately. Process restart cannot resurrect
a live browser/action approval. Existing durable conversation/learning recovery
is preserved without replaying uncertain external effects.

Native integration replaces only browser observation/physical-input boundaries
and exercises the actual Rust loop, broker, continuation constructor, worker and
filesystem. JS tests execute actual fixed bridge functions with synthetic browser
and network APIs. Neither proves real Chrome behavior. Authorized live acceptance
must verify private authentication, same-window resume, observed navigation,
exact download approval/denial, saved byte hash, refusal and cleanup on the
installed Chrome/Dext version, using authorized synthetic records first.

## Validation results

Final validation on Windows, after rebuilding the native extension and wheel:

- `.cache/pr1-tools/python/python.exe .cache/operator-validation/run_python.py`:
  **272 discovered, 261 passed, 11 skipped, zero failures/errors** (85.357s).
  The skips require unavailable Windows symlink privileges. This includes
  17 universal-execution tests, 49 session/API tests, 10 compiled native-entry
  tests and four wheel/sdist tests. The extracted-wheel test also executes a
  generic installed function in the real child worker alongside legacy Dext.
- `cargo check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml`:
  passed.
- `cargo test --locked --offline --manifest-path AutoCua/web/Cargo.toml`:
  **53 passed, 2 ignored, zero failures** (10.14s). Ignored cases are the internal
  inherited-pipe child helper (used by its parent test) and opt-in real Chrome.
  The native integration includes three-platform actions/functions/downloads,
  same-browser continuation, failed-download handoff, and preservation of fast
  and single-tab tool registries.
- `node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs AutoCua/ui/platform_session/selection.test.mjs AutoCua/ui/platform_session/operator_review.test.mjs AutoCua/ui/chat_input/correction.test.mjs`:
  **49 passed, zero failures/skips**. These include actual fixed bridge-function
  execution, denial of foreign/changed/redirected/oversize downloads, focus
  privacy, and foreign history refusal before dispatch.
- `npm.cmd --prefix AutoCua/ui run typecheck` and `run build`: passed; tracked
  `AutoCua/ui/index.js` rebuilt.
- Maturin `build --locked --offline --profile dev --out .cache/operator-wheels`
  and `sdist --out .cache/operator-sdist`: passed. Inspected
  `saccade-0.1.9-cp310-abi3-win_amd64.whl` and `saccade-0.1.9.tar.gz`; module
  contents match the checkout and private platform data is excluded. Existing
  nonfatal sdist root-Cargo.toml probe/package-metadata warnings remain.
- `git diff --check`: passed; Git reports its existing generated-bundle
  LF-to-CRLF notice. The report's 26-file list was compared with `git status`
  and matches exactly. The index remains unchanged.
- Linux Rust tests were not executed: the previously inspected local WSL
  Docker Desktop environment has no Cargo. No remote CI was started.
- No real Chrome, Dext session, external provider or private accounting dataset
  was exercised. Browser boundaries in these tests are synthetic; the production
  limitations above remain unverified by live acceptance.

## Exact changed files

```text
AutoCua/saccade/business_run.py
AutoCua/saccade/business_worker.py
AutoCua/saccade/capabilities.py (new)
AutoCua/saccade/execution.py (new)
AutoCua/saccade/navigation_correction.py
AutoCua/saccade/operator_language.py
AutoCua/saccade/operator_requests.py
AutoCua/saccade/platform_learning.py
AutoCua/ui/index.js (rebuilt)
AutoCua/ui/platform_session/operator_chat.ts
AutoCua/ui/platform_session/operator_review.tsx
AutoCua/ui/service.py
AutoCua/web/agent/main_driver/service.rs
AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs
AutoCua/web/browser/AutoCuaBridge/tools.js
AutoCua/web/browser/browser.rs
AutoCua/web/controller/click/service.rs
AutoCua/web/controller/tab/service.rs
AutoCua/web/controller/view.rs
AutoCua/web/platform_scope.rs
AutoCua/web/tool_registry/service.rs
docs/pr5_universal_execution_progress.md
pyproject.toml
tests/test_packaging.py
tests/test_platform_sessions.py
tests/test_universal_execution.py (new)
```

The existing branch and implementation were retained. Other platform engine
directories were not modified. Build products/logs stay in ignored caches,
except the repository's tracked UI bundle.

## Proposed PR description

**Title:** Complete supervised execution through the existing AutoCua Web engine

Supervised platform sessions now execute normal observed Web actions through
the existing scanner/controller, requesting exact one-use decisions for uncertain
effects. Same-chat continuation retains browser authority; procedure learning
remains separately reviewed and independently pinned.

Add a platform-local capability contract using the existing bounded worker,
preserve Dext bank/scribe dispatch, and verify explicitly approved same-origin
downloads without relaxing Chrome download denial. Exercise three independent
platforms across authorization, native continuation, actual workers, private
receipts, failure handling and approved learning. Real Chrome/Dext and live
accounting validation remain unperformed.

**Proposed commit message:**
`feat(web): complete platform-scoped supervised execution and learning`
