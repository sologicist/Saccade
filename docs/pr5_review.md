# PR5 initial implementation review (historical checkpoint)

This records the initial PR5 checkpoint subsequently committed by the operator as
`507ec10f9161d12192594310396f346cc425bd95`. The current completion/security review,
updated results, file inventory and merge-readiness assessment are in
[pr5_completion_review.md](pr5_completion_review.md). The original counts and
limitations below describe that earlier checkpoint, not the current worktree.

Date: 2026-11-12. Branch: `feat/dext-live-navigation-learning`.

## Outcome and incomplete live goal

The independent safe slices are implemented: native scoped navigation previews,
real UI/backend operator decisions, generic procedure diffs and atomic versioned
publication, durable pins, explicit rollback, unverified dossier claims, reference
revision binding, three-file migration and operator review for quotes/credit notes.

**PR5 is not functionally complete for live Dext.** No gesture, real dossier/record
binding, live PDF receipt, production accounting provider or disclosure consent
boundary is enabled. These are deliberate fail-closed blocks, not simulated live
successes. [dext_navigation_learning.md](dext_navigation_learning.md) documents
the exact missing proofs, security review, manual pilot and migration decisions.

`git fetch origin develop` succeeded. Local HEAD, `develop`, `origin/develop`
and merge base all matched `91a2f4d10cc72666dabcd95dcc80bb67db15da9e`, the PR4
squash. The requested feature branch already existed at that commit and the
starting worktree was clean. No branch rewrite, staging, commit, push, PR creation,
merge, reset, private-data extraction or user-data deletion was performed.

The five requested extracted handoff documents were read and matched the ZIP
byte-for-byte. All 50 file size/SHA-256 entries in its manifest verified. The
manifest itself hashes to `019d3c6c1b3b7eb1d324cea4b4d962c6125e43ddc4796a20cb035e52e6c878b6`.
Selected sanitized historical navigation/learning/download/business sources were
inspected as references, never executed or installed. No private accounting file
from the user's IDE tabs or original archive was opened.

## Exact changed files

- `.github/workflows/ci.yml`
- `AutoCua/saccade/business_functions/platforms/dext/runtime.py`
- `AutoCua/saccade/business_run.py`
- `AutoCua/saccade/dext_control.py`
- `AutoCua/saccade/procedure_store.py`
- `AutoCua/ui/chat_input/chat_input.css`
- `AutoCua/ui/index.js`
- `AutoCua/ui/platform_session/dext_review.tsx`
- `AutoCua/ui/platform_session/platform_session.tsx`
- `AutoCua/ui/service.py`
- `AutoCua/web/agent/main_driver/service.rs`
- `AutoCua/web/browser/browser.rs`
- `AutoCua/web/controller/skills/service.rs`
- `AutoCua/web/controller/view.rs`
- `AutoCua/web/platform_scope.rs`
- `AutoCua/web/tool_registry/service.rs`
- `docs/dext_business_tools.md`
- `docs/dext_navigation_learning.md`
- `docs/pr5_review.md`
- `tests/test_business_tools.py`
- `tests/test_dext_navigation.py`
- `tests/test_packaging.py`
- `tests/test_platform_sessions.py`

Total: 23 files. No desktop/mobile engine, Chrome pipe/launch/bridge/extension,
platform manifest, dependency lockfile or shipped `dext.md` was modified.
Existing platform-data Git/distribution exclusions already cover all new runtime
state, so no new exclusion rule was necessary.

## Validation

Tools: cached Python 3.12.10, Rust 1.97.1 Windows GNU, maturin 1.16.0 and Node
v26.13.0. Existing ignored PR4 Flask/Pillow prerequisites were reused. No runtime
or development dependency was added. No network/model calls occur in these tests.

| Check | Actual result |
| --- | --- |
| Full Python discovery with native, wheel and sdist flags | 150 total: 141 passed, 9 skipped, 0 failures/errors |
| Rust unit/integration tests, locked/offline | 41 passed, 2 intentionally ignored, 0 failed; 43 total |
| Rust check, all targets on Windows, locked/offline | Passed |
| Existing JS observer/UI session contracts | 25 passed, 0 failed/skipped |
| UI typecheck and production build | Passed; shipping `index.js` rebuilt |
| Fresh ABI3 Windows wheel | Built; isolated install/native import/real synthetic worker passed |
| Fresh source archive | Built and inspected; packaging regression passed |
| Git whitespace/inventory/privacy checks | Passed; all 23 changed files listed, no protected-engine/data changes |

The two ignored Rust cases are the inherited-pipe internal child helper and the
real-Chrome test. The parent inherited-handle exchange ran and passed. Python
skips reflect missing Windows symlink privilege only, not a skipped native or
packaging contract.

Python breakdown: business tools 38 (37 passed, 1 privilege skip); navigation and
learning 29 (28 passed, 1 privilege skip); packaging 4 passed; native entry 6
passed; session/API contracts 26 passed; platform contracts 47 (40 passed,
7 privilege skips). The final complete Python command exited 0.

Both distributions include the new Python control/store and current shipping UI
assets. Isolated wheel tests import the native extension and execute a real
bounded synthetic worker without checkout fallback. The source archive was
inspected, not independently built on Linux or installed from source.

- `saccade-0.1.9-cp310-abi3-win_amd64.whl`: 547 entries; SHA-256
  `994c4045192bdf48fb5d543464f799e2c2dcad0ec5801e117ff6a14cc80448ae`.
- `saccade-0.1.9.tar.gz`: 580 entries; SHA-256
  `857d85ee4d6f5ee00b416c78278233f3512172874a535d753dd412297e622ab1`.

Inspection found zero private platform data/report entries, PDFs, browser-profile
directories, cache trees or legacy/pilot reference bundles in either artifact.

Commands actually executed, from the repository root:

```powershell
$env:CARGO_HOME = (Resolve-Path '.cache/pr1-tools/cargo-home').Path
$env:PATH = (Resolve-Path '.cache/pr1-tools/rust/bin').Path + ';' + (Resolve-Path '.cache/pr1-tools/mingw64/bin').Path + ';' + (Resolve-Path '.cache/pr1-tools/python').Path + ';' + $env:PATH
$env:SACCADE_TEST_PYTHON = (Resolve-Path '.cache/pr1-tools/python/python.exe').Path
& '.cache/pr1-tools/rust/bin/cargo.exe' test --locked --offline --manifest-path AutoCua/web/Cargo.toml
& '.cache/pr1-tools/rust/bin/cargo.exe' check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml
node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs AutoCua/ui/platform_session/selection.test.mjs
npm.cmd --prefix AutoCua/ui run typecheck
npm.cmd --prefix AutoCua/ui run build
$env:GIT_CONFIG_COUNT = '1'
$env:GIT_CONFIG_KEY_0 = 'safe.directory'
$env:GIT_CONFIG_VALUE_0 = 'C:/Users/yassi/Documents/Saccade'
& '.cache/pr2-review/maturin/maturin-1.16.0.data/scripts/maturin.exe' build --locked --offline --profile dev --interpreter .cache/pr1-tools/python/python.exe --out .cache/pr5-wheels
& '.cache/pr2-review/maturin/maturin-1.16.0.data/scripts/maturin.exe' sdist --out .cache/pr5-sdist
& '.cache/pr1-tools/python/python.exe' -B '.cache/pr5-validation/run_python.py'
git -c safe.directory=C:/Users/yassi/Documents/Saccade diff --check
git -c safe.directory=C:/Users/yassi/Documents/Saccade status --short --branch
```

The ignored local runner adds this checkout and cached prerequisites to the
embedded interpreter path and sets `SACCADE_TEST_NATIVE` to the fresh debug DLL,
`SACCADE_TEST_WHEEL` to `.cache/pr5-wheels/saccade-0.1.9-cp310-abi3-win_amd64.whl`,
and `SACCADE_TEST_SDIST` to `.cache/pr5-sdist/saccade-0.1.9.tar.gz`. It performs
`unittest.defaultTestLoader.discover("tests", top_level_dir=".")` and writes counts
to ignored `.cache/pr5-validation/python-results.json`. CI uses normal Python;
the existing discovery command includes all new tests.

Resolved validation attempts: reading UTF-8 handoff text with the embedded
interpreter's default CP1252 stdout initially raised `UnicodeEncodeError`; setting
`PYTHONIOENCODING=utf-8` resolved it. A newly added native prompt-adoption assertion
initially failed because the synthetic full-loop fixture had no native domain
manifest at its overridden Web root. Adding the isolated empty Dext domain
fixture resolved it; the final real-loop test checks overlay presence in model
messages. No failing test was removed. Maturin still emits its existing nonfatal
root-Cargo probe/crate metadata warnings during successful sdist discovery.

## Acceptance checklist

Here VERIFIED SYNTHETIC means tested with invented data/fake browser boundaries,
never live Dext. No item is VERIFIED LIVE.

| Handoff review item | Status and evidence/limitation |
| --- | --- |
| PR4 squash base; preserve develop/main | VERIFIED SYNTHETIC — fetched refs and exact merge base checked |
| No Git publication/rewrite | VERIFIED SYNTHETIC — HEAD unchanged, diff remains local |
| No private corpus/PDF/profile/secret in changed files/distributions | VERIFIED SYNTHETIC — inventory and archive inspection |
| Existing tests/checks/build/packaging | VERIFIED SYNTHETIC on Windows; Linux/remote CI NOT TESTED |
| Dext supervised/quality/profile/native DENY | VERIFIED SYNTHETIC — existing native/session/observer tests retained |
| Approved real menu-to-invoice gesture | BLOCKED — no verified Dext target semantics or postcondition |
| Real workspace/record matching, including same URL | BLOCKED — preview revisions invalidate claims but do not prove record identity |
| Stale/foreign/popup/lost observer/rejected/uncertain target | VERIFIED SYNTHETIC — existing sticky scope and new preview/review contracts; no dispatch |
| Bank-row navigation with exact real label | BLOCKED — registered synthetic labels only |
| No generic click/script/input/autosave bypass | VERIFIED SYNTHETIC — native deny tests and stricter Dext URL action denial |
| Tracked native procedure unchanged | VERIFIED SYNTHETIC — generated fixtures, baseline-byte checks and final diff |
| Correction produces candidate, not overwrite | VERIFIED SYNTHETIC — closed route selection and old/new/diff |
| Approval bound to proposal/base/candidate | VERIFIED SYNTHETIC — exact UI event and backend checks |
| Refusal/stale/concurrent edits leave active intact | VERIFIED SYNTHETIC — consumed refusals and whole-pointer CAS |
| Atomic publication/immutable snapshots/crash/rollback | VERIFIED SYNTHETIC — before/after replace failures, cross-process lock, pin/pointer loss |
| Next run reuses only approved revision | VERIFIED SYNTHETIC — durable pin tests and actual native model-message assertion |
| No private values/unstable IDs in reusable SOP | VERIFIED SYNTHETIC — closed grammar and filesystem inspection |
| Operator real dossier-to-workspace binding | BLOCKED — claim is explicitly not business authority |
| Fresh isolated client reference reads | VERIFIED SYNTHETIC — exactly three files; optional generic file intentionally removed |
| Approximately 1.93 MiB purchases reference | VERIFIED SYNTHETIC — full 2,025,020-byte text accepted; >2 MiB rejected |
| PR4 source/schema/worker/ticket protections | VERIFIED SYNTHETIC — full regression suite and stale-reference worker check |
| Independent live Gemini consent | BLOCKED — no grant/network adapter; fake default remains |
| Typed bank result from exact verified real row | BLOCKED live; VERIFIED SYNTHETIC for exact registered fake label |
| One-use real record-bound PDF receipt/scribe | BLOCKED — no live receipt issuer or global download exception |
| Native DENY after controlled download attempt | BLOCKED as a new lifecycle; existing permanent DENY/cancellation VERIFIED SYNTHETIC |
| No Dext form entry/save | VERIFIED SYNTHETIC — no new browser dispatch path or mutation permit |
| Fake browser distinctly labeled | VERIFIED SYNTHETIC — fixture text, tests and report explicitly synthetic |
| Real Windows Chrome/Dext manual pilot | NOT TESTED — operator initiation required |
| Real PDF capture/Gemini analysis | BLOCKED — no real input, credential or external call used |
| Exact counts/skips/commands | VERIFIED SYNTHETIC — local result files and commands above |
| Threat model/manual steps/next phase | VERIFIED SYNTHETIC as documentation; manual steps NOT TESTED |

## Risks and remaining work

- The requested live navigation/accounting workflow remains blocked, as detailed
  above. Operator review of a preview does not prove target safety or record
  identity. No fake download event is promoted into a trusted live receipt.
- The UI was typechecked and built and real Flask/native flow contracts ran;
  visual interaction in a running desktop browser was NOT TESTED.
- Linux compilation is configured by the existing CI matrix but was not run on
  this Windows host. Updated GitHub Actions have not run remotely.
- Store integrity trusts the local host filesystem/ACLs. Reparse checks are not
  a full defense against malicious concurrent same-account filesystem changes.
  Windows atomic replacement/file flush is not a tested hardware power-loss
  guarantee. Inert temp evidence has no automatic retention cleanup.
- Missing/corrupt pointer/pin or interrupted first initialization may require
  operator repair. The store intentionally refuses automatic adoption of orphan
  snapshots or silent replacement with the latest revision.
- PR4's bounded worker remains a subprocess, not an OS sandbox. Compiled desktop
  executables still require a trusted Python worker runtime before execution.
- No genuine provider endpoint/API request or complete consent/effect journal was
  implemented. Real provider compatibility and real classification are unverified.

Next prerequisite PR: establish observed Dext workspace/record/frame identity and
safe one-step target/postcondition semantics in an operator-controlled test
workspace. Then add record-bound PDF lifecycle receipts and independently approved
exact-payload disclosure before live analysis. A later, separate write-effect PR
can propose field preview/fill with durable intent, reconciliation and idempotence;
it must not infer save permission from an approved accounting proposal.

## Proposed commit and PR description

Title: `feat(dext): add operator-reviewed navigation previews and versioned procedures`

Base: `develop`. This title deliberately does not claim verified live navigation
or real accounting proposals.

Proposed body:

> Supervised Dext sessions previously had no trusted operator review or durable
> navigation-learning path. Add one per-run navigation-preview tool to the
> existing Rust Web registry/controller/loop, independent authenticated UI review,
> and immutable local procedure proposals with exact approval, CAS publication,
> crash recovery, pinned revisions, explicit adoption and rollback.
>
> Preserve native domain selection, Chrome profile/observer/download DENY and PR4
> business gates. Restrict accounting references to the three client-specific
> files, bind reference revisions to decisions/workers, and require operator
> review for quotes and credit notes. No generic reference file or dependency is
> added. Same-host model URL navigation is denied for Dext.
>
> Live Dext gestures, verified real client/record binding, causal PDF receipts,
> production accounting-provider disclosure and all accounting writes remain
> blocked. The new tool previews and waits for a genuine operator event but never
> clicks. This is a partial PR5 implementation, not live Dext acceptance.
>
> Validation: Python 141 passed / 9 symlink-privilege skips; Rust 41 passed / two
> intentional ignores; 25 JS tests passed; Windows all-target check, UI
> typecheck/build and fresh isolated wheel/native-worker/sdist contracts passed.
> Linux and live Chrome/Dext/provider validation remain unverified locally.

No commit, push, PR or merge has been performed. Stop for the user's separate
explicit Git-publication approval.
