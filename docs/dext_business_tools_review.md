# PR4 review and validation

Validation date: 2026-11-12. Branch: `feat/dext-business-tools`.
Base and unchanged HEAD: `1d53352350ee6842571fba509b8004be61a624fe` (`develop`). The starting tree was clean. No commit, push, PR creation, merge, rebase, reset or user-data deletion was performed.

## Result

Dext now has one per-run native `call_function` tool on the existing Rust Web path. AST discovery, independent native/Python gates, frozen source revisions, bounded private subprocesses and normal correlated chat results are integrated. The actual `AgentService.process_request` loop is exercised with a fake model and page, a real worker, positive and denied calls, source changes and operator handoff. No second browser driver or agent loop was added.

`bank` preserves the inspected exact-label/full-Markdown response contract and rejects malformed or 512-prefixed accounts. The accounting provider is explicitly a trusted synthetic fake. `scribe` preserves legacy proposal/review validation in trusted offline tests; normal sessions require a future verified download receipt and never enable live PDF access. Null/uncertain classifications require operator review. Existing Chrome download denial, profile isolation/lease and sticky navigation scope remain in place.

Architecture, source-specific compatibility decisions, trust boundaries, privacy limits and the manual smoke-test checklist are in [dext_business_tools.md](dext_business_tools.md).

## Exact changed files

- `.github/workflows/ci.yml`
- `.gitignore`
- `AutoCua/saccade/business_catalogue.py`
- `AutoCua/saccade/business_contract.py`
- `AutoCua/saccade/business_functions/__init__.py`
- `AutoCua/saccade/business_functions/platforms/__init__.py`
- `AutoCua/saccade/business_functions/platforms/dext/__init__.py`
- `AutoCua/saccade/business_functions/platforms/dext/functions.py`
- `AutoCua/saccade/business_functions/platforms/dext/invoice_validation.py`
- `AutoCua/saccade/business_functions/platforms/dext/policy.json`
- `AutoCua/saccade/business_functions/platforms/dext/runtime.py`
- `AutoCua/saccade/business_process.py`
- `AutoCua/saccade/business_run.py`
- `AutoCua/saccade/business_worker.py`
- `AutoCua/web/agent/main_driver/service.rs`
- `AutoCua/web/browser/browser.rs`
- `AutoCua/web/controller/skills/service.rs`
- `AutoCua/web/controller/view.rs`
- `AutoCua/web/lib.rs`
- `AutoCua/web/platform_scope.rs`
- `AutoCua/web/tool_registry/business.rs`
- `AutoCua/web/tool_registry/service.rs`
- `docs/dext_business_tools.md`
- `docs/dext_business_tools_review.md`
- `pyproject.toml`
- `tests/business_fixtures.py`
- `tests/test_business_tools.py`
- `tests/test_packaging.py`

Total: 28 files. No desktop/mobile engine implementation, native domain procedure, platform manifest, Chrome launch/pipe implementation, or shipping UI bundle changed.

## Actual validation

Local execution used repository-cached Python 3.12.10, Rust 1.97.1 and maturin 1.16.0 because the system Python launcher could not start the Windows Store installation under the sandbox account. Node was v26.13.0. Existing Flask/Pillow test prerequisites were downloaded into ignored `.cache/pr4-test-deps`; no runtime dependency was added to the project.

| Check | Actual result |
| --- | --- |
| Full Python discovery, native and fresh-wheel/sdist flags enabled | 119 tests: 111 passed, 8 skipped, 0 failures, 0 errors |
| Rust tests, locked/offline, Windows GNU toolchain | 40 passed, 2 ignored, 0 failed (42 total) |
| Rust check, locked/offline, all targets on Windows | Passed |
| Extension observer and UI session selection Node tests | 25 passed, 0 skipped, 0 failed |
| UI TypeScript typecheck | Passed |
| UI production build | Passed; generated bundle matched HEAD byte-for-byte before restoring normal Windows checkout line endings |
| Fresh Windows ABI3 wheel | Built; isolated extraction, installed catalogue/native import and real synthetic worker passed |
| Source distribution | Built, inspected and covered by the packaging regression test |
| git diff --check | Passed |

Python test-count breakdown:

- `test_business_tools`: 38 tests.
- `test_packaging`: 4 tests.
- `test_platform_session_native`: 6 tests.
- `test_platform_sessions`: 24 tests.
- `test_platforms`: 47 tests.

The eight Python skips are solely symlink-creation privilege restrictions (seven existing platform cases and one new business case). No native-entry or packaging contract was skipped in the final run. The two ignored Rust cases are the internal inherited-pipe child helper and the deliberately ignored real-Chrome test; the parent inherited-handle exchange test ran and passed.

Commands actually used (repository-root working directory):

```powershell
$env:CARGO_HOME = (Resolve-Path '.cache/pr1-tools/cargo-home').Path
$env:PATH = (Resolve-Path '.cache/pr1-tools/rust/bin').Path + ';' + (Resolve-Path '.cache/pr1-tools/mingw64/bin').Path + ';' + (Resolve-Path '.cache/pr1-tools/python').Path + ';' + $env:PATH
$env:SACCADE_TEST_PYTHON = (Resolve-Path '.cache/pr1-tools/python/python.exe').Path
& '.cache/pr1-tools/rust/bin/cargo.exe' test --locked --offline --manifest-path AutoCua/web/Cargo.toml
& '.cache/pr1-tools/rust/bin/cargo.exe' check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml
node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs AutoCua/ui/platform_session/selection.test.mjs
npm.cmd --prefix AutoCua/ui run typecheck
npm.cmd --prefix AutoCua/ui run build
$env:GIT_CONFIG_COUNT='1'
$env:GIT_CONFIG_KEY_0='safe.directory'
$env:GIT_CONFIG_VALUE_0='C:/Users/yassi/Documents/Saccade'
& '.cache/pr2-review/maturin/maturin-1.16.0.data/scripts/maturin.exe' build --locked --offline --profile dev --interpreter .cache/pr1-tools/python/python.exe --out .cache/pr4-wheels
& '.cache/pr2-review/maturin/maturin-1.16.0.data/scripts/maturin.exe' sdist --out .cache/pr4-sdist
& '.cache/pr1-tools/python/python.exe' -B '.cache/pr4-validation/run_python.py'
git -c safe.directory=C:/Users/yassi/Documents/Saccade diff --check
git -c safe.directory=C:/Users/yassi/Documents/Saccade status --short
```

The local Python runner adds the repository and cached prerequisites to the embedded interpreter path, sets `SACCADE_TEST_NATIVE` to the freshly built DLL, `SACCADE_TEST_WHEEL` to the rebuilt wheel and `SACCADE_TEST_SDIST` to the rebuilt source archive, and executes `unittest.defaultTestLoader.discover("tests", top_level_dir=".")`. The standard Python commands for normal installations and CI are in the architecture guide.

Resolved validation attempts: the initial wheel comparison correctly rejected an artifact made before later source changes; rebuilding resolved it. An explicit `maturin sdist --manifest-path AutoCua/web/Cargo.toml` invocation failed to find the root pyproject; the repository-root default invocation built the inspected archive successfully. Maturin 1.16.0 still emits a nonfatal root-Cargo.toml probe message and the existing crate-metadata warning during sdist discovery. The final sdist command exited 0.

A final Rust rerun initially exited with Windows `STATUS_DLL_NOT_FOUND` because that invocation omitted the cached Python directory from `PATH`. Restoring the documented environment resolved the missing Python DLL; the subsequent complete Rust test and all-target check commands exited 0.

Artifact inspection found zero private platform data/report paths, local PDFs, browser-profile directories, cache trees or pilot-reference bundles in either distribution. Required business Python files, policy and technical platform metadata were present.

- `saccade-0.1.9-cp310-abi3-win_amd64.whl`: 544 entries; SHA-256 `ace74c87b1d880862eb5d688204fbb06d4105b1ecccae8a898f70215d304ac9a`.
- `saccade-0.1.9.tar.gz`: 577 entries; SHA-256 `60973b1d92384a3a08dd0ef1923cccbeb63ae43cbed261e05c2186b27f944647`.

## Limits and remaining validation

- No Chrome, authenticated Dext, real cloud-model call, real client input, download or accounting mutation was used. The manual supervised smoke test remains for the operator; this is not evidence of live end-to-end accounting.
- Linux compilation is configured in CI but was not executed on this Windows host. Updated GitHub Actions have not run remotely for these uncommitted changes.
- The worker is not a security sandbox. It retains host filesystem/network permissions; trusted installation integrity and the documented TOCTOU limits still apply.
- Real client/provider disclosure, live PDFs and mutations remain blocked. Compiled desktop executables fail closed until a trusted worker Python runtime is explicitly supported; source and wheel Python execution were tested.
- No new runtime dependency was added. CI now installs already-declared Flask/Pillow prerequisites and maturin for its fresh-wheel and source-distribution checks.

Next PR: verified causal Chrome download receipts bound to Dext record/client identity before live `scribe`; then explicit privacy/effect approval and durable journals before external disclosure or mutation.

## Proposed commit and PR

Commit / PR title:

`feat(web): add scoped Python business functions for Dext`

PR base: `develop`.

Proposed PR body:

Dext sessions previously had no path to approved Python business functions through the Web agent. This adds one per-run `call_function` tool to the existing Rust registry, agent loop and controller, with strict AST contracts, independent business/native authorization, revision-bound single-use calls and a bounded private worker. Typed synthetic results appear in the existing chat; denials, stale source and uncertain classifications stop for operator review.

The inspected Dext `bank` and `scribe` proposal contracts are adapted behind an offline fake accounting provider. Production PDFs, real data disclosure and accounting mutations remain unavailable. Chrome download denial, dedicated-profile ownership, URL/tab scope, generic Web tools and the single native Dext skill are preserved.

Validation: Python 111 passed / 8 symlink-privilege skips; Rust 40 passed / 2 intentional ignores; Node 25 passed; Windows all-target check, UI typecheck/build, fresh ABI3 wheel installation/worker and sdist regression passed. Live Dext/Chrome and Linux execution remain unverified locally.

No commit or PR has been created. Stop here for explicit approval before Git publication.
