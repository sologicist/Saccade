# Dext Auto Lite implementation report

## Branch and baseline

Implementation branch: feat/dext-auto-lite.
Base: 91a2f4d10cc72666dabcd95dcc80bb67db15da9e (origin/develop, merged PR4).
The starting tree was clean and already on this branch. No checkout, pull,
reset, stash, merge, cherry-pick, commit, push or PR creation was performed.
No PR5 code, browser handoff, operator broker, navigation-learning overlays,
download permits or protected receipt framework was imported.

## One Web engine, automatic resources

The existing native scanner, controller, action dispatcher, provider loop,
conversation service and bounded business worker remain the execution path.
The Platform/Generic/Dext and Supervised/Auto controls, state, events, payload
construction and CSS have been removed. The normal Web/Computer/Mobile modes
remain. index.js is generated with Vite, not edited by hand.

Old conversation bindings remain on disk and readable for compatibility but
are not used to configure a new Web run. Missing/corrupt obsolete selection
metadata cannot prevent reading history or resuming generic Web. No destructive
conversation migration is performed. Obsolete request fields cannot select a
platform or force a dedicated profile.

Installed platform identity comes only from the scanner's observed HTTPS URL.
The lookup parses URL/hostname/port, rejects credentials and lookalikes, and
requires a unique exact hostname in installed platform configurations. It does
not inspect prompts, titles, model names or frontend selection state.

The existing native follow_url/domain_block mechanism selects domain knowledge.
Dext's guide is populated; the Google Sheets mapping and guide are preserved.
The controller refreshes business declarations before model decisions and scans
again before dispatch. Leaving a matching website disables its functions; stale
calls cannot execute. Returning restores declarations. Existing set_business_tool
caches unchanged definitions and updates normal/dialog providers together.

The generic browser receives no automatically imposed PlatformScope, Dext profile,
Dext step limit or single-site navigation restriction. At scans, normal shared
Web runs may follow another active tab already owned by the same agent. They
never take over an unowned human tab, a competing agent's tab, a pinned parallel
tab or a scoped session. Scanned tab identity is returned to the native scanner
so subsequent actions target the page actually observed. Navigating an existing
controlled tab and switching through existing tab tools also update detection.

PlatformScope::validate_action and the bridge whitelist apply only to explicitly
scoped legacy callers. URL detection never constructs that scope. The original
Web click, input, scroll, keyboard, tab, script, scrape, dialog and download paths
remain available on Dext, with their ordinary geometry, script and ownership
checks. There is no extra platform approval or download approval panel.

Only installed trusted callables are available: dext.bank and dext.scribe.
An unrelated registered platform can be identified and load its domain skill
without obtaining Dext functions. Additional business implementations still need
their own explicit trusted registration; this is not a new plugin framework.

## Downloads and actual filesystem paths

The existing native click tool clicks the observed Download control. Anonymous
buttons with the observed download class get a descriptive label from the normal
scanner. No PDF.js, MAIN-world script, iframe resource extraction, guessed URL,
fetch, Blob adapter, new browser, download manager or interception layer is used.

For a recognized download click, the existing bridge reads Chrome's Downloads
history for up to eight seconds after the click. It accepts one newly started,
completed, existing item with a matching page referrer. Multiple items,
interruption, a foreign/unknown referrer or missing completion produce explicit
non-success download metadata. A successful click alone never establishes a
successful download. The observation does not change Chrome settings or policy.

Chrome's absolute filename is consumed privately by the existing controller and
business run. Only its basename is returned to the model. The trusted host
verifies the PDF and can use the actual browser-confirmed parent folder, which
supports a nondefault Chrome destination. Non-PDF browser downloads retain their
normal result and are not treated as Scribe inputs.

For an exact filename supplied through chat/tool output, the local helper uses
Windows SHGetKnownFolderPath(FOLDERID_Downloads), or the operator's absolute
SACCADE_DOWNLOADS_DIR override. It does not use the project working directory,
search unrelated directories, invent collision suffixes or select a similarly
named file. Spaces, accents, Unicode and Chrome's exact (1) suffix are preserved.

The host rejects traversal, unexpected path components, paths outside the trusted
folder, missing/nonregular/reparse files, .crdownload/.part files, stale files,
changed files and PDFs over 8 MiB. It reads stable actual bytes and checks %PDF-
and the EOF marker. This is not a full local PDF parser; Gemini must actually
parse the document, and failures cannot return a fabricated proposal. The worker
rechecks the file and its host-observed SHA-256 before analysis. A failed newer
file verification invalidates the previous current-file hint.

Freshness starts when the business run is activated on Dext and is reset to the
trusted native timestamp of each new Download click. A failed or unconfirmed
new click cannot silently reuse the previous PDF. Older files are not
automatically trusted on a later run or after reactivation. Download again through
the existing browser if a stale file has no current evidence. The simple lookup
is intentionally not a durable download-history/receipt system.

No PDF copy into platform data or new receipt ID is needed. Files remain at the
actual Chrome/Windows Downloads location. The model may supply the exact reported
filename as a lookup key, but the installed scribe callable receives the resolved
absolute path. The path is not accepted as arbitrary filesystem authority.

## Scribe, clients and private references

Production BusinessRun defaults to the real file-based mode. The existing worker
and installed Dext function directory are retained. Production tickets declare
the provider disclosure effect; explicit offline tests retain compute-only tickets. Explicit automatic=False and
explicit offline fixtures remain available to tests; normal Web runs do not use
synthetic invoice responses, even for a synthetic-labelled registration.

registration.json supplies an explicit active_client. The model cannot select
another registered client or redirect its reference root. Real synthetic:false
registrations are supported, including a minimal client policy with that flag.
Only these reference types are allowed, freshly read in full:

- achat: platforms/dext/data/<client>/comptable_achats.md
- vente: platforms/dext/data/<client>/comptable_ventes.md
- banque: platforms/dext/data/<client>/comptable_banque.md

There is no generic comptable.md. Bank rules are not used for invoices and client
rules are not merged. Existing private registrations/references were not read,
modified, copied or migrated during development. platforms/*/data remains ignored
by Git and excluded from wheel/sdist.

Scribe sends actual PDF bytes as an inline application/pdf part and the complete
selected Markdown to Google GenAI. The existing AutoCua Google model selection
and credentials are passed privately to the worker/provider. An offline model is
never used in production. The existing invoice validator checks the returned JSON,
amounts, dates, accounts and balanced entries. Results are accounting proposals
for review, never Dext writes, saves or posts. Bank also uses the full bank
reference in production and validates compte/null results.

Client registration is trusted operator configuration, not semantic proof of PDF
ownership. Operators must ensure it matches the Dext client shown in the live UI.
The skill instructs the agent to stop on disagreement or uncertainty. No filename
or timestamp is represented as proof of the invoice's accounting identity.

## Existing AutoCua provider settings

An explicit chat instruction to analyze the identified invoice with Scribe
authorizes that analysis, including the PDF and selected full client reference
sent to Gemini. No additional accounting consent setting, prompt, dialog or
approval is required. This does not authorize unrelated documents or Dext writes.

When the Web agent uses Google, Scribe reuses that run's selected Gemini model
and runtime Google key. Otherwise it uses the existing saved Google selection
when available, or the default in AutoCua's Google MODEL_MAPPINGS. The existing
llm_manager._key loader resolves GOOGLE_API_KEY from runtime settings, environment
or the same API-key file used by the app. There is no second credential field,
store, model table or accounting configuration. Unknown model aliases, missing
keys or unavailable dependencies fail explicitly; they never produce fixture
results. The worker builds the same Google provider through build_provider,
including AutoCua's HTTP/TLS configuration.

Only the resolved Google key is added to the bounded child's otherwise filtered
environment. It is not placed in tool arguments, tickets, JSON requests or tool
results. Dotenv loading is disabled in the isolated child so importing the shared
provider cannot reload unrelated credentials from a project .env. Files,
references and provider exceptions are not placed in public
diagnostic messages. Function results use the existing private conversation/tool
result path; they may therefore enter the selected browser model's conversation.
Accounting function responses are not publicly printed as diagnostic payloads.

## Gemini declarations

Gemini-specific recursive normalization removes non-string enum values without
changing integer types, canonical schemas or other provider formats. String enums
remain. Native version == 1 validation is unchanged. Regression coverage checks
nested schemas and actual Google SDK FunctionDeclaration validation, including
rejection of the original numeric-enum schema. Google GenAI 3.3.0 was installed
only in the isolated validation cache; no live provider request was made.

## Validation boundaries and remaining limitations

Automated tests use temporary synthetic Downloads/client directories, fake Chrome
API responses, an authenticated local WebSocket extension peer and stubbed Gemini
responses. They exercise the native controller's
automatic activation/deactivation/stale-call checks, native click dispatch plus
Chrome metadata reading, actual local file reads, full references, SHA-256 file
change rejection, strict invoice validation, shared Google settings/key loading and the
existing real isolated Windows subprocess. The child success test has a disposable
SDK protocol stub; separate tests validate the real installed SDK types/envelope.
None of these tests prove successful download or invoice extraction on live Dext.

Manual Windows testing performed: the OS Known Folder API returned an absolute
Downloads path, without listing/reading customer files. No real Chrome session,
Dext login, client invoice, accounting reference or Gemini key was used.

Known production limits:

- Save/Print dialogs are not automated or suppressed. If Chrome does not create a
  completed download, the tool reports unconfirmed; no successful Scribe result
  can be inferred from a click.
- Completion must occur within the observation window and retain an exact page
  referrer. Slow downloads, referrer-policy differences or multiple simultaneous
  downloads fail clearly and need real-browser observation before adaptation.
- Files from earlier runs are rejected as stale rather than guessed/reused.
- No semantic client-owner identification is inferred from a basename or hash.
- A frozen launcher must set SACCADE_WORKER_PYTHON to a trusted absolute Python
  interpreter path with the declared dependencies, and ship the existing verified
  business Python source bundle. The same bounded worker, isolation and Job limits
  are used; no model argument can choose the interpreter. Missing/invalid runtime
  configuration fails clearly. The configured-runtime path was tested with a real
  child process under a simulated frozen host; an actual Nuitka installer was not
  run. CPython development and wheel execution were tested.
- Vertex-only authentication is not implemented for the accounting call; use the
  Google API-key configuration supported above.
- Linux Rust, a standalone installer and live Windows Chrome/Dext/Gemini acceptance
  were not run. Production success is not claimed from green synthetic tests.

## Minimal manual acceptance

1. Use a CPython source or wheel installation with declared Google dependencies.
   Rebuild/restart Saccade so the current Rust extension and bridge resources load.
2. Keep the real client registration and exactly three Markdown references local.
   Confirm active_client matches the client observed in Dext.
3. Choose normal Web and Gemini. Confirm there are no platform/execution selectors.
4. Navigate the controlled browser to Dext. Observe the Dext guide and call_function
   availability without manually selecting a platform or forcing a Dext profile.
5. Open a permitted test invoice under that active client. Click the live observed
   Download control through the existing Web tool. Do not automate a system dialog.
6. Check the returned exact completed filename. Confirm the trusted host locates
   and reads that file, and scribe receives its absolute path and correct sens.
7. Explicitly ask Scribe to analyze that invoice. The existing Google settings
   suffice; no additional consent or model setting is required. Verify the Gemini
   call returns a validated proposal using the full
   selected reference. Review it; there is no automatic accounting write.
8. Navigate away and back (also switch owned tabs) and verify resources are revoked
   and restored. Preserve the same conversation and generic browser ownership.

## Final local test results

- Python: 134 discovered, 126 passed, eight skipped, zero failures/errors;
  25.970 seconds. All skips require unavailable Windows symlink privileges.
  Includes the four fresh wheel/sdist packaging tests and compiled native-entry
  tests, plus 15 Auto Lite cases. The real child test covers Unicode filenames
  and non-Latin proposal text with the existing JSON pipe codec.
- Rust all-target check passed. Native tests: 42 passed, two ignored, zero
  failures; 4.01 seconds. The ignored cases are the internal pipe helper and
  opt-in real Chrome launch. Google SDK 3.3.0 declaration checks executed locally.
- JavaScript: 25 passed, zero failed. Includes ownership-preserving tab selection,
  native input dispatch, completed/canceled/ambiguous/old/absent Chrome evidence,
  no download-policy relaxation and removal of manual selector wiring.
- UI TypeScript check and Vite production build passed; generated index.js rebuilt.
- The native URL-activation integration test routes click, input, keyboard,
  scroll, navigation and download through ControllerView and the authenticated
  WebSocket bridge. The ordinary navigation click does not request download
  observation. The completed synthetic PDF reaches the private path handler;
  original missing-element and Chrome Web Store checks still refuse invalid
  actions. Script/dialog/tab requests exercise the native bridge policy boundary.
- Credential tests cover runtime Google settings, the existing saved Google key
  loader, saved/default model selection, rejection of unregistered aliases,
  separation from other providers, and absence of keys from tool/request JSON.
  The real isolated child verifies dotenv is disabled and unrelated API keys
  are absent. All provider responses are synthetic test responses.
- Development wheel and source distribution built successfully. Installed-path,
  module/policy/skill/config inclusion and private-data exclusion checks passed.
- git diff --check passed (line-ending conversion notices only).
- No live Chrome/Dext/Gemini acceptance, standalone installer or Linux Rust run
  was performed. See the explicit boundaries above; synthetic success is not
  described as production acceptance.

Commands and local artifacts:

```text
cargo check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml
cargo test --locked --offline --manifest-path AutoCua/web/Cargo.toml
node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs AutoCua/ui/platform_session/auto_lite.test.mjs
npm.cmd --prefix AutoCua/ui run check
.cache/pr1-tools/python/python.exe .cache/auto_lite_all.py
.cache/auto-lite-wheels/saccade-0.1.9-cp310-abi3-win_amd64.whl
.cache/auto-lite-sdist/saccade-0.1.9.tar.gz
```

The Python runner uses cached test dependencies and supplies fresh wheel/sdist/
native-library paths to the existing tests. Build logs and the isolated SDK are
under ignored .cache/. No application dependency was installed globally.

## Exact source changes

### Modified (32)

```text
.github/workflows/ci.yml
AutoCua/agent_conversation/service.py
AutoCua/default_skills/web/domain_skill/dext.md
AutoCua/saccade/business_catalogue.py
AutoCua/saccade/business_functions/platforms/dext/functions.py
AutoCua/saccade/business_functions/platforms/dext/policy.json
AutoCua/saccade/business_functions/platforms/dext/runtime.py
AutoCua/saccade/business_process.py
AutoCua/saccade/business_run.py
AutoCua/saccade/business_worker.py
AutoCua/ui/chat/chat.js
AutoCua/ui/chat_input/chat_input.css
AutoCua/ui/chat_input/chat_input.js
AutoCua/ui/chat_input/chat_input.tsx
AutoCua/ui/index.js
AutoCua/ui/service.py
AutoCua/web/agent/main_driver/service.rs
AutoCua/web/browser/AutoCuaBridge/background.js
AutoCua/web/browser/AutoCuaBridge/element.js
AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs
AutoCua/web/browser/AutoCuaBridge/tools.js
AutoCua/web/browser/browser.rs
AutoCua/web/browser/bridge.rs
AutoCua/web/controller/click/service.rs
AutoCua/web/controller/view.rs
AutoCua/web/platform_scope.rs
AutoCua/web/tool_registry/business.rs
AutoCua/web/tool_registry/service.rs
tests/business_fixtures.py
tests/test_business_tools.py
tests/test_packaging.py
tests/test_platform_sessions.py
```

### Added (6)

```text
AutoCua/saccade/accounting_provider.py
AutoCua/saccade/automatic_platform.py
AutoCua/saccade/downloaded_pdf.py
AutoCua/ui/platform_session/auto_lite.test.mjs
docs/dext_auto_lite.md
tests/test_auto_lite.py
```

### Removed (3)

```text
AutoCua/ui/platform_session/platform_session.tsx
AutoCua/ui/platform_session/selection.test.mjs
AutoCua/ui/platform_session/selection.ts
```

No client registration/reference, API-key file, Chrome profile or platform engine outside Web was modified. Proposed commit message (not committed): `fix(web): preserve generic Dext actions and reuse AutoCua Gemini settings`.
