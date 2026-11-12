# Dext operator review and navigation learning (PR5)

## Delivered boundary

This change delivers local operator review, versioned generic navigation guidance,
native navigation **previews**, and stronger reference revision checks. It is a
partial PR5 implementation. The requested real Dext navigation/accounting journey
is **not complete**. No live Dext, Chrome launch, private accounting corpus, real
PDF or external model request was used during implementation.

| Capability | Evidence/status |
| --- | --- |
| Existing native scope/profile/download DENY | TESTED SYNTHETICALLY; prior security code retained |
| Navigation request, independent UI decision and native handoff | TESTED SYNTHETICALLY through the real Rust agent loop |
| Actual Dext menu/record gesture and postcondition | BLOCKED: verified Dext semantic/frame/record adapter absent |
| Local procedure candidate, exact review, publication, pin and rollback | TESTED SYNTHETICALLY |
| Local chat correction to a proposed generic procedure | TESTED SYNTHETICALLY; conservative French/English compiler, exact separate approval |
| Operator local dossier claim | TESTED SYNTHETICALLY; explicitly unverified for business execution |
| Verified real Dext dossier/record binding | BLOCKED: no stable observed identity adapter |
| Existing offline synthetic bank and invoice worker | TESTED SYNTHETICALLY, including real subprocess/native entry |
| Real bank label collection and provider classification | BLOCKED: verified row binding and disclosure boundary absent |
| Causal live PDF receipt / live scribe | BLOCKED; native download DENY preserved |
| Real Gemini provider and per-call live disclosure consent | BLOCKED; no network adapter or grant is issued |
| Dext accounting form entry/save | BLOCKED; future write-effect phase |
| Any live browser/Dext compatibility claim | NOT TESTED; no capability is VERIFIED LIVE |

The supplied handoff explicitly permits safe scaffolding when Dext semantics
cannot be established and requires missing live capabilities to remain closed.
Nothing here substitutes synthetic results for real browser evidence.

## Existing architecture and integration

The Rust Web agent remains the sole loop. The existing controller remains the
sole action router. Existing authenticated extension transport, Windows CDP pipe,
exact-host scope, sticky observer failures, dedicated profile lease, worker and
`call_function` policy remain in place. No new driver, service, server, agent,
runtime dependency, browser permission or credential lookup was added.

The existing UI creates a `DextRunControl` only for a supervised Dext run, passes
the trusted Python instance to the native constructor, and closes it on stop,
new-chat, failure or run completion. Generic/Auto sessions cannot create a
navigation tool through model JSON. `validate_control` checks the exact host type
and installed context. The native constructor retains its independent platform
and lease checks.

The per-run registry appends `dext_navigation` alongside the PR4 business tool in
the existing provider constructors (all five dialects). The parser accepts only
version, a closed route name and a positive target ID. It preserves call IDs,
notes-first behavior, batch results and done-alone rules. This tool is absent
from static generic, fast and scrape registries.

The controller obtains a new native scope observation, including existing
download-denial verification, and resolves a preview from its current element
map. The native stamp binds observer, tab, profile and configuration revision.
The preview records the target digest, label/role/geometry, observation ID, run,
policy and pinned procedure revision, intended check and 60-second deadline.
An independently authenticated UI decision consumes the exact proposal once.
The existing tool call waits on a Python Event, releasing the GIL and observing
stop. Rejection, expiry, stale source or approval all return a correlated result;
**approval still returns `verified_dext_navigation_adapter_required` without
dispatching input**. The loop hands control to the operator and does not retry.
The ordinary controller post-scope check still runs.

This stamp does **not** prove frame identity, a fresh Dext DOM, target semantics,
workspace, record identity or transition. Its observation ID is a host preview
identity, not a fabricated Dext record ID. No coordinate click or script fallback
exists on this path. Even model-supplied same-host `new_tab`/`update_tab` URLs are
now denied for Dext: a hostname is insufficient to establish a safe action. The
fixed installed bootstrap URL is unaffected; generic Web behavior is unchanged.

## Operator channel and learning

Open **Dext operator review** in the existing platform selector. It is a bounded
scrolling panel that remains accessible while the composer is active. All DOM
labels and diffs are React text nodes, never HTML instructions. The operator may
enable local correction mode and type recognized French/English navigation
sentences in the existing chat. The message is intercepted before model execution
or general task persistence and compiled to generic steps (`workspace`, `invoices`,
`bank`, `record`, `review`). Unknown details, private values, negations and effectful
instructions are rejected, not silently discarded. Raw chat, website, PDF, model
or tool prose never enters reusable procedure content. Predefined route selection
remains available. The resulting candidate still needs separate exact approval.

`/api/dext/control` uses the existing app's token and exact local Host/Origin
guard. POST additionally requires an explicit exact local Origin, the current
chat ID and an in-memory per-run review token. The latter is never placed in
model inputs/results, conversation history, SOP files or logs. Requests use the
strict duplicate-key rejecting JSON codec with an 8 KiB limit. The body has a
closed event schema and responses use `Cache-Control: no-store`; ordinary chat
text such as "yes" grants nothing.

Teaching creates an old/new/diff preview with rationale, redacted evidence status,
proposal ID, base revision/generation and candidate digest. Approval and refusal
are distinct UI events bound to all three identities. Publication changes the
active pointer only after independent exact approval. A stale candidate cannot
overwrite another publication; an explicit refusal can discard a stale candidate
without changing the active revision.

The intentionally closed output grammar cannot contain private names, labels,
invoice numbers, URLs, selectors, session element IDs, HTML/JavaScript, secrets,
network instructions, permissions or arbitrary Markdown. It has at most eight
steps and emits fixed generic Markdown. This is a safe first learning vocabulary,
not a claim to have learned working Dext selectors. Approved text is guidance
and cannot authorize any browser/business operation.

The native domain-skill loader still selects `dext.md` by actual URL. Only when
that exact native domain is active does the same existing prompt path append the
approved pinned overlay in a separate guidance block. The shipping baseline may
be empty. Runtime code never writes it. A native-loop test verifies that an
approved overlay actually reaches model messages, not just a Python helper.

## Storage, concurrency and recovery

All runtime state lives in ignored `platforms/dext/data/navigation/`:

- `snapshots/<digest>.json`: immutable baseline/operator revisions, canonical
  content, base pointer, hashed run provenance, UTC and proposal identity.
- `proposals/` and `decisions/`: generic candidates and immutable exact decisions.
- `active.json`: one atomic current/previous pointer and monotonic generation.
- `pins/<chat-digest>.json` and `.bound`: durable chat revision and presence marker.
- `store.lock`: advisory OS lock, released automatically on process death.

Writes use exclusive temporary files, fsync, immutable create-if-absent snapshots
and atomic pointer replacement. A cross-process lock plus compare-and-swap on the
entire base pointer prevents concurrent publication and ABA overwrites. Orphan
snapshots and partial temporary files are inert. Crash before pointer swap leaves
the old active revision; crash after swap reconstructs the complete new revision.
If a decision was recorded but activation failed, replay cannot silently publish
it; the operator must review a new proposal.

Missing/corrupt active pointers, missing pin files with surviving bound markers,
tampered snapshots or changed shipped baselines fail closed. Interrupted first
initialization can require operator repair, rather than guessing from orphan
files. Explicit rollback creates a new revision and preserves old snapshots; it
never rewrites history. Refusal leaves the active pointer intact.

Pins survive reopening/resuming a conversation and publication cannot alter the
running pin. New chats pick the latest approved revision. An existing chat can
adopt it only through the explicit **Adopt approved procedure for next run** UI
event while idle and without pending review/navigation. The native path checks
the pin again and freezes the installed source bundle before each model decision;
navigation preparation/approval rejects changed source, policy or pin.

POSIX directory fsync is used where available. Windows file fsync and atomic
replacement do not establish an absolute power-loss guarantee for every storage
device. Tests simulate failures around replacement, not hardware power removal.
Inert temporary files are retained as crash evidence; cleanup/retention is an
operator task. Private directories inherit host ACLs. Local filesystem/code
integrity remains trusted; symlink/reparse checks do not eliminate all TOCTOU
races against a malicious same-account filesystem writer.

## Client references and business contracts

Each client has **exactly three** approved filenames:
`comptable_banque.md`, `comptable_achats.md`, `comptable_ventes.md`. No generic
accounting reference file is introduced or read. The user instruction supersedes
historical handoff text about optional description files. Runtime `description`
remains null; its existing output field and offline invoice validation contracts
are preserved. Quotes and credit notes now explicitly require operator review,
including a balanced credit-note proposal. Historical helper tests may validate descriptions as in-memory
data without creating a fourth file.

References remain isolated under the registered active client's directory. The
existing strict local registration is preserved; other registered clients cannot
be selected through tool arguments. A per-file **2 MiB** cap deliberately permits
an approximately 1.93 MiB purchases corpus in full. Nothing is truncated. The
reader revalidates paths/reparse points, bounds and encoding on every use.

PR4 decision fingerprints now also bind all three current synthetic reference
revisions (including absence). Changing a corpus after model selection requires
a new decision; the parent and independent worker reject stale tickets. Reference
receipts retain digests only. A closed real-client registration never pre-reads
its private corpus merely during catalogue refresh.

The UI may record an operator-confirmed local client **claim** for a particular
preview observation. It is explicitly `verified_for_business: false`; it neither
unlocks real data nor changes PR4 synthetic authorization. A new observation
invalidates the claim even at the same URL. Real client processing remains blocked
because the current scanner cannot establish workspace/record identity. The
optional private-data extraction script was not run; no user corpus was read.

## Exact live blockers and security review

1. **Navigation:** the current element map supplies DOM IDs and rectangles for
   generic actions, but no verified Dext semantics, frame/record/workspace adapter
   or safe postcondition. No selectors are invented. Local operator confirmation
   does not establish that clicking a control cannot submit or autosave remotely.
2. **PDF provenance:** `chrome_pipe.rs::set_downloads_denied` verifies browser-level
   DENY acknowledgments. The transport now preserves bounded ordered Browser
   download events, including trailing frames in the same ACK read, with sticky
   malformed/replay/overflow handling. GUID/frame and a URL digest stay in private
   memory; filename/path text is not retained. Reads still occur while commands
   are pending, not through a continuous approved-download operation. No Dext
   record correlator, file verifier or isolated single-download exception exists.
   Every observed attempt, even canceled, stops scoped work. The extension's observer
   cancels attempts and latches review; it does not issue provenance receipts.
   Relaxing the global policy would permit effects this PR cannot prove. No
   exception, receipt issuer or pretend successful lifecycle is added.
3. **Live provider:** there is no real-record binding, PDF provenance or native
   external-effect permit. Consequently no per-call disclosure grant or real
   Gemini adapter is enabled. The tested offline fake remains the only provider;
   changing `COMPTABLE_LLM_MODEL` still fails before worker/network I/O. Existing
   fake response tests cover account/invoice parsing and error redaction. They do
   not prove Gemini request compatibility or real classification accuracy.
4. **Uncertain remote effects:** no new remote effect is dispatched here. Future
   execution must treat a dispatched-but-unobserved click or ambiguous provider
   response as uncertain, reconcile with the operator and never retry silently.
5. **Worker/host:** PR4 process-tree cleanup, source-only imports, single-use
   tickets and independent native/Python gates remain. A bounded subprocess is
   not a security sandbox or network firewall. No approval text can expand these
   boundaries. Existing main-agent page/model behavior is not a new privacy grant
   for transmitting local accounting references.

## Validation and operator pilot

The exact commands, counts, exclusions and source manifest are in
[pr5_completion_review.md](pr5_completion_review.md). CI discovers the new Python contracts through its
existing test command and retains native Windows tests, Linux compile check,
JavaScript contracts, UI build/typecheck, wheel and sdist checks. No cloud keys or
live Dext access are required. Python symlink tests may be skipped without the
corresponding Windows account privilege.

Reproduce with the existing PR4 cached tools or a normal configured environment:

```powershell
python -m unittest discover -s tests -t . -v
$env:SACCADE_TEST_PYTHON = (Get-Command python).Source
cargo test --locked --manifest-path AutoCua/web/Cargo.toml
cargo check --locked --all-targets --manifest-path AutoCua/web/Cargo.toml
node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs AutoCua/ui/platform_session/selection.test.mjs
npm.cmd --prefix AutoCua/ui run typecheck
npm.cmd --prefix AutoCua/ui run build
```

For packaging, rebuild wheel/sdist and set `SACCADE_TEST_NATIVE`,
`SACCADE_TEST_WHEEL`, and `SACCADE_TEST_SDIST` as in the PR4 guide. Private navigation
state inherits the existing Git and distribution exclusion for platform `data`.

An operator may explicitly initiate this limited manual pilot; it was not run:

1. Prepare synthetic local registration and exactly three fictitious references.
   Select Web → Dext → Supervised → Quality. Sign in manually; unauthorized SSO
   still requires stop/review. Do not put credentials or customer records in chat.
2. In a test workspace, ask for a navigation **preview**, not a click. Review its
   exact target locally. Reject once; approve another preview and verify the
   explicit adapter-required block. No actual gesture/transition is promised.
3. Enable local chat correction mode and submit recognized generic navigation sentences.
   Inspect old/new text and digests, reject one candidate, then explicitly publish
   another. Confirm tracked `dext.md` is unchanged.
4. Show that the current pin is unchanged; while idle explicitly adopt the new
   procedure for the next run, or start a new chat. Reopen the prior conversation
   and verify its persisted pin. Review the previous text before explicit rollback.
5. Attempt an unknown dossier, stale preview, unverified PDF or live provider
   selection. Each must remain blocked. Never approve a real disclosure merely
   to exercise this code; there is no enabled production adapter.

Before live navigation can ship, an operator-controlled test session must establish
stable workspace/record identities, safe exact target semantics, frame/DOM freshness
and observed postconditions. Then implement causal bounded PDF lifecycle receipts
and independent exact-payload provider consent under native effect permits. Only
after those prerequisites should a separate write-effect PR add field preview/fill,
intent journal, idempotence and independently approved save handling.

The current local onboarding commands and separate operator-controlled real test
plan are in [dext_reference_onboarding.md](dext_reference_onboarding.md) and
[dext_manual_test_plan.md](dext_manual_test_plan.md). The private ZIP remains unopened.
