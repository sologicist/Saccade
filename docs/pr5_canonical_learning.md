# PR5: canonical learning.md and spontaneous navigation corrections

Branch: `feat/dext-live-navigation-learning`. This continues the existing PR5.

## Stable verified Markdown

The exact human-readable current document is now:

`platforms/dext/data/navigation/learning.md`

It contains exactly the canonical content of the revision selected by
`active.json`, with no added wrapper or independent editing authority. Immutable
JSON and revision-specific Markdown snapshots remain unchanged. The tracked
`AutoCua/default_skills/web/domain_skill/dext.md` is unchanged.

The existing process lock serializes approval, rollback, projection verification
and pin reads. `learning.projection.json`, in the same private directory, records
the last verified pointer and an optional next pointer. It is a recovery journal,
not a source of procedure approval. Only validated `active.json` selects content.

Publication order under that lock:

1. Validate and publish the immutable approved JSON/Markdown snapshot using the
   existing exact review, revision hashes and compare-and-swap checks.
2. Verify the old stable document. Persist projection intent containing complete
   old/target pointer contracts before the active pointer swap.
3. Atomically replace `active.json` using the existing fsync/replace mechanism.
4. Atomically replace `learning.md` with complete canonical bytes, then read and
   verify those bytes. Settle the projection journal to the active pointer.

Recovery is deterministic. If interruption precedes activation, the old active
procedure remains authoritative and the unactivated target is never adopted. If
it follows activation, a missing projection or bytes matching the journal's
previous/target approved content are regenerated or verified from the active
canonical snapshot. If Markdown was swapped but journal settlement was interrupted,
the next verified load settles the same revision. No proposal is reapproved or
external action replayed by recovery. A decision may already be committed when
an I/O error reaches the caller: refresh verified active state instead of replaying
the decision. Existing orphan-snapshot and missing-active-pointer protections stay.

First initialization creates the document from the trusted baseline revision.
Existing PR5 stores with no stable projection migrate from their checked active
snapshot. Missing Markdown is recoverable. Unknown text, an unexpected copy of
an older approved revision without matching publication intent, malformed journal,
symlinks, reparse points or unsafe paths fail closed; unknown text is not silently
overwritten or used. Rollback is a new reviewed revision and updates the same
stable projection through the identical transaction.

The files are individually atomic, not one filesystem transaction across both
pointer and Markdown. An interruption can leave the previous complete approved
Markdown physically present until recovery. Consumers must use the locked store
verification, as the native loader does. No partially written or unapproved text
is returned as current by that verified interface. Windows power-loss durability
still depends on the underlying volume; process-interruption recovery is tested.

`ProcedureStore.active()`, initialization, pin access and Markdown loading verify
the projection. Native guidance still reads the exact immutable revision pinned
to its conversation. Updating `learning.md` cannot change an existing pin. A new
supervised Dext conversation pins the current approved revision; an old conversation
continues using its earlier checked snapshot even after approval or rollback.

The existing `/platforms/*/data/` Git exclusion and package data exclusions cover
`learning.md`, its journal, snapshots and temporary publication files. No private
reference files or real account data were read or copied for this change.

## Contextual spontaneous corrections

Pending operator answers and exact procedure reviews keep priority. When none is
awaiting an answer, the ordinary composer consults the same authenticated host
before normal dispatch. The host checks the persisted Web/platform binding,
original objective or recent native navigation calls, and the actual current run.
A context signature and one-use nonce bind the submission to that conversation
and run; changed, replayed and foreign contexts cannot initiate a correction.

Supported correction framing is stripped separately from route compilation:
explicit mistakes, "Tu dois", "Il faut", "Le bon chemin est", the bounded
purchase-invoice purpose phrase, and supported first/then connectors. Every
remaining step must completely match the existing closed vocabulary. Unknown
qualifiers, client/record details, URLs, selectors, scripts and sensitive effects
are rejected or clarified, never silently discarded. French and English variants
resolve to the same canonical Purchases/Inbox route. A route without relevant
navigation context asks whether it corrects the previous attempt. "Tu t'es trompé"
without a path asks for the sections. Unrelated requests remain ordinary requests.
"I'm connected" without pending authentication creates no learning or authority.

This extension currently targets the existing supervised Dext feature. It does
not add another platform, classifier model, conversation database or orchestrator.
Generic Web and other engine behavior remain outside spontaneous Dext learning.

### While executing

The host records one bounded correction in the existing broker and sets a trusted
pause marker on the existing stop event. It does not start a second agent, inject
tool calls or approve the route. The UI says **pause requested, correction not
applied yet**. An in-flight provider/tool call may finish until the existing
controllable stop boundary is reached. Existing per-action stop checks remain.

At the native checkpoint, the loop returns `waiting_operator`, releases inputs
and tab control, and retains its protected browser/pipe. The host saves the usual
paired conversation, validates the native handoff receipt and holds the same
profile lease. Only then is canonical guidance attached to the existing teaching
flow. If ownership or checkpoint verification fails, it reports the correction
unapplied and blocks Resume. Stop/New chat serialize with correction submission
and defer browser cleanup until the worker has stopped.

The operator receives an acknowledgment with the canonical route and confirms
through chat before reobservation. Corrections also work during a resumed run;
the consumed earlier intervention cannot mask a new correction. Pending procedure
approval or authentication waiting for an answer still wins. No model requests
are made while genuinely paused. The pausing phase does not falsely advertise
that an already in-flight request has stopped.

### After a terminal run

The host preserves the saved original task, settings and paired history. It asks
for confirmation to reopen a dedicated surface and verify the proposed route.
After confirmation, a narrowly validated native `correction_reopen` path may open
the installed scoped start URL while preserving history. This is an explicit new
owned browser session after the old run ended, not reconnection to a lost pipe
and not a fallback for normal `ask_operator` Resume. It requires a paired scoped
Dext checkpoint, no retained browser and the ordinary lease/live-profile checks.
It cannot start another connection to a live locked profile. Teaching then pauses
before provider work to collect manual evidence on the newly observed surface.

If source settings, saved context or a safe handoff are unavailable, the correction
remains unapplied with an explicit explanation. In-memory run settings are not
reconstructed across a backend restart. Ordinary pending recovery protections are
preserved; no missing browser is silently replaced by the ordinary Resume path.

## Learning and authority

A suggested route alone never writes a reusable procedure. Existing unique-control
and changed-heading observations, same-tab corroboration, manual assistance and
exact host-only proposal review remain required. Unsupported evidence stays
blocked or triggers a focused question. Approval publishes immutable versions and
refreshes verified `learning.md` while preserving unrelated approved paths and
the active conversation's pin. The original objective continues only within its
existing capabilities. Procedure approval grants no click, accounting, download,
client binding or disclosure authority.

Automatic real Dext navigation remains unverified and blocked: recognized sentences
and observed section labels do not prove safe gesture/frame/record semantics.
There are no new selectors, browser permissions or business tool execution paths.

## Exact changed files

- `AutoCua/saccade/procedure_store.py`: stable projection, recovery journal, locked
  verification, approval/rollback refresh and preserved pins.
- `AutoCua/saccade/navigation_correction.py`: bounded correction framing and
  practical French/English navigation variants.
- `AutoCua/saccade/operator_language.py`: contextual deterministic classification
  using the bound objective or recent native calls.
- `AutoCua/saccade/operator_requests.py`: one-use context claims, one queued
  correction per run, verified checkpoint attachment and existing continuation.
- `AutoCua/ui/service.py`: authenticated classification route, actual run binding,
  pause request, safe terminal correction continuation and Stop/New chat ordering.
- `AutoCua/web/agent/main_driver/service.rs`: stop-event operator pause, native
  handoff receipt, constrained correction restart and native regression coverage.
- `AutoCua/ui/chat_input/chat_input.js`: keep supervised Dext correction input
  available after run acknowledgment; preserve other mode behavior.
- `AutoCua/ui/platform_session/operator_chat.ts`: consult context classification
  before normal dispatch and distinguish queued correction from verified pause.
- `AutoCua/ui/platform_session/operator_review.tsx`: show the pausing state without
  claiming that the correction is applied or that in-flight work already stopped.
- `AutoCua/ui/index.js`: rebuilt shipping UI bundle.
- `tests/test_learning_projection.py`: initialization, equality, rejection,
  migration, missing/tampered/unsafe projection, atomic replacement, interruption
  recovery, rollback, pins, native overlay and Git exclusions.
- `tests/test_spontaneous_corrections.py`: bounded language variants, context,
  ordinary/authentication messages and rejected unknown details.
- `tests/test_platform_sessions.py`: real host routes for active, resumed, ended,
  ambiguous, replayed and failed handoff cases plus cancellation. Fix the isolated
  webview test stub so restoring its module snapshot cannot duplicate the broker.
- `tests/test_platform_session_native.py`: native restart checkpoint/scope guards
  and proof that a confirmed correction cannot bypass profile ownership.
- `AutoCua/ui/platform_session/operator_review.test.mjs`: correction transport,
  pending-intervention priority and prevention of a competing run.
- `docs/dext_navigation_learning.md`: link the current stable projection workflow.
- `docs/pr5_conversational_operator.md`: link the extension to the earlier report.
- `docs/pr5_canonical_learning.md`: this report and manual protocol.

No Windows/Linux/macOS/Android/iOS engine file, Chrome transport implementation,
tracked domain baseline, dependency or Git exclusion was changed.

## Verification

All automated data and browser states are synthetic. No Chrome/Dext operation,
credential, private accounting file or live provider call was used.

| Check | Result |
| --- | --- |
| Full Python discovery with fresh native DLL/wheel/sdist | 225 tests: 214 passed, 11 skipped, no failures/errors |
| Windows Rust tests, default parallel execution | 50 passed, 2 ignored, no failures |
| Windows Rust all-target check | Passed |
| JavaScript observer/selector/operator/composer contracts | 41 passed |
| UI TypeScript and production build | Passed |
| Fresh Python wheel and source distribution | Built and inspected successfully |
| Git whitespace and tracked `dext.md` comparison | Passed; baseline unchanged |

The eleven Python skips require unavailable Windows symlink privileges. The two
Rust ignores are the internal inherited-pipe child helper, exercised through its
parent test, and the real-Chrome opt-in test. Linux, interactive UI, Chrome/Dext,
real-provider behavior and power-loss durability were not tested. Synthetic
success does not establish real-browser compatibility.

```powershell
cargo test --locked --offline --manifest-path AutoCua/web/Cargo.toml
cargo check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml
node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs AutoCua/ui/platform_session/selection.test.mjs AutoCua/ui/platform_session/operator_review.test.mjs AutoCua/ui/chat_input/correction.test.mjs
npm.cmd --prefix AutoCua/ui run typecheck
npm.cmd --prefix AutoCua/ui run build
maturin build --locked --offline --profile dev --out .cache/operator-wheels
maturin sdist --out .cache/operator-sdist
```

Python used cached Python 3.12.10, Flask/Pillow dependencies and
`.cache/operator-validation/run_python.py` with fresh `SACCADE_TEST_NATIVE`,
`SACCADE_TEST_WHEEL`, `SACCADE_TEST_SDIST` paths. Normal equivalent:
`python -m unittest discover -s tests -t . -v` with those variables set. Rust
1.97.1, Node 26.13.0 and maturin 1.16.0 were cached locally. Final logs and counts
are under ignored `.cache/operator-validation/canonical-*`. The sdist command
retains its existing nonfatal root-manifest probe warning.

## Operator-controlled manual protocol (not executed)

1. In a disposable, non-sensitive supervised Dext chat, request purchase invoices.
   During navigation type "Non, il faut aller dans Achats puis Boîte de réception".
   Verify the queued acknowledgment, then the real checkpoint, same dedicated
   window/profile and original objective. No second Chrome or agent may start.
2. Confirm through chat and follow manual evidence requests. Verify zero provider
   calls/token growth while paused. Reject one proposal and confirm `learning.md`
   is unchanged. Approve a separately corroborated exact candidate; confirm that
   `learning.md` equals its canonical immutable Markdown bytes.
3. Start another supervised Dext conversation and confirm it receives the approved
   guidance. The earlier conversation must retain its prior pin. Review rollback
   through advanced controls and verify the stable projection updates accordingly.
4. After a completed/failed run, send the correction example with "You made a
   mistake". Confirm the original task is retained and the explicit reopen prompt
   appears. A live locked profile must block a competing startup. Fresh reobservation
   must precede model work or any authorized action.
5. Send "Summarize the current page" and "I'm connected" without pending auth:
   neither may become learning or a grant. Try an ambiguous route and verify a
   focused clarification. Test correction during a resumed run and Stop during
   pausing; cleanup must follow worker completion.
6. In synthetic/disposable data only, interrupt publication at the documented
   boundaries and reopen the store. Verify deterministic recovery from approved
   state, refusal of unknown Markdown and preservation of old pins. Never edit
   private production procedure files merely to exercise a destructive test.

No commit, staging, push, merge, branch switch, new PR or user-data deletion was
performed. Suggested commit: `fix(web): maintain canonical learning.md and route spontaneous corrections`
