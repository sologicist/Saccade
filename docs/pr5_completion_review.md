# PR5 completion, security review and real-Dext readiness

Date: 2026-11-12 (Europe/Paris). Existing branch:
`feat/dext-live-navigation-learning`. Existing [PR #5](https://github.com/sologicist/Saccade/pull/5)
targets `develop`; it was inspected read-only and remains open/unmerged.

## Decision

**PR5 is not ready to merge as completed live Dext functionality.** This review
resolves local onboarding, chat-originated procedure proposals and lost CDP
download evidence. It does not resolve the missing live navigation adapter,
verified Dext client/record identity, record-bound PDF receipt issuer or production
disclosure boundary. CI and synthetic results are not real Dext evidence.

The starting tree was clean at operator-published PR5 commit
`507ec10f9161d12192594310396f346cc425bd95`. PR4/develop is
`91a2f4d10cc72666dabcd95dcc80bb67db15da9e`. The actual committed PR5 diff against
develop was inspected, followed by this additional local diff. No branch switch,
reset, cleanup, staging, commit, push, new PR, PR edit/comment or merge occurred.
Unrelated work and private data were preserved.

The original handoff safety/specification documents were reviewed and their
manifest hashes still matched. The new request was read from the attached text.
`prompts_FRT_MPH_sans_Gemini.zip` was **not opened, extracted, imported or uploaded**.
Development used invented references, fake browser/model boundaries and private
inherited pipe test processes, never real Chrome/Dext or customer data.

## Missing functionality resolved

1. **Safe local onboarding:** `reference_management` initializes client
   directories without files or registry changes; validates exactly three full
   UTF-8 references with per-file diagnostics; and supports explicit real-client
   metadata registration/activation under a process lock, expected-revision CAS
   and atomic replacement. It never imports an archive, overwrites references,
   converts real data to synthetic or grants business/disclosure permissions.
2. **Reference execution boundary:** parent and independent worker both require
   a complete valid three-file bundle before execution. The selected function
   rereads its full reference. Existing source/reference revisions, active-client
   scope, schemas and single-use tickets remain enforced. Hard-linked reference
   files, binary/control-character content and additional Markdown are refused.
   Real registrations may have empty labels/responses; they still fail the real
   privacy gate before accounting data is read during catalogue refresh.
3. **Chat corrections:** explicit local teaching mode intercepts the existing
   chat's Enter/send flow before model execution or ordinary task persistence.
   A conservative French/English complete-sentence compiler derives only generic
   navigation steps. Unknown/private/effectful details are rejected, not omitted
   silently. No raw correction is saved. The candidate shows its source and
   redacted evidence digest; separate exact operator approval remains mandatory.
   Immutable publication, pinned revisions, CAS, recovery and rollback are reused.
   The real Rust-loop test now starts this learning path from a chat correction
   and verifies approved guidance in subsequent model messages.
4. **Operator-channel hardening:** the existing token, chat binding, exact Origin,
   per-run review token, strict JSON and no-store protections remain. Send/stop
   `postMessage` events additionally require the actual matching local iframe
   window and app origin. Foreign pages/frames cannot submit an operator draft.
5. **CDP evidence preservation:** the private Chrome pipe now keeps bounded
   ordered Browser download begin/progress/terminal metadata instead of dropping
   it while waiting for ACKs. Complete trailing frames from the same denial-ACK
   read are checked too. GUID/frame and URL digest remain in memory; filenames,
   file paths and raw URLs are not retained. Invalid, orphaned, replayed,
   inconsistent and overflowing sequences latch failures. Every attempt, including
   canceled/completed events, still blocks scoped operations. Native CDP errors
   are redacted. No allow exception, file reader or receipt issuer was added.

## Capability truth table

| Capability | Status |
| --- | --- |
| Three-file onboarding/diagnostics/registry CAS | IMPLEMENTED AND VERIFIED SYNTHETICALLY |
| Parent/worker complete-bundle validation and fresh revisions | IMPLEMENTED AND VERIFIED SYNTHETICALLY |
| Explicit chat correction → candidate → separate approval → pinned native guidance | IMPLEMENTED AND VERIFIED SYNTHETICALLY |
| Approval authentication, CSRF/origin, stale source/pin/proposal and replay checks | IMPLEMENTED AND VERIFIED SYNTHETICALLY |
| Native scoped navigation preview and independent operator wait/handoff | IMPLEMENTED AND VERIFIED SYNTHETICALLY |
| CDP event collection/default denial, including inherited Windows pipes | IMPLEMENTED AND VERIFIED SYNTHETICALLY |
| New desktop controls and sender-frame guard in an actual running UI | IMPLEMENTED BUT NOT LIVE-TESTED |
| Observed real workspace/client/bank-row binding | BLOCKED — no native semantic identity adapter |
| Approved real navigation gesture/revalidation/postcondition | BLOCKED — no verified frame/backend-node/target/record semantics |
| Controlled single-download exception, file verification and live one-use receipt | BLOCKED — record/document association and full approved lifecycle absent |
| Live bank/scribe provider and exact-payload disclosure consent | BLOCKED — real binding/receipt/native external-effect boundary absent |
| Accounting form fill/save/reconcile | BLOCKED — outside PR5; no mutation permit |
| Real Dext functionality | No capability is VERIFIED ON REAL DEXT |

## Precise blockers and security review

**Navigation.** `browser.rs::parse_mapping` currently carries index/tag/role/name/
line/geometry, not an authoritative Dext record/workspace identity or current frame/
backend-node identity. `dext_navigation_stamp` proves observer/tab/profile/config
scope only. A same-URL SPA transition may change a record. No supplied real test
workspace or observed Dext selectors/semantics establish that a gesture cannot
submit or autosave. Consequently the controller still dispatches no input and
an approved preview returns `verified_dext_navigation_adapter_required`. The
operator claim remains `verified_for_business: false`; no substring, local ID or
model assertion can unlock a real client.

**PDFs.** Native event collection fixes lost evidence, not causal provenance.
It reads during pending commands and is not a continuous approved-download pump.
There is no record-bound one-download permission, private destination/file
verifier, expiry-bound receipt issuer or tested return-to-DENY lifecycle for an
approved exception. Browser begin events identify frame/GUID; progress provides
GUID/counters/state. A reported file path is optional and does not guarantee file
existence. Those events supply no Dext client/workspace/record identity. Thus even
completion cannot authorize live scribe. These protocol facts were checked against
the [official Chrome DevTools Browser schema](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/browser_protocol.json).

All active scoped operations still require a positive native DENY ACK, and any
recorded download attempt/error stops work. Existing post-scope teardown restores
normal Chrome behavior after observer release; this is not an in-scope download
exception. A failed ACK/transport or teardown restoration still requires operator
review. No claim of approved-download restoration testing is made.

**Bank/scribe/privacy.** Active-client-only lookup is unchanged. Real clients are
refused by `BusinessRun.prepare` before corpus/model execution. The normal UI
provides no live or synthetic test receipt override to scribe; a model-selected
PDF path remains denied. Offline fixture receipts are test inputs, not genuine
one-use live receipts. Existing single-use execution tickets are consumed before
execution, including failure. No real provider was enabled and changing
`COMPTABLE_LLM_MODEL` still refuses external I/O. There are no accounting writes,
new browser/network permissions, credential reads or data-disclosure grants.

**Learning.** Only the authenticated UI operator event invokes the compiler.
Page/model/tool content cannot approve or publish. The grammar rejects private
values, URLs, unstable selectors, negations, accounting rules and action bypasses.
Only canonical generic guidance plus hashed evidence/provenance persists. The
shipped native `dext.md` is unchanged. Approved prose grants no permission; per-chat
pins remain fixed until explicit idle adoption, with corruption failing closed.

**Residual host risks.** Advisory locks do not control malicious manual filesystem
writers. Reparse/path/link checks and revision rereads retain documented TOCTOU
limits. Windows file flush/atomic replacement is not a tested hardware power-loss
guarantee. The bounded worker is not an OS sandbox; its process-tree cleanup and
cancellation/GIL tests remain. No hardware crash, real UI, actual Chrome 157
compatibility, Linux execution or external provider compatibility was tested here.

## Tests actually executed

| Check | Actual result |
| --- | --- |
| Full Python/native/fresh-wheel/sdist discovery | 169 total: 159 passed, 10 skipped, 0 failures/errors |
| Rust locked/offline tests on Windows GNU | 45 passed, 2 intentionally ignored, 0 failed; 47 total |
| Rust locked/offline all-target check on Windows | Passed |
| Observer/UI selection/local correction JavaScript tests | 30 passed, 0 skipped/failed |
| UI TypeScript check and production build | Passed; shipping bundle rebuilt |
| Fresh ABI3 Windows wheel / isolated installed native import and real worker | Passed |
| Fresh source archive and privacy/resource inspection | Passed; not independently installed/built from sdist |
| Final Git whitespace/inventory/privacy audit | Passed; 29 local files / 39 total PR5 files; HEAD unchanged, nothing staged/deleted |

Python module totals: business 38; original navigation/store 29; chat correction 5;
packaging 4; native constructor 6; session/API 27; platforms 47; onboarding 13.
The 10 skips are Windows symbolic-link privilege restrictions (7 existing platform,
1 business, 1 navigation and 1 onboarding). Native and packaging tests all ran.
The two Rust ignores are the internal inherited-pipe child helper and deliberate
real-Chrome test. The parent exchange test ran both clean-ACK and interleaved
begin/ACK/canceled-frame cases through genuine inherited Windows handles.

Tools: cached Python 3.12.10, Rust 1.97.1 GNU, maturin 1.16.0 and Node v26.13.0.
Existing ignored Flask/Pillow prerequisites were reused; no dependency, Cargo/npm
lockfile or OS engine implementation changed. GitHub CI was not run for this local
unpublished diff. The initial PR's reported green CI is not evidence for these
uncommitted changes or any live Dext capability.

Commands, from the repository root:

```powershell
$env:CARGO_HOME = (Resolve-Path '.cache/pr1-tools/cargo-home').Path
$env:PATH = (Resolve-Path '.cache/pr1-tools/rust/bin').Path + ';' + (Resolve-Path '.cache/pr1-tools/mingw64/bin').Path + ';' + (Resolve-Path '.cache/pr1-tools/python').Path + ';' + $env:PATH
$env:SACCADE_TEST_PYTHON = (Resolve-Path '.cache/pr1-tools/python/python.exe').Path
& '.cache/pr1-tools/rust/bin/cargo.exe' test --locked --offline --manifest-path AutoCua/web/Cargo.toml
& '.cache/pr1-tools/rust/bin/cargo.exe' check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml
node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs AutoCua/ui/platform_session/selection.test.mjs AutoCua/ui/chat_input/correction.test.mjs
npm.cmd --prefix AutoCua/ui run typecheck
npm.cmd --prefix AutoCua/ui run build
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = 'C:/Users/yassi/Documents/Saccade'
& '.cache/pr2-review/maturin/maturin-1.16.0.data/scripts/maturin.exe' build --locked --offline --profile dev --interpreter .cache/pr1-tools/python/python.exe --out .cache/pr5-completion-wheels
& '.cache/pr2-review/maturin/maturin-1.16.0.data/scripts/maturin.exe' sdist --out .cache/pr5-completion-sdist
& '.cache/pr1-tools/python/python.exe' -B '.cache/pr5-completion-validation/run_python.py'
git -c safe.directory=C:/Users/yassi/Documents/Saccade diff --check
git -c safe.directory=C:/Users/yassi/Documents/Saccade status --short --branch
```

The ignored runner adds the checkout/cached prerequisites to the embedded Python
path, sets `SACCADE_TEST_NATIVE` to the fresh DLL, `SACCADE_TEST_WHEEL` and
`SACCADE_TEST_SDIST` to the artifacts below, and runs complete unittest discovery.
The standard `python -m unittest discover -s tests -t . -v` works in a normally
configured environment; packaging/native flags are needed to run those contracts.
CI discovery automatically includes new Python cases; its JS command now includes
the correction/sender-frame integration tests. Maturin's existing nonfatal
sdist root-manifest probe/crate metadata warnings remain; builds exited 0.

Artifacts under ignored `.cache/`:

- Wheel: `saccade-0.1.9-cp310-abi3-win_amd64.whl`, 551 entries, SHA-256
  `c9b0707693f175f29f7b63d5a27f404f96067d61111b245b89b0281e7ec02a3f`.
- Sdist: `saccade-0.1.9.tar.gz`, 585 entries, SHA-256
  `4b9e25160cd9b431496f0007ba20e136a0c890fa0d0fe46fd12cc1011adf14e1`.

Inspection found zero private platform data/report entries, PDF/ZIP documents,
browser profiles, cache directories or pilot reference bundles in either archive.
New Python modules/current shipping UI assets match the checkout; Rust event
sources are present in the sdist. No private reference was committed or placed in
an automated fixture, model prompt, log, telemetry payload or shipped artifact.

## Operator onboarding and manual live plan

[dext_reference_onboarding.md](dext_reference_onboarding.md) documents actual
locations, safe directory-only initialization, precise validation, explicit
metadata registration and active-client selection. Neither validation nor local
registration constitutes consent to disclose data or permission to process it.

[dext_manual_test_plan.md](dext_manual_test_plan.md) is the separate unexecuted
operator plan for visible dedicated Chrome, manual authentication, real workspace
inspection, invoice/bank previews, learning/review, attempted stale/foreign cases,
blocked PDF/provider checks, interruption, recovery and cleanup. It identifies
which steps cannot pass until a verified adapter/receipt boundary exists.

## Proposed existing-PR update (not published)

Suggested title: `feat(dext): add supervised review, local navigation learning and download evidence`

Suggested body for the existing PR #5, base `develop`:

> Add independent local operator review and versioned navigation guidance to the
> existing Rust Web loop. Chat corrections are compiled locally to a bounded
> generic procedure proposal; exact separate approval publishes immutable revisions
> while per-chat pins and explicit rollback/adoption prevent silent changes.
>
> Complete local three-reference onboarding/validation and metadata-only client
> registration with active-scope revision checks. Validate the full bundle in
> parent and worker, preserve PR4 bank/invoice contracts, reject unsafe/hard-linked
> files, and retain default-off real-data processing.
>
> Preserve ordered bounded CDP download metadata through existing private pipes,
> including events around policy ACKs. Any attempt still stops scoped work; this
> adds no download exception or real receipt. Harden chat sender-frame validation.
>
> This remains a partial PR5: actual Dext gestures, verified real client/record
> binding, causal PDF receipts, independent external disclosure consent and all
> accounting writes stay blocked. Do not merge as completed live functionality.
>
> Validation: Python 159 passed / 10 privilege skips; Rust 45 passed / 2 intentional
> ignores; JS 30 passed; Windows check, UI typecheck/build, fresh isolated wheel/
> native-worker/sdist checks passed. No live Dext/Chrome, private corpus, Gemini
> or Linux run was performed. See the completion review and manual test plan.

Suggested commit message:
`fix(dext): harden local onboarding, chat learning and download evidence`

No Git publication action has been taken; stop for operator review.

## Exact file inventory

The table below distinguishes this local review delta from files already changed
in published PR5 commit `507ec10`. It includes the full PR5 worktree diff against
develop and every nonignored new file. No protected desktop/mobile engine,
dependency lockfile, private data file or shipped native `dext.md` changed.

| File | Changed in this review |
| --- | --- |
| `.github/workflows/ci.yml` | Yes |
| `AutoCua/saccade/business_catalogue.py` | Yes |
| `AutoCua/saccade/business_functions/platforms/dext/runtime.py` | Yes |
| `AutoCua/saccade/business_run.py` | Yes |
| `AutoCua/saccade/business_worker.py` | Yes |
| `AutoCua/saccade/client_references.py` | Yes |
| `AutoCua/saccade/dext_control.py` | Yes |
| `AutoCua/saccade/navigation_correction.py` | Yes |
| `AutoCua/saccade/procedure_store.py` | Yes |
| `AutoCua/saccade/reference_management.py` | Yes |
| `AutoCua/ui/chat_input/chat_input.css` | Existing PR5 |
| `AutoCua/ui/chat_input/chat_input.js` | Yes |
| `AutoCua/ui/chat_input/correction.test.mjs` | Yes |
| `AutoCua/ui/index.js` | Yes |
| `AutoCua/ui/platform_session/dext_review.tsx` | Yes |
| `AutoCua/ui/platform_session/platform_session.tsx` | Existing PR5 |
| `AutoCua/ui/service.py` | Existing PR5 |
| `AutoCua/web/agent/main_driver/service.rs` | Yes |
| `AutoCua/web/browser/browser.rs` | Existing PR5 |
| `AutoCua/web/browser/chrome_pipe.rs` | Yes |
| `AutoCua/web/browser/download_events.rs` | Yes |
| `AutoCua/web/controller/skills/service.rs` | Existing PR5 |
| `AutoCua/web/controller/view.rs` | Existing PR5 |
| `AutoCua/web/lib.rs` | Yes |
| `AutoCua/web/platform_scope.rs` | Existing PR5 |
| `AutoCua/web/tool_registry/service.rs` | Existing PR5 |
| `docs/dext_business_tools.md` | Yes |
| `docs/dext_manual_test_plan.md` | Yes |
| `docs/dext_navigation_learning.md` | Yes |
| `docs/dext_reference_onboarding.md` | Yes |
| `docs/pr5_completion_review.md` | Yes |
| `docs/pr5_review.md` | Yes |
| `tests/business_fixtures.py` | Yes |
| `tests/test_business_tools.py` | Existing PR5 |
| `tests/test_dext_navigation.py` | Existing PR5 |
| `tests/test_navigation_correction.py` | Yes |
| `tests/test_packaging.py` | Yes |
| `tests/test_platform_sessions.py` | Yes |
| `tests/test_reference_management.py` | Yes |

This review: 29 files. Full PR5 against develop: 39 files.
