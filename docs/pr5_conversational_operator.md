# PR5 conversational assistance and navigation learning

Branch: `feat/dext-live-navigation-learning`. Date: 2026-11-13.

The stable `learning.md` projection and spontaneous-correction extension are
documented in [Canonical learning and spontaneous corrections](pr5_canonical_learning.md).
That report supersedes the earlier snapshot-only projection description below.

## Implementation

The existing ordinary chat composer now checks the trusted operator broker before
model selection, correction mode or normal run startup. While an intervention is
pending, it submits a bounded reply to `/api/operator` with the current session,
run, intervention, revision and one-use token. A failed status lookup, foreign
conversation, unknown state or an unshown/replaced proposal cannot start a new
task. The normal start route retains its independent pending-intervention guard.

Questions appear as assistant replies using the existing chat renderer and
conversation transcript. A subtle indicator shows that the agent is paused and
making no model requests. Clarifications use the same user/assistant renderer,
without starting a run, and append to the existing local exchanges file through
`ConversationService.save_operator_reply()`. This method leaves model memory and
tool-call/result pairing unchanged. Valid resumed replies use `start_or_resume()`
and `save_run()` as before; the exchange shows the operator's actual reply while
the native task retains its original objective, informational context and history.
The display text is passed by the authenticated host, not accepted from run JSON.

The broker handles French/English confirmations deterministically. Authentication
and manual-action replies such as "Je suis connecté", "C'est bon", "J'ai terminé"
or "Done" confirm completion only in that pending context. Negative or uncertain
answers remain paused and receive a focused host clarification, with a rotated
revision/token. Questions accept bounded non-sensitive information; blocked
requests can solicit clarification without creating action authority. Passwords,
authentication codes and keys are rejected; authentication uses the dedicated
Chrome window privately. No LLM is used to interpret a reply. The filter is not a
general DLP system: operators must never enter obfuscated secrets or credentials.

The existing protected browser handoff is preserved: the broker retains the same
native scanner, private CDP transport and profile lease. Each resumed execution
revalidates installed context, saved paired checkpoint, ownership, authorized
page, fresh observer and download denial. It cannot replace the suspended browser
with a new Chrome. The source run control is also retained per conversation, so
using another chat does not redirect an old answer to another Dext session.

## Navigation compilation and corroboration

The conservative correction compiler accepts complete French/English paths such
as "Click Purchases, then Inbox" and "Ouvre les achats puis la boîte de réception".
It emits only closed vocabulary tokens. Unknown qualifiers, private names,
record identifiers, URLs, selectors, scripts and permission instructions are not
silently discarded. Incomplete guidance produces a focused question. Raw chat is
never stored in a navigation snapshot or proposal.

The native agent receives an explicit instruction to request assistance itself
when authentication, missing navigation knowledge, manual work or uncertainty
prevents progress. The user need not mention internal tools. In conversational
supervised Dext runs, an unsupported navigation preview returns immediately into
a manual-action pause; it does not require opening the technical preview panel.
The previous exact preview/review contracts remain available in advanced review.

The host attaches a bounded teaching draft to the existing Dext run control.
Before any model call, the existing native scanner supplies fresh, scope-checked
observations through the existing controller. For each teachable section step,
the draft requires one visible, exact recognized navigation label and a later
observation showing the corresponding changed section heading. Repeated identical
observations, ambiguous duplicate labels and transitions across different tabs
cannot complete a step. French/English labels are mapped to canonical names;
only canonical routes and digests of source/postcondition observations survive.

When an intermediate observation is needed, the existing native loop returns a
specific manual `waiting_operator` request before calling the provider. The same
task resumes after the operator replies. Once the bounded path is corroborated,
the existing procedure store creates an incremental candidate, and the loop
pauses for host-controlled review before another provider call.

This corroborates a demonstrated **operator-assisted** section path. It is not
proof of Dext control/frame semantics, read-only behavior, record identity or a
successful real navigation action. It never enables automated clicks. Workspace
or record identity cannot be learned from chat as a substitute for a verified
adapter. If the real tree lacks a supported visible control/heading, learning
remains blocked for clarification rather than inventing evidence.

## Exact conversational procedure approval

The assistant presents a concise canonical path summary and the exact procedure,
with an optional diff. A presentation digest seals the originating conversation,
run, intervention, current revision, proposal ID, base revision, candidate
revision, summary and diff. The browser-side reply transport also refuses to
consume an affirmative answer against a proposal not yet shown in that chat.

Only a specific pending learning proposal can interpret "Yes", "Oui" or "Yes,
save it" as procedure approval. "Continue" or "Done" cannot save a procedure.
"No" or "Don't remember this" rejects it; "Show me what will be saved" presents
the exact text without model work. "Change the second step" rejects the old
candidate, asks for the replacement and requires new corroboration before a new
candidate is proposed. Unknown or ambiguous decisions remain paused.

The trusted host calls the existing `DextRunControl.operator_event('review')` and
`ProcedureStore.review()` with the sealed exact identity. Mutable/replaced,
stale, foreign and replayed candidates are rejected. A missing or unpaired
execution checkpoint cannot publish learning or resume. Publication is never a
model tool. Independent browser, business, accounting, download and disclosure
approval mechanisms are unchanged. A procedure decision grants none of those
permissions. After the decision, the original task continues through the same
launcher and browser, subject to all existing gates.

## Markdown storage and compatibility

Canonical immutable snapshots remain JSON at:

`platforms/dext/data/navigation/snapshots/<revision>.json`

Each approved revision has a derived immutable UTF-8 Markdown representation:

`platforms/dext/data/navigation/snapshots/<revision>.md`

JSON hashes, the baseline digest, validated canonical rendering and the existing
atomic `active.json` pointer remain authoritative. Snapshot JSON and complete
Markdown are published before the pointer activates a revision. File fsync and
existing OS locking/CAS rules remain. Missing legacy Markdown is generated only
from a checked canonical snapshot; a mismatching or unsafe Markdown file fails
closed. There is no mutable `active.md` or second independent source of truth.
The native procedure overlay reads the checked Markdown for the pinned revision.

New conversational candidates contain bounded paths. A correction revises the
path with the same entry section and preserves unrelated approved paths. Legacy
route-list snapshots and preview/correction contracts continue to load. Rejected
or orphan candidates never activate. Prior snapshots and explicit rollback are
preserved. The active conversation keeps its pin even after approval; new
supervised Dext conversations use the approved active revision. Optional explicit
adoption remains an advanced action at the existing safe boundary.

The tracked `AutoCua/default_skills/web/domain_skill/dext.md` is unchanged. The
entire local navigation directory is excluded by `/platforms/*/data/` in Git and
`platforms/*/data/**` in wheel/sdist packaging. No private MPH/FRT references,
accounting records, credentials, raw operator chat or website instructions were
copied into reusable guidance. Ordinary validated replies can appear in the
existing local conversation transcript; that transcript is separate from SOPs.

## Exact changed files

- `AutoCua/agent_conversation/service.py`: natural paused messages and local
  clarification exchanges without changing native resume memory.
- `AutoCua/saccade/operator_requests.py`: contextual reply handling, per-chat
  teaching/control retention, sealed learning review and anti-replay protections.
- `AutoCua/saccade/operator_language.py`: bounded deterministic French/English
  reply interpretation, without provider calls.
- `AutoCua/saccade/navigation_correction.py`: natural section paths and bounded
  native observation corroboration; no selectors or private values.
- `AutoCua/saccade/dext_control.py`: conversational manual pauses and teaching
  attachment, checked Markdown overlay and existing host-side review integration.
- `AutoCua/saccade/procedure_store.py`: incremental paths and immutable checked
  Markdown projections with backward compatibility.
- `AutoCua/ui/service.py`: trusted chat routing, same-task continuation, exact
  procedure presentation, paired-checkpoint checks and ordinary display text.
- `AutoCua/ui/chat_input/chat_input.js`: broker-first ordinary composer and
  existing-renderer clarifications without an execution run.
- `AutoCua/ui/platform_session/operator_chat.ts`: status/presentation validation
  and trusted reply transport; no fallthrough on errors or stale conversations.
- `AutoCua/ui/platform_session/operator_review.tsx`: subtle pause/procedure
  presentation using the ordinary composer, without separate answer fields or
  Resume/Teach controls.
- `AutoCua/ui/platform_session/dext_review.tsx`: label the existing collapsed
  technical controls as advanced review and diagnostics.
- `AutoCua/ui/index.js`: rebuilt shipping UI bundle.
- `AutoCua/web/agent/main_driver/service.rs`: spontaneous assistance instruction,
  pre-provider learning checkpoint, actionable manual navigation requests and
  native zero-provider-call regression coverage.
- `AutoCua/web/controller/view.rs`: feed scope-checked scanner observations into
  the existing run control before provider work.
- `tests/test_operator_conversation.py`: real broker/control/store synthetic
  conversational approval, privacy, Markdown, evidence and replay contracts.
- `tests/test_platform_sessions.py`: actual host routes for French completion,
  negative answers, same-browser resume, per-chat control and full teaching cycle.
- `tests/test_packaging.py`: new reply modules and UI assets in the fresh wheel;
  existing private-data exclusion checks retained.
- `AutoCua/ui/platform_session/operator_review.test.mjs`: actual reply transport,
  presentation/session refusal and existing platform restoration/renderer tests.
- `AutoCua/ui/chat_input/correction.test.mjs`: actual composer priority,
  clarification rendering, zero run requests and previous correction contracts.
- `docs/ask_operator.md`: link current conversational behavior and privacy rules.
- `docs/dext_navigation_learning.md`: describe current chat integration and
  canonical Markdown projections while retaining advanced contract documentation.
- `docs/pr5_conversational_operator.md`: this implementation and validation report.

## Validation and remaining limitations

Validation uses synthetic states and fictitious data only. No real browser,
Dext account, credentials, private accounting file or live external provider was
used. The native fake-provider test verifies that a manual teaching checkpoint
returns with its provider counter unchanged. HTTP tests cover repeated status
polls with no added calls, same lease/scanner continuation and the full procedure
cycle. These results do not establish real-browser compatibility or real-provider
spontaneous assistance behavior.

Final commands/results are recorded with cached Python 3.12.10, Rust 1.97.1,
maturin 1.16.0 and Node 26.13.0:

| Check | Result |
| --- | --- |
| Full Python discovery, native DLL, fresh wheel and sdist | 202 total: 192 passed, 10 skipped, no failures/errors |
| Windows Rust tests, default parallel execution | 50 passed, 2 ignored, no failures |
| Windows Rust all-target check | Passed |
| JavaScript observer, selector, operator and composer tests | 39 passed |
| UI TypeScript check and production build | Passed |
| Fresh wheel and sdist construction/inspection | Passed |
| Git whitespace check; tracked baseline comparison | Passed; `dext.md` unchanged |

The Python skips require unavailable Windows symlink privileges. The Rust ignores
are the internal inherited-pipe child helper (invoked through its parent test)
and the opt-in real-Chrome test. Linux, interactive UI, real Chrome/Dext and live
provider SDK/network behavior were not exercised.

```powershell
cargo test --locked --offline --manifest-path AutoCua/web/Cargo.toml
cargo check --locked --offline --all-targets --manifest-path AutoCua/web/Cargo.toml
node --test AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs AutoCua/ui/platform_session/selection.test.mjs AutoCua/ui/platform_session/operator_review.test.mjs AutoCua/ui/chat_input/correction.test.mjs
npm.cmd --prefix AutoCua/ui run typecheck
npm.cmd --prefix AutoCua/ui run build
maturin build --locked --offline --profile dev --out .cache/operator-wheels
maturin sdist --out .cache/operator-sdist
```

Python discovery used `.cache/operator-validation/run_python.py`, with cached
Flask/Pillow dependencies and fresh `SACCADE_TEST_NATIVE`, `SACCADE_TEST_WHEEL`,
`SACCADE_TEST_SDIST` paths. Normal equivalent:
`python -m unittest discover -s tests -t . -v` with those variables set. Final
logs and result files are under ignored `.cache/operator-validation/chat-*`.
Maturin sdist retains the existing nonfatal root-manifest probe warning.

Automatic Dext navigation remains blocked because no verified semantic/frame/
record adapter exists. Recognized visible section labels and headings support
manual guidance only. Unsupported labels or missing intermediate evidence remain
staged; the operator receives a focused request. No learned text removes native
download denial, proves client/record identity, authorizes bank/scribe disclosure,
captures a live PDF or enables accounting entry. Learning overlays in this PR
apply to supervised Dext sessions. Process-restart browser reattachment remains
unsupported; saved context must not silently launch a replacement browser. The
existing paused-browser and long-context/compression limitations remain.

## Operator-controlled manual protocol (not executed)

1. In the real Saccade interface, use a disposable/non-sensitive supervised Dext
   chat and request purchase invoices without mentioning tool names. Verify the
   assistant asks for sign-in or missing navigation knowledge naturally.
2. While paused, record the provider counter/token total and wait at least a
   minute. Refresh/reopen the same chat: totals must not grow. Complete sign-in
   privately in the same dedicated Chrome window. Reply "Non, pas encore" first
   and verify no resume; then "Je suis connecté" and verify the same chat,
   objective, browser/profile, paired transcript and platform binding.
3. When asked how to navigate, reply "Ouvre les achats puis la boîte de réception".
   Follow any focused requests to show the source control and intermediate
   section. Confirm each manual step through chat. Unsupported or ambiguous
   states must remain paused; do not fabricate selectors or successful actions.
4. Review the concise path and exact proposed Markdown. Say "Show me what will
   be saved", then reject one candidate. Verify no active revision changes.
   Demonstrate a supported path again and say "Yes, save it" only after reviewing
   that precise presentation. Verify the immutable local JSON/Markdown revision,
   preserved previous versions and unchanged tracked baseline.
5. Continue the original task within its existing capabilities. A new supervised
   Dext chat must receive approved guidance; the current chat must retain its
   original pin. Unsupported navigation, record, download or disclosure actions
   must produce an actionable pause rather than a claimed success.
6. Try a stale answer/proposal and use another chat while one is paused. Verify
   session isolation, no competing browser, no self-approval and safe cancellation.
   Do not enter credentials or customer records in chat, logs or procedures.

No manual real-environment validation is claimed by this report. No staging,
commit, push, merge, branch switch, new PR or user-data deletion was performed.

Suggested commit: `feat(web): integrate conversational operator assistance and reviewed Markdown learning`
