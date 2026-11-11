# Web platform sessions

This implementation uses the existing AutoCua chat, conversation storage,
launcher, Web Rust loop, scanner, controller and authenticated Chrome extension.
It adds no second agent loop or browser driver. Business tools, accounting
approvals, effect journals, PDF processing and learning are outside this slice.

## Operator workflow

1. Open a new chat and select **Web use**.
2. Choose a platform from **Platform**. The backend supplies the registered list;
   **Generic AutoCua** keeps ordinary Web use available.
3. Keep **Supervised**, **Quality** and a registered image-capable model for the
   initial pilot. **Auto** requires a separate explicit selection. Both modes
   currently permit observation and in-scope navigation only.
4. Start a request such as "Observe the login page and describe what is visible."
   Dext opens `https://app.dext.com/login` in visible Chrome using the dedicated
   `saccade-dext` profile. An empty native Dext procedure is a valid starting state.
5. Complete sign-in manually in Chrome. Passwords and MFA codes stay out of chat.
   Unexpected identity-provider redirects stop the agent for operator review.
6. Reopen the chat to restore its platform and execution mode. Use a new chat to
   change either. Provider/model selection and conversation history remain intact.

There is no accounting action approval UI in this slice. Click, input, Enter,
keyboard, vault fill, scroll, dialog answers, browser scripts, scrape execution,
history navigation, tab closure and downloads are refused for scoped runs in
both execution modes. Native run-local bookkeeping remains available. Complete
interactive login manually rather than trying to authorize it through model text.

## Context and profile ownership

`GET /api/platforms` uses the validated platform registry. `POST /api/start-agent`
accepts `platform_id` and, for a selected platform, `execution_mode`. Omitting the
platform on a resumed chat restores its saved binding; an explicit incompatible
selection returns a conflict. Unknown IDs and unsupported settings fail before
agent creation. Client-supplied hosts or start URLs cannot define the scope.

The versioned context contains the platform ID, execution mode, dedicated Chrome
profile, allowed hosts, start URL, step limit and a SHA-256 revision of technical
configuration. It is persisted as `platform_session.json` beside the existing
conversation history. Binding markers in the index and saved conversation prevent
a missing context file from silently downgrading the chat to generic Web use.
Invalid, missing or changed saved scope requires operator review and a new chat.
An explicit generic binding is distinct from an unbound new conversation.

UI and terminal launches acquire a descriptor-backed profile lease before
creating the native agent. Rust validates borrowed ownership or acquires its own
lease when called directly. The lease lasts through teardown and is released on
errors, stop and process death. A stale lock file or clock expiry never grants
ownership. Another run for the same profile returns `409 busy`; a still-finishing
UI run also blocks replacement of the UI's active run state. Other conversations
can be read while a run owns Chrome. Lock files live under the local data root,
and contain no credentials or client data.
The legacy parallel Web helper, which shares one profile among several agents,
is rejected before Chrome or children launch. Generic single-run Web behavior
remains available. This explicit compatibility restriction follows the one-active-
run-per-profile rule; no replacement parallel infrastructure is introduced.

## Native execution boundary

The PyO3 entry revalidates the context against installed Python metadata before
model/browser startup. Rust decodes the versioned contract again and keeps the
scope separate from model output. Scoped runs require visible Chrome, Quality,
an explicitly image-capable registered model, and their dedicated profile.
Custom debugging ports and parallel scoped runs are refused.
Scoped sessions also stage their authenticated extension bridge separately
inside the dedicated Chrome profile. A personal-profile extension cannot dial
the scoped run by reading the generic bridge's shared configuration.

The native controller checks every action before the existing handler, checks
live browser state again after execution and settling, and preserves one result
per tool-call ID when a batch stops. The scanner checks before returning page
observations. An out-of-scope or uncertain observation is sticky: an allowed URL
seen later cannot clear it. The run ends with `waiting_operator` and the reason
is saved in the existing conversation system; this is an operator handoff, not a
new structured `ask_operator` or approval workflow.

Only parsed HTTPS URLs on exact configured hosts and default port 443 are
eligible. Credentials, hostname suffix tricks, wildcard/subdomain inference,
`file:`, `javascript:`, `data:`, `blob:` and arbitrary browser-internal URLs are
denied. Direct navigation is validated before dispatch; tab switching resolves
the actual stable tab identity and validates its live URL. Pending URLs, other
profile tabs and popups are part of the observation. Known untouched startup
blank tabs are non-actionable exceptions; unexpected new internal/blank tabs
require review.

The existing extension supplies a bounded, per-run navigation event queue on its
authenticated bridge. This catches a cross-host redirect even if the final page
has already returned to an authorized host. Missing observations, changed run
identifiers, queue overflow, debugger detachment or transport loss stop the run.
Page download denial is established before agent navigation. Download attempts
trigger cancellation and review without reading filenames, file contents or PDFs.
Generic extension lines retain their existing behavior. Automatic browser
recovery and automatic dialog acceptance are disabled for scoped sessions.

Native domain selection remains URL-based through `skills.json`; `dext.md` stays
the sole Dext procedure. A recognized domain does not grant business tools,
customer-reference access or permission to mutate records.

## Security limits

- This is an agent execution boundary, not a browser network firewall. A page,
  manual operator action or redirect may issue a network request or execute site
  JavaScript before observation catches it. Further agent actions are stopped;
  completed remote effects cannot be undone by this policy.
- Host scope covers top-level documents and tabs. It does not allowlist all
  child-frame or subresource traffic; neither grants additional tool rights.
- Same-host HTTPS navigation does not prove that the remote server implements
  side-effect-free GET endpoints. Scope membership never grants accounting rights.
- Download denial/cancellation is best effort at Chrome's boundary. A transfer
  may begin before cancellation; no verified receipt or document correlation is
  implemented here.
- Profile leases coordinate cooperative Saccade entry points. They do not stop
  a person or unrelated program from controlling Chrome. Manual changes are
  re-observed before the agent proceeds.
- Teardown removes the run observer and releases browser ownership before the
  profile lease. Unverified download-policy restoration is reported for operator
  review; the dedicated profile may require a manual browser restart.
- The local operator controls configuration and procedure files. These checks
  do not sandbox hostile concurrent filesystem modification or a compromised
  Chrome extension/browser. No real tenant or accounting write is part of tests.

## Verification and manual review

Run from the repository root. Keep test temporary files inside the repository:

```powershell
New-Item -ItemType Directory -Force .cache/platform-session/tmp | Out-Null
$env:TEMP = (Resolve-Path .cache/platform-session/tmp).Path
$env:TMP = $env:TEMP
# Optional artifact checks use a freshly built wheel and its actual extension.
maturin build --locked --interpreter (py -3.11 -c "import sys; print(sys.executable)") --out .cache/platform-session/wheels
$env:SACCADE_TEST_WHEEL = (Get-ChildItem .cache/platform-session/wheels/*.whl | Select-Object -First 1).FullName
py -3.11 -m zipfile -e $env:SACCADE_TEST_WHEEL .cache/platform-session/wheel-extracted
$env:SACCADE_TEST_NATIVE = (Resolve-Path .cache/platform-session/wheel-extracted/AutoCua/web/agent_native.pyd).Path
py -3.11 -m unittest discover -s tests -t . -v
cargo check --locked --manifest-path AutoCua/web/Cargo.toml
cargo test --locked --manifest-path AutoCua/web/Cargo.toml
node --test AutoCua/ui/platform_session/selection.test.mjs
node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs
npm.cmd --prefix AutoCua/ui run typecheck
npm.cmd --prefix AutoCua/ui run build -- --outDir ../.cache/review-ui-build
git diff --check
```

Use the official Python 3.11 executable as `PYO3_PYTHON` when needed on Windows.
The existing shipping UI loads tracked `AutoCua/ui/index.js`; regenerate it from
the verified build when the React source changes. Node tests use synthetic Chrome
events, and Python route tests replace the model/native agent with a synthetic
runner. A real-browser pilot remains an explicit manual verification step.
The native-entry artifact tests also invoke the real PyO3 constructor in isolated
processes, failing deliberately at model initialization before Chrome can start.
They verify trusted-context rejection and owned/borrowed lease cleanup. Without
`SACCADE_TEST_NATIVE`, these six tests report an explicit skip.

In a dedicated test profile, verify the selector, its saved restore, the default
Supervised mode, the Quality/model rejection messages and a second-run busy
response. Manually follow an unexpected login redirect: the agent must stop and
retain the handoff reason. Close or return unauthorized pages manually before
retrying after review; do not expand hosts based on an LLM suggestion. Never use
a real customer record to demonstrate browser mutations in this phase.
