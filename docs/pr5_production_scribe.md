# PR5 production PDF Scribe

Implemented on `feat/dext-live-navigation-learning`; no commit, push or merge.
Existing uncommitted execution/UI/browser edits were retained. Production Scribe
is not tied to a particular customer or invoice: any active operator-registered
Dext client, including `synthetic: false`, can use an approved current PDF.

## Reused implementation

The supplied `Saccade-pilote (1).zip` was inspected for code only:

- `Saccade/agent_functions/comptable.py`: native PDF base64 file envelope,
  LiteLLM Gemini completion, key/model configuration, JSON output, bounded
  response/timeout, zero retries and truncation handling.
- `Saccade/agent_functions/platforms/dext/comptable_pdf.py`: target PDF analysis,
  invoice/credit-note/quote semantics and structured accounting validation.
- `Saccade/agent_functions/platforms/dext/_reference_data.py`: client-specific
  full Markdown selection, adapted to the current private registration layout.

The previously ported `invoice_validation.analysis` remains the validator.
No private accounting reference files were extracted, copied or transmitted.
No new OCR engine, agent loop, synthetic production provider or Dext writer was
introduced. LiteLLM receives the actual verified PDF bytes, not a prewritten
invoice result. Its external boundary is stubbed only in automated tests.

## Registry, client and document contract

The existing generic capability catalogue includes the packaged trusted
`dext.scribe_pdf` entry only for Dext. Its source revision includes the existing
trusted package fingerprint. Platform-local registrations cannot override it.
Legacy `dext.bank` and offline `dext.scribe` retain their contracts and tests.

The native `call_function` tool accepts:

```json
{
  "version": 1,
  "name": "dext.scribe_pdf",
  "arguments": {
    "document": "receipt:<current-download-receipt-id>",
    "client_id": "<active-registered-client>",
    "sens": "achat"
  }
}
```

The model cannot supply a filesystem path or switch the registered active
client. Client names are registry IDs, not hard-coded MPH/FRT values.
References are read fully and freshly from the selected client's private folder:

| Direction | File under `platforms/dext/data/<client>/` |
| --- | --- |
| `achat` | `comptable_achats.md` |
| `vente` | `comptable_ventes.md` |
| Bank | `comptable_banque.md`; never used by PDF Scribe |

There is no generic `comptable.md`. Reference reads retain existing size,
encoding, symlink/reparse/hard-link and client-directory safeguards. Missing or
invalid references fail before a provider call; they are not truncated or replaced.

New protected-download receipts include their retained native browser session,
tab and page binding. The production operation reobserves through the existing
native scanner before authorization and reissue. Approval binds current DOM
evidence, receipt/PDF digest, active-client registration revision, direction,
reference filename/revision, function revision, provider/model and conversation.
If the visible heading establishes a contradictory invoice direction, execution
is rejected. Unknown identity is not inferred from filename or hash.

The operator must inspect the current document and explicitly reply:
**Confirm document identity and approve Gemini disclosure**.
The presentation states that this confirms the document/client/direction/PDF
correspondence and permits sending this PDF and the FULL selected reference to
Google Gemini once. A general approval or learning Yes does not authorize it.
Changing the client, document, direction, references, registration, source code,
page or browser invalidates reuse. Older receipts without browser provenance
must be downloaded again through the protected transport; no data migration occurs.

## Worker, provider and proposal

The existing bounded child receives the consumed host decision and revalidates
its binding and local inputs. Credentials are read only after approval and sent
through a restricted child environment, never model-visible tool arguments.
Only Gemini configuration is added; other worker invocations retain the original
credential-free environment. Cancellation/job ownership and output limits remain.
The Scribe deadline is 100 seconds, with one 90-second Gemini request and no
automatic retry, fallback provider or new orchestrator. No model requests occur
while the operator is deciding.

Install the declared optional dependency in the application interpreter:
`python -m pip install -e ".[scribe]"`.
Use `GEMINI_API_KEY`, or the existing AutoCua Google API key setting. A project
`.env` Gemini key is supported when python-dotenv is available. Set
`COMPTABLE_LLM_MODEL` in the runtime environment to an approved `gemini/<model>`;
the default matches Pilote: `gemini/gemini-3.1-flash-lite`.

No provider callback or telemetry is enabled. Provider errors use enumerated
diagnostics, not exception messages containing documents, keys or URLs. Response
limits, exact fields, dates/currency, integer cents, balancing, direction/credit
note conventions and incomplete/complex invoice review checks apply. Results
include provider review reasons and a mandatory operator-review marker. Accounting
entries are never written, saved or posted to Dext by this function. Successful
proposals use the existing private local results UI and stay out of model results.

The browser retains download denial and profile/host ownership. Existing
same-origin download limitations still apply; arbitrary paths, cross-platform
receipts and unobserved resources are not substitutes for protected transport.
Ordinary navigation continues through the existing Generic Web controller.
Obsolete fallback messages requesting ordinary manual navigation were replaced
with focused tool/permission diagnostics; download failures expose only known
safe error codes. The specialized legacy Dext preview remains a preview.

## Validation and remaining acceptance

- Full rebuilt-artifact Python suite: **279 tests, 268 passed, 11 skipped**
  (Windows symlink privileges), zero failures/errors; 90.676 seconds.
- Seven new production tests cover real-client policy, active-client rejection,
  wrong direction, arbitrary paths, foreign platform/page, receipt integrity,
  reference/registration changes after consent, exact identity/disclosure phrase,
  full Markdown/multimodal completion, provider failure/truncation, invalid
  accounting, private proposal delivery and actual child-process missing-config
  reporting. Only synthetic data and stubbed external network responses are used.
- `cargo check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml`:
  passed. `cargo test --locked --offline --manifest-path AutoCua/web/Cargo.toml`:
  **53 passed, 2 ignored** (internal child helper and opt-in real Chrome).
- Existing bridge/operator/selection/composer JS suites: **49 passed**.
- UI typecheck/build passed; wheel and sdist rebuilt and inspected by four
  packaging tests, including production-module presence and exact source bytes.
- Stale execution tests were aligned with the preexisting uncommitted change
  that ordinary supervised navigation uses native tools without click whitelists.
  One-use/stale/foreign/presentation tests now exercise separately gated downloads;
  authorization, business isolation and accounting checks were retained.
- `git diff --check` still identifies five whitespace-only lines in preexisting
  uncommitted edits; no security or runtime failure is associated with them.
- No Linux Rust, real Chrome, real Dext invoice or external provider was run.
  The validation interpreter lacks LiteLLM, and this checkout contains no Dext
  client registration. This is a deployment/acceptance prerequisite, not a
  synthetic-only execution guard. No real-client data was sent externally.

Live acceptance is pending in the operator's configured application environment:
select any registered client and invoice, download using protected transport,
request `dext.scribe_pdf` for the correct direction, inspect/confirm the binding
and disclosure, and review the resulting accounting proposal. The supplied
MPH/NESPRESSO scenario is an example, not a hard-coded requirement.

## Files changed for this request

```text
AutoCua/saccade/business_process.py
AutoCua/saccade/business_worker.py
AutoCua/saccade/capabilities.py
AutoCua/saccade/operator_requests.py
AutoCua/saccade/platform_learning.py
AutoCua/saccade/scribe_pdf.py (new)
AutoCua/web/agent/main_driver/service.rs
AutoCua/web/controller/view.rs
AutoCua/ui/index.js (rebuilt from existing UI sources)
pyproject.toml
tests/test_packaging.py
tests/test_universal_execution.py
tests/test_scribe_pdf.py (new)
docs/pr5_production_scribe.md (new)
```

Other preexisting edits in `execution.py`, `browser.rs` and
`operator_review.tsx` were retained. No private file, registration, learning
history, other OS engine, index staging or Git history was changed.

Proposed commit: `feat(dext): add consent-bound Gemini PDF Scribe proposals`.
