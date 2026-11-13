# PR5: shared conversational platform learning

This change continues `feat/dext-live-navigation-learning`. It does not add an
agent loop, browser connection, conversation store, dependency or permission.

## Shared implementation and intentional specialization

`PlatformLearningControl` owns the existing learning checkpoint, observation
expiry, session pin, proposal and exact review. `DextRunControl` subclasses it
only for Dext business-catalogue freshness, client claims and the existing
blocked navigation preview. Accounting, bank, scribe, downloads, record identity
and write authorization remain Dext-specific and retain their existing gates.

`navigation_correction` compiles complete bounded phrases against the selected
adapter; `NavigationTeaching` corroborates a manual transition. The existing
operator broker handles the same question, response, correction, pause, browser
handoff, candidate presentation, approval and same-chat continuation for every
installed platform. Unsupported details produce clarification, never a guessed
route. Simple completion/authentication replies use no model interpretation.

The native controller has separate learning and Dext preview controls. The
existing native scanner supplies platform/profile/configuration/observer/tab
evidence after its normal scope checks. The actual native prompt composition
combines the active exact-host platform baseline with its checked pinned
overlay. It rejects a different platform's overlay. An overlay grants no browser
or business authority. No extra tool is exposed for generic learning.

## Register another platform

Use the existing strict `platforms/<id>/platform.json`, native domain manifest
and `AutoCua/default_skills/web/domain_skill/<id>.md` contracts. The baseline is
resolved through the installed registry; the model/chat cannot supply paths,
Python imports or another platform identity. Profile ownership stays with the
existing `saccade-<id>` lease and private CDP transport.

Optionally install `platforms/<id>/learning.json`:

```json
{
  "schema_version": 1,
  "platform_id": "synthetic_portal",
  "landmarks": [
    {"id": "settings_page", "label": "Settings", "aliases": ["Parametres"]},
    {"id": "billing_page", "label": "Billing", "aliases": ["Facturation"]}
  ]
}
```

This is trusted installed configuration, not learned data. Declare only public
section labels, never client names, identifiers, credentials or private content.
The loader rejects unknown fields, duplicate keys/IDs, overlapping normalized
labels, unsafe files, identity mismatches and oversized content. It accepts at
most 32 landmarks, 8 aliases per landmark and short non-executable labels. There
are no configured scripts, selectors, dynamic imports or automation grants.
`learning.json` is included by the wheel/sdist configuration when installed.

No adapter means the common operator/pause/baseline lifecycle still works, but
new labels cannot be compiled or remembered: the operator receives a focused
clarification. Dext retains a shipped, isolated compatibility vocabulary in
`dext_learning.py`; existing installations need no metadata or data migration.
Changing an adapter is a trusted deployment change, not a chat learning action.
Revision mismatches fail closed; old approved vocabulary is not silently
reinterpreted. Review such a deployment separately.

## Evidence and privacy contract

New schema-2 steps contain only a configured landmark identifier and the
verification requirement `manual_heading_transition`. Each bounded path has at
most eight steps, with at most eight independently preserved paths. Markdown is
rendered solely from the validated public adapter, never from operator prose or
DOM text. Evidence contains digests rather than raw observations.

A step needs exactly one visible supported control with that closed label,
followed by a different trusted observation with exactly one matching heading.
A heading already present does not prove a transition. Changing observer, tab,
profile, platform or configuration invalidates the source evidence. Browser
scope checks, exact authorized hosts and sticky security violations remain the
native scanner's responsibility and precede the learning checkpoint.

This evidence corroborates operator-assisted guidance. It does not prove frame,
workspace or record semantics, nor that a gesture would be safe. The control
requests manual navigation when those capabilities are unavailable. Unsupported
labels, private qualifiers, URLs, scripts and partial interpretations remain
blocked or require clarification. Raw correction text may remain in the local
conversation under its existing policy; it is never persisted in the procedure.

## Isolated persistence and backward compatibility

Each installed platform uses exactly:

`platforms/<id>/data/navigation/learning.md`

Its active pointer, recovery journal, immutable JSON/Markdown snapshots,
proposals, decisions, pins, lock and rollback history live in that same private
directory. Existing Git and package data exclusions apply to every platform.
Unknown IDs, traversal, symlinks/reparse points, unexplained Markdown changes,
foreign revisions and damaged pointers fail closed.

The stable Markdown is a verified projection of `active.json`, never an
independently editable source. Publication still uses the same locked CAS,
fsync, immutable snapshots, atomic replacements and projection recovery
journal. Windows power-loss durability still depends on the volume. Rejected
proposals cannot activate content. Rollback is a new revision, never mutation.

Dext schema-1 snapshots, baseline hashes, Markdown bytes and conversation pins
remain valid and immutable. No real data migration is executed. New shared
learning candidates use schema 2 with explicit platform and adapter revisions.
An old Dext path is converted only inside a newly proposed candidate that needs
its own approval; the original snapshot and old conversation pin remain intact.
Legacy Dext identity/review cautions that cannot become section transitions are
retained through a checked immutable schema-1 revision reference and displayed
in full in the new candidate, without claiming new transition evidence.
The legacy advanced Dext proposal API remains supported. Schema 1 is rejected
outside Dext. Cross-platform snapshot/proposal copies cannot pass identity
validation, including when baselines happen to match.

Existing chats retain their immutable pin across pause/resume and approval.
New chats pin the current approved revision. The native prompt reads checked
immutable pinned Markdown, not the latest mutable projection. The store also
verifies the current projection before use to detect tampering/recovery gaps.

## Chat, approval and continuity

The server derives correction eligibility from the saved verified Web platform
binding. Its one-use correction claim includes the task/history/run state and
adapter revision. The ordinary composer stays available after an installed
platform's run acknowledgment. Pending questions and exact procedure reviews
take precedence over spontaneous classification.

An active correction requests the existing safe native checkpoint. Until the
worker confirms a saved paired transcript and browser ownership, the correction
is only queued. Manual/authentication pauses retain the dedicated browser and
lease through the existing broker. A suspended browser is never silently
recreated. Post-run correction uses the existing explicit reviewed fresh-surface
continuation, now for any validated platform. It retains the same task/chat and
reobserves before any action. No model polling runs while waiting.

The broker seals the exact proposal, full platform context, adapter, pin,
session, control run and request presentation. It rechecks the installed binding
and pin before approval/resume; existing one-use response/revision tokens and
store CAS prevent stale approvals and replay. Approval authorizes only publishing
the displayed guidance. It does not adopt a new pin in the current chat and
never authorizes an external effect.

## Automated evidence and manual protocol

Tests use Dext fixtures and `synthetic_portal` with another host, baseline,
profile, public vocabulary and store. They exercise the actual HTTP launcher,
chat/broker, storage and native prompt composition/checkpoint using synthetic
scanner/provider boundaries. They do not launch Chrome or validate real Dext.
See `pr5_platform_learning_review.md` for exact commands/results and changed files.

Manual protocol, not executed by this change:

1. Use an isolated Dext test profile/account and synthetic records only. Open a
   supervised task, request a manual/authentication pause and verify the window
   remains usable, the lease stays exclusive and model-call counters stop.
2. Correct a public section path through the ordinary chat. Demonstrate each
   source control and heading manually; confirm observations in that same chat.
   Review the complete candidate, reject it once, then demonstrate and approve
   a fresh candidate. Verify only Dext's private `learning.md` changes.
3. Resume the original task. Confirm the selector remains bound to Dext and the
   browser/profile is revalidated. Confirm this chat retains its old pin; a new
   chat receives the newly approved overlay. Do not approve business effects.
4. Repeat with a second disposable registered platform using two public control
   labels and real heading transitions. Configure only metadata/domain skill,
   with no copied host/controller code. Use an operator-controlled HTTPS test
   site and its separate profile; `portal.example.test` is an offline fixture,
   not a real reachable service. Confirm its overlay excludes Dext guidance.
5. Attempt stale approval, wrong-platform/profile observation and foreign
   snapshot/pin reuse. Expect review/blocked states before further action.
   Cancel while paused and verify exclusive ownership is released only after
   native cleanup succeeds. Test failed reattachment without creating another
   Chrome or debugging connection.

Real browser behavior, authentication flows and platform frame/record semantics
remain unverified until that protocol is performed. Synthetic tests must not be
presented as proof of real browser automation.
