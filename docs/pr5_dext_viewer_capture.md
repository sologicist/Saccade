# PR5 native-download simplification and remaining security limitation

## Current status

The Dext-specific extraction implementation has been removed. The requested
Chrome-file-to-Scribe production chain is NOT implemented or validated.
No real Chrome/Dext session, client documents, profile or provider was accessed.
No pull, reset, checkout, commit or push was performed.

## Removed components

- PDFViewerApplication/getData and MAIN-world extraction functions.
- Dext preview resource selection, Network response caches, authenticated resource
  replay, source tokens, frame/loader proofs and the associated extension commands.
- Native viewer state, system-control probe, receipt/control fingerprint hooks,
  controller branches and production test mocks for that adapter.
- Extraction-only diagnostics/tests and the instruction to use download on a
  button without href. The scanner's descriptive Download PDF label remains.

Generic protected observed-link downloads remain intact for all platforms. The
existing Chrome scope/ownership/pipe/lease, DENY, operator broker, learning store,
client registrations, private data and accounting functions remain intact.

## Native execution and truthful results

Observed Download buttons use the existing click/hold_click tool and dispatcher.
A generic recognized download control receives a session/target-bound operator
execution decision (independent of learning and Gemini consent). The destination
is explicitly unverified; approval does not promise that Chrome can save a file.
A dispatched click is not a verified download: recognized successful download
clicks return waiting_operator/native_download_unconfirmed, never a file receipt.
Other navigation remains on the same engine. No system dialog is automated.
The prompt forbids guessed filenames/paths, invented receipts and inferred Scribe
results. This is not a claim that arbitrary model prose can be formally verified.

## Why the Chrome file path is still unavailable

Audit found no existing Generic AutoCua completion-to-filesystem receipt path.
The Chrome Downloads API has DownloadItem.filename (absolute path), state and
exists, but exists may be stale and DownloadItem has no tab/frame identity field.
It cannot alone prove that a file belongs to an authorized click. Existing CDP
Browser download evidence keeps frame/GUID/lifecycle metadata, not a verified
path. Browser.downloadProgress.filePath is optional and is not filesystem proof.
The existing pipe does not offer a production download capture operation.

Scoped native Rust enforces Browser.setDownloadBehavior DENY; the extension also
cancels and flags any attempt. Browser.setDownloadBehavior is context-wide, not
an exact tab/action/file permit. Temporarily allowing the context and canceling
other downloads after their creation would leave a race and is not the precise
pre-dispatch protection requested. That policy was not weakened. The current
native click can therefore be denied or blocked by a Save/Print dialog; neither
case is reported as a successful PDF download. No search of Downloads, old-file
selection, inferred filename or model-supplied path was added.

Before implementing production capture, a native admission mechanism must reject
unrelated downloads before writing while allowing the authorized native click.
It must then associate one new CDP frame/GUID with the Chrome DownloadItem and
completed absolute path, reject ambiguous/concurrent/stale/canceled events,
verify the file and restore DENY on every exit. This mechanism is still missing;
a Downloads API observer alone would not meet that security guarantee.

API references: https://developer.chrome.com/docs/extensions/reference/api/downloads
and https://chromedevtools.github.io/devtools-protocol/tot/Browser/

## Existing private storage and Scribe

The retained protected-link transport can still supply bytes to save_download.
It verifies size (8 MiB), PDF signature, read-back and SHA-256 and publishes
platforms/<platform>/data/navigation/downloads/<random-id>.pdf plus
<random-id>.receipt.json. The model receives a host-issued receipt ID, not PDF
bytes. Scribe keeps receipt:<id>, the active registered Dext client, achat/vente,
the full client-specific comptable_achats.md/comptable_ventes.md and separate
Gemini disclosure approval. No accounting write is performed.

No migration or deletion of existing private receipts was performed. Receipts
from the removed viewer adapter are rejected for revalidation rather than
silently trusted without their former identity checks. Other supported receipt
contracts and legacy Dext functions remain unchanged.

## Validation and gaps

Tests retain the real native bridge one-use permit checks, generic observed-link
transport across three platforms, private receipt/Scribe/provider validation,
accounting constraints, canceled/replayed/invalid CDP events and Chrome ownership.
A new Python regression verifies native click authorization without extraction.
The scanner serialization test still verifies the empty Dext button label.

There is no passing production or synthetic Chrome-file capture test: that path
is missing. Completed absolute-path ingestion, simultaneous Chrome files,
Save-dialog recovery, filesystem-tamper checks for Chrome-created files and
native-click-to-file-to-Scribe acceptance remain unimplemented. Existing link
receipt tests are not presented as proof of native Chrome file capture.

## Minimal real validation

Rebuild/restart the local application without changing the dedicated profile.
Open the selected registered client/invoice. Observe the labeled Download control
and its exact click decision. Expect denial/unconfirmed status if no verified
file path is returned; stop if a native dialog opens. Do not repeatedly approve,
automate the dialog or claim Scribe success. Production acceptance requires the
missing precise admission/capture path first, then a real downloaded PDF receipt
and a separate approved Gemini call. Testing the current code cannot establish
that missing capability.

## Actual local results and changed files

- Full Python suite: 283 discovered, 272 passed, 11 symlink-privilege skips,
  zero failures/errors (89.404 seconds). After the final destination wording,
  all 10 Scribe tests passed again.
- Rust all-target check passed; 54 tests passed, two ignored (real Chrome opt-in
  and internal pipe helper); final suite duration 11.50 seconds.
- 51 JavaScript tests passed. UI typecheck and Vite build passed.
- Final development wheel and sdist rebuilt. Packaging rerun results are recorded
  in .cache/operator-validation/native-simplify-packaging.log.
- git diff --check passed; real Chrome/Dext/Gemini and Linux Rust were not run.

Files changed during this simplification (including removal of uncommitted work):
AutoCua/web/browser/AutoCuaBridge/tools.js (restored generic contents),
AutoCua/web/browser/AutoCuaBridge/element.js,
AutoCua/web/browser/AutoCuaBridge/platform_scope.test.cjs,
AutoCua/web/browser/browser.rs,
AutoCua/web/controller/view.rs,
AutoCua/web/agent/main_driver/service.rs,
AutoCua/saccade/platform_learning.py,
AutoCua/saccade/scribe_pdf.py,
tests/test_scribe_pdf.py,
docs/pr5_dext_viewer_capture.md.
Existing operator_requests.py and test_operator_conversation.py changes were
preserved. No client data, profiles, keys, registrations or learning were changed.
