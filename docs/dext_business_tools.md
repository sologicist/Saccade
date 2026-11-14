# Dext business functions (PR4)

PR4 adds a bounded, synthetic-only accounting proof to the existing Saccade Web
agent. It does not automate accounting entry, enable downloads, or authorize
browser clicks, input, scraping or scripts. Windows with visible dedicated Chrome
is the only protected live Dext runtime. Linux supports compilation and offline
contracts only.

## Architecture and authority

The existing `AutoCua/web/tool_registry/service.rs` remains the native LLM tool
registry. `LLMManager` builds per-run provider definitions in the existing OpenAI,
Anthropic, Gemini, Perplexity and chat-completions dialects. Static generic and
scrape registries never include `call_function`. Model selection, input limits,
normal response parsing and provider retry behavior are preserved.

The existing Rust main driver refreshes the catalogue immediately before a model
decision. Calls pass through its normal parser, notes handling, controller action
router and correlated history. The controller obtains a private typed permit from
the independent Python business gate, then checks native platform scope and live
browser observation. After execution the normal controller post-check runs again.
A redirect or lost observation replaces success with operator review. A business
permit grants no browser capability. `PlatformScope::validate_action` continues to
reject an ordinary JSON `call_function` without this separate gate.
The typed result is also sent through the existing chat text callback, explicitly
labelled synthetic, without adding another chat or UI component.
Business failures requiring review stop the existing loop with `waiting_operator`;
they cannot be automatically retried or followed by an unverified success claim.

Python implementations live in `AutoCua/saccade/business_functions/platforms/dext`.
They are not a Python replacement for the Rust registry. Shared catalogue,
signature, gate and worker plumbing lives directly under `AutoCua/saccade`.
There is no additional agent loop, driver, listener or HTTP service.

## Function and provider contracts

`call_function` has version 1, a registered name and an arguments object. Its
strict provider schema uses the closed union of function arguments; unused union
fields may be null. The server removes null union fields and validates the exact
individual signature. Unknown keys, modules, source overrides, permissions and
effects cannot be provided by the model.

```json
{
  "version": 1,
  "name": "dext.bank",
  "arguments": {
    "string": "SYNTHETIC TRANSFER",
    "client_id": "synthetic-pilot",
    "pdf": null,
    "sens": null
  }
}
```

`bank(string, client_id)` passes the exact nonblank label (1–1000 characters) and
the entire freshly read `comptable_banque.md` to the accounting provider boundary.
It returns exactly `{"compte": string_or_null}`. Accounts must contain 2–20
uppercase letters/digits and must not start with `512`. Null represents an
uncertain classification; it is not evidence of accounting correctness.
The native loop hands a null classification, an uncertain invoice, every credit
note and every quote back to the operator after displaying the typed result.
A quote needs no accounting entry and does not manufacture one.

The initial provider is explicitly a **fake**, selected with the separate
`COMPTABLE_LLM_MODEL=offline-synthetic-v1` setting. Its responses are trusted
operator-supplied synthetic fixtures, not an accounting matching algorithm.
It accepts the full current reference just as a real provider would, but makes
no network request. Any other accounting model is rejected with
`external_provider_consent_required`. No Gemini/LiteLLM dependency was added.
An eventual real provider must be classified as `external_effect`, obtain explicit
operator-controlled disclosure consent and client authorization, and satisfy a
future effect/approval design. Merely changing the model setting cannot enable it.

`scribe(pdf, client_id, sens)` retains `achat`/`vente` and the legacy analysis
shape: `date`, `type`, `ecriture`, `reference`, `description`, `journal`,
`total_ttc`, `total_tva`, `devise`, and `fournisseur` for purchases or `client`
for sales. Types are `facture`, `avoir`, `devis` or null. Lines use `compte`,
`role`, `debit_centimes`, `credit_centimes`. ISO dates, currency, bounded integer
centimes, single-sided lines, balance, VAT/base/party roles and invoice direction
are checked. Quotes, unknown documents, explicit review and complex/multi-rate
allocations produce empty entries and a null journal. Credit notes reverse sides.
Each client has exactly three reference files: `comptable_banque.md`,
`comptable_achats.md`, and `comptable_ventes.md`. There is no generic reference
file. Description remains null on this runtime path; the output schema is unchanged.

Production `scribe` always refuses unverified PDFs with
`verified_download_receipt_required` **before starting a worker**. The argument
is an opaque synthetic fixture ID, never a model-selected filesystem path.
Only trusted Python test callers can supply offline fixture receipts, scoped to
the current client and direction with an exact PDF digest and known critical
fixture facts. The normal Rust/UI entry never supplies such receipts. They are
not live download receipts and must not be represented as such.

## Source-specific compatibility decisions

The supplied sanitized `SACCADE_PR4_CODEX_HANDOFF (1).zip` was inspected in memory;
its reference manifest hashes matched. No archive or reference corpus was copied
into the repository. The Dext-specific functions, provider/PDF helpers, catalogue,
dispatch/worker pattern and selected legacy tests informed this implementation.
No legacy filesystem, dossier creation, browser orchestration or production
procedure was imported. The fictional reference aliases are not product tenants.

Intentional adaptations/tightening:

- `client_id` replaces the old code-based `sigle`; the registered active client
  is authoritative, and another registered client's ID is insufficient.
- Duplicate keys, nonfinite JSON and extra fields are rejected for both functions.
- The original remote accounting inference is represented by an injectable
  provider boundary; only the trusted offline fake is enabled in PR4.
- PDF fixtures are limited to 256 KiB and each of the three references to 2 MiB.
  Provider JSON is limited to 32,000 bytes, worker output to 64 KiB.
- Malformed rows are rejected even for quotes/review outputs. `512*` accounts
  are refused in invoice proposals too. Critical synthetic fixture mismatches
  fail explicitly rather than accepting a well-formed invented proposal.
- Worker execution has a 10-second deadline followed by bounded cleanup waits. No historical provider request,
  raw document, raw reference or exception text is persisted by this subsystem.

## Local configuration and privacy

Private references live only at `platforms/dext/data/<client_id>/`. This directory
and generated platform reports are ignored by Git and excluded from wheel/sdist.
The client registration is `platforms/dext/data/registration.json`, read only by
trusted host code. It is not a model argument, UI-supplied permission object or
production client allowlist embedded in source.

For an offline synthetic pilot, the operator can create this local file:

```json
{
  "schema_version": 1,
  "active_client": "synthetic-pilot",
  "clients": {
    "synthetic-pilot": {
      "synthetic": true,
      "bank_labels": ["SYNTHETIC TRANSFER", "SYNTHETIC UNKNOWN"],
      "bank_responses": {"SYNTHETIC TRANSFER": {"compte": "40100000"}}
    }
  }
}
```

Also create nonempty, entirely invented `comptable_banque.md`,
`comptable_achats.md` and `comptable_ventes.md` under
`platforms/dext/data/synthetic-pilot/`. The complete three-file bundle is validated
in the parent and worker before a business function executes. There is no production
fallback client or baked-in tenant. The active client binding is fixed when the
run is constructed; changing it requires a new run. Labels must match the
operator's registered strings exactly. Synthetic unknown labels return null.
Setting `synthetic` to false closes the privacy gate. Marking real data as
synthetic would be an operator configuration error, not a privacy mechanism.
Do not put actual labels, clients, documents or references in pilot configuration.

For explicit local directory initialization, three-file validation and real-client
metadata registration, see [dext_reference_onboarding.md](dext_reference_onboarding.md).
Registration is not real-record authorization or disclosure consent. The CLI never
imports archives or retags real data as synthetic.

Every call rereads current references, detects changes during reading and records
their digests in an in-memory receipt. Receipts contain a hashed client identity,
run/call identities and source/reference revisions, not raw reference text.
No receipt journal is written. Scoped raw conversation debug dumps and console
turn-content printing are disabled. The existing local chat still displays its
normal user-visible tool results; it must remain private and excluded from Git.

## Discovery, revisions and worker boundaries

Discovery parses UTF-8 AST without importing callable modules. Only two explicit
public functions in the installed Dext package can be registered. The signature
grammar supports bounded strings/numbers, booleans, literals, nullable values,
closed typed dictionaries (including optional fields) and bounded arrays.
Unsupported, dynamic or ambiguous annotations, defaults and variadic signatures
are refused. Docstrings and reference text grant no authority.

The fingerprint covers all Python/JSON files under `AutoCua/saccade`, package
markers and the package root. Business modules cannot import unfingerprinted
local packages, third-party packages or dynamic module targets. Registration and
validated session metadata are included in the per-turn revision. Helper or
policy changes invalidate a selected call. The parent validates again before
launching; the fresh worker independently reconstructs and validates the selection
before importing the fixed approved module and invoking exactly one function.
Tickets are internal, per-run and single-use; replayed model text cannot reuse one.

The worker receives a bounded JSON request over private inherited stdin/stdout.
There is no public endpoint. `-I -B`, a fixed installed package root, a minimal
environment without provider keys, output/error limits and a total deadline reduce
ambient access. Stderr and exception text are never returned. On Windows a
kill-on-close job is assigned before any request is sent, with one active process
permitted; failure to establish it prevents execution. Timeout, cancellation and
KeyboardInterrupt clean up the worker. Source/editable and wheel Python runtimes
are supported; compiled desktop executables fail closed with
`worker_python_runtime_required` rather than launching a second application.

These controls are **not a security sandbox**. Approved Python retains the host
user's filesystem and network permissions. Installed code, local registration,
the interpreter and stdlib are trusted. A privileged concurrent writer can still
race path checks or module import after fingerprinting; metadata/read checks and
fresh-process validation reduce, but do not eliminate, TOCTOU. Deploy from a
trusted installation protected against concurrent modification. Future effectful
functions remain denied; no uncertain external operation is automatically retried.
The child uses source-only import loaders for the installed Saccade namespace,
so an existing unchecked/stale `.pyc` cannot substitute different executed code
for a fingerprinted source file. A dedicated regression poisons bytecode in an
isolated synthetic installation and verifies that the source still executes.

## Validation and packaging

Run from the repository root with Python 3.10+ (3.11+ preferred), Node/npm and the
repository-pinned Rust toolchain. Flask and Pillow enable the existing UI route
contracts. Tests generate synthetic references/PDF bytes under ignored `.cache`.

```powershell
python -m unittest discover -s tests -t . -q
$env:SACCADE_TEST_PYTHON = (Get-Command python).Source
cargo test --locked --manifest-path AutoCua/web/Cargo.toml
node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs AutoCua/ui/platform_session/selection.test.mjs
npm.cmd --prefix AutoCua/ui run typecheck
npm.cmd --prefix AutoCua/ui run build
cargo build --locked --manifest-path AutoCua/web/Cargo.toml
$env:SACCADE_TEST_NATIVE = (Resolve-Path AutoCua/web/target/debug/agent_native.dll).Path
python -m unittest tests.test_platform_session_native -v
maturin build --locked --profile dev --out .cache/pr4-wheels
maturin sdist --out .cache/pr4-sdist
$env:SACCADE_TEST_WHEEL = (Get-ChildItem .cache/pr4-wheels/*.whl | Select-Object -First 1).FullName
$env:SACCADE_TEST_SDIST = (Get-ChildItem .cache/pr4-sdist/*.tar.gz | Select-Object -First 1).FullName
python -m unittest tests.test_packaging -v
git diff --check
```

The new Rust test exercises both the action path and the actual
`AgentService.process_request` loop with the LLM manager, provider dialect,
normalizer, controller, native scope policy, Python gate, real subprocess worker,
chat callback and tool-call-ID pairing. The model, Chrome scan/observations,
compression service and loop-test lease handle are synthetic; existing native
constructor tests separately verify real profile ownership. The Chrome seam is
`cfg(test)` only and absent from shipping builds. This proves software execution
and fail-closed transitions, not live Dext authentication or the operation of a
real Chrome download policy.

The wheel test extracts a fresh installation in an isolated interpreter, discovers
the installed Python catalogue/metadata and imports the native extension without
the source checkout. CI runs offline business tests, the Windows native turn,
existing session tests, fresh wheel/sdist contracts and Linux `cargo check --all-targets`.
CI does not call Dext, a cloud model or real customer data.

## Manual supervised pilot (not an automated accounting test)

1. Prepare only the synthetic local registration/reference described above.
2. Choose Web use → Dext → Supervised → Quality with a supported vision model.
   Confirm visible Chrome uses `saccade-dext`, with its existing profile lease.
3. Authenticate manually on an authorized Dext page. Do not open real documents,
   accounts or transaction labels for this proof.
4. If sign-in redirects outside the configured hosts, stop for operator review.
   Do not expand hosts or guess SSO permissions. Complete sign-in manually in
   that same dedicated profile after the session is released, return to an
   authorized page, and start a new supervised run. Report an incompatible flow
   if the observer cannot resume safely; never clear a sticky violation in place.
5. Supply the exact synthetic label and registered synthetic client in the
   existing chat. Confirm one typed `compte` result; then test an unknown label.
6. Confirm an unverified `scribe` call is refused and generic/new-platform chats
   do not receive Dext tools. Verify browser navigation and downloads remain
   protected; no accounting entry is created or saved.

This manual smoke test requires operator participation and has not been replaced
by the deterministic fixture. Menus, record navigation, document reading,
downloads, live PDF analysis and accounting entry remain unsupported in PR4.
The next PR must establish causal download receipts with Dext record/client
binding before live `scribe`. Approval and an effect journal must precede any
mutation or external-disclosure enablement.
