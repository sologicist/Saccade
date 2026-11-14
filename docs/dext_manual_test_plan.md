# Manual real-Dext test plan — PR5 readiness

Status: **not executed**. No capability is VERIFIED ON REAL DEXT. This plan is
for a human operator after explicit authorization of a non-sensitive test
workspace. It is not permission for unattended login or production processing.
See [pr5_completion_review.md](pr5_completion_review.md) for implementation status.

## Preconditions and local evidence

- Use only a dedicated Dext demo/test workspace with invented invoices and bank
  transactions. Verify that no production client, supplier, bank data or actual
  accounting references are visible or loaded.
- Use the normal local Saccade launcher and its configured Python/desktop runtime.
  Select **Web → Dext → Supervised → Quality**. Do not use Auto, a custom debugging
  port, another profile, a second agent or a desktop-agent fallback.
- Authorize the chosen main Web model to observe only this non-sensitive test
  page. This does not authorize transmission of accounting references or PDFs to
  an accounting provider. No Gemini call is enabled by this build.
- Follow [dext_reference_onboarding.md](dext_reference_onboarding.md) using entirely
  fictional data. Do not extract the supplied private archive as part of testing.
- Keep any evidence locally under ignored `platforms/dext/reports/`. Do not commit
  screenshots, signed URLs, cookies, raw prompts, PDFs, bank labels or references.
  Record only redacted metadata in a review summary: application commit, OS,
  Chrome version, test-case ID, expected/actual status, operator decision and
  opaque revision/run/evidence digests.

## 1. Visible Chrome startup and profile ownership

Start one supervised test run. Verify visible Chrome uses the dedicated
`saccade-dext` profile. Attempt a second concurrent run and confirm rejection
without taking over the first run's stop channel. Verify native download DENY
has a positive acknowledgment before scoped work begins.

Expected status: IMPLEMENTED BUT NOT LIVE-TESTED until actual evidence is reviewed.
A missing authenticated bridge, wrong profile, missing denial ACK or existing
incompatible Chrome process must stop; never substitute a remote debugging port.

## 2. Manual authentication

The operator handles sign-in, passwords and MFA manually. Do not put credentials
in chat. An unauthorized SSO hostname must stop the run; do not expand the host
allowlist. If sign-in must occur between runs, end the run, authenticate manually
in the dedicated profile, close Chrome cleanly and restart through the protected
launcher so a fresh private pipe/lease can be established. Preserve cookies only
locally. Report incompatible login flows rather than bypassing them.

Download DENY is verified **during an active protected scope**. Existing teardown
restores ordinary Chrome behavior after the scope/observer is released. An open
Chrome window or a waiting-operator result alone is not proof an active protected
scope still exists. Do not perform download-policy tests after teardown.

## 3. Verify the actual workspace and client mapping

Manually identify the test workspace using stable account/workspace identity and
independent visible corroboration. A local client ID, title, substring match or
URL is insufficient. Record what live fields exist and whether they remain stable
across SPA transitions. Do not supply production names or IDs to this repository.

Current expected result: **BLOCKED — no verified workspace/record adapter**.
The UI can record an operator claim, explicitly not business authorization. If it
silently enables a real client or changes an active client, stop and report a bug.

## 4. Reach a test invoice

Ask for one invoices navigation preview. Review the exact current target label,
role, geometry, tab, policy and observation/procedure revisions locally. Reject
once, then approve a fresh preview. Check expiry and changed-target refusal.

Current expected result: **BLOCKED — no verified frame/target semantics or
postcondition adapter**. Approval must send no click. The operator may navigate
manually to gather non-sensitive evidence, but that is not an agent navigation
success. Before enabling a future adapter, establish frame/backend node identity,
fresh hit-test/DOM identity, non-writing semantics and fresh postcondition proof.

## 5. Reach a test bank transaction

Repeat with a synthetic bank row. Manually inspect whether Dext exposes stable
transaction identity and an exact label tied to the verified workspace/client.
Move to another row at the same URL; old observations/claims must be invalidated.

Current expected result: **BLOCKED for automated navigation and verified label
capture**. Registered fake labels can exercise the existing offline bank function,
but are not evidence that a real Dext transaction was recognized.

## 6. Operator chat correction and procedure publication

Enable **Use next chat message as a local navigation correction** in Dext operator
review. Type, for example, `Open invoices then confirm the workspace then select
the record then ask for operator review.` Send with Enter and the normal send orb.

Verify that no new model run starts and no raw correction is stored in general
history. Review the generic diff, origin, evidence status and exact base/candidate
digests. Reject once and confirm the active pointer is unchanged. Submit another
correction, explicitly approve its exact diff, and verify publication.

Confirm the existing conversation's pin is unchanged. While idle explicitly adopt
the approved revision for the next run, or start a new chat. Reopen the previous
chat and verify its pin. Review the previous revision and explicitly approve a
rollback. Confirm tracked `AutoCua/default_skills/web/domain_skill/dext.md` is
unchanged. Private names, selectors, URLs, values or accounting-rule corrections
must be rejected and never become reusable guidance.

Expected status: IMPLEMENTED BUT NOT LIVE-TESTED for desktop interaction; core
compiler/API/store/native reuse is IMPLEMENTED AND VERIFIED SYNTHETICALLY.

## 7. Approval expiry, rejection and isolation

Try a stale observation, a changed row at the same URL, wrong client, foreign tab,
unexpected redirect and a rejected/expired approval. Each must stop or remain
blocked with no input or worker for the unauthorized request. A browser disconnect
or observer loss must remain sticky; another allowed URL cannot clear it. No
chat word such as "yes" may approve a pending operation.

## 8. PDF download and provenance

Current result: **BLOCKED — no approved single-download exception, verified
record/document binding, local-file verifier or receipt issuer**. Do not attempt
to turn a model-supplied path or manual download into a receipt. No live `scribe`
test can pass in this build.

The new CDP journal is tested with inherited pipes and synthetic begin/progress/
completion/cancellation frames. Its events are observations, not permission or
file identity. A completed event does not prove a file exists. A future authorized
test must prove record/frame association, one download only, private destination,
completed PDF identity/digest/size and an acknowledged return to DENY, including
failure/cancel/timeout/disconnect. Additional downloads or ambiguous association
must invalidate the operation. Restoration failure requires stop/restart review.

## 9. Read-only accounting proposals

Use only the already registered invented inputs and the fake provider. Confirm
bank returns exactly an account or null, quotes/credit notes/uncertainty require
review, invoice schemas remain strict and description remains null without a
fourth reference file. Do not compare fake output to real Dext as proof of live
classification. Real bank capture, real PDF analysis and Gemini remain BLOCKED
until record binding and independent exact-payload disclosure consent exist.
Never fill, type, save, submit or reconcile any Dext accounting field.

## 10. Interruption, recovery and cleanup

Stop while waiting for an operator decision and verify prompt cancellation,
permission revocation and lease release. Close/reopen the conversation and verify
the pinned approved revision. Corrupt or missing local pin/pointer must fail
closed, not silently adopt a new revision. Inspect any worker shutdown using only
synthetic jobs; no worker/process tree should survive cancellation. Test browser
disconnect recovery through the normal protected restart, never a side channel.

End all test runs and close the dedicated Chrome process yourself. Preserve local
evidence for review; do not delete private references or upload artifacts. Record
each capability using exactly one of: IMPLEMENTED AND VERIFIED SYNTHETICALLY,
VERIFIED ON REAL DEXT, IMPLEMENTED BUT NOT LIVE-TESTED, or BLOCKED — EXACT REASON.
No live label is earned until the genuine run and its evidence are reviewed.

## Merge decision

PR5 is **not ready to merge as completed live Dext functionality**. Successful
onboarding, chat learning and CDP evidence tests do not resolve its required live
navigation and PDF provenance prerequisites. Keep the existing PR open for review;
do not create another PR or merge based on CI alone.
