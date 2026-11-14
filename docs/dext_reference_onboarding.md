# Private Dext reference onboarding

The local store is `platforms/dext/data/<client_id>/` under the Saccade checkout
or installed project root. Registration is `platforms/dext/data/registration.json`.
Use lowercase IDs matching `[a-z][a-z0-9_-]{0,47}`; `navigation` is reserved for
the procedure store. A local ID is not a verified Dext workspace identity.

Each client must have exactly these three Markdown filenames:

- `comptable_achats.md`
- `comptable_ventes.md`
- `comptable_banque.md`

There is no generic accounting reference file. Extra Markdown files, including a
generic description reference, are rejected. There are no fallback client rules.

## Initialize directories without copying private data

Run these commands yourself in your configured Python environment, from the
repository root. They create directories only and are safe to repeat. They do
not create sample accounting rules, edit registration, import ZIP files, overwrite
existing references or authorize analysis:

```powershell
python -m AutoCua.saccade.reference_management initialize --client frt
python -m AutoCua.saccade.reference_management initialize --client mph
```

The resulting directories are `platforms/dext/data/frt/` and
`platforms/dext/data/mph/`. The implementation did not run these commands against
your data and did not open `prompts_FRT_MPH_sans_Gemini.zip`. If you choose to place
your three existing files in each directory, do that separately on your computer
after checking destinations. No automatic import/extraction command is provided.

## Validate locally

These explicit commands read complete local files in the operator's Python
process. They make no network/model request and print only technical metadata,
per-file error codes, sizes and revisions, never reference text:

```powershell
python -m AutoCua.saccade.reference_management validate --client frt
python -m AutoCua.saccade.reference_management validate --client mph
```

Validation exits 0 for a valid three-file bundle, 2 for invalid input. Diagnostics
include `missing_reference`, `empty_reference`, `invalid_reference_encoding`,
`invalid_reference_content`, `size_limit`, `unsafe_path`, `unsafe_reference_link`,
or an unavailable file/directory. Unexpected Markdown is reported by count without
printing potentially sensitive filenames.

Each file must be nonempty UTF-8 (a UTF-8 BOM is accepted), without binary headers,
NUL or inappropriate control characters. Each may be up to **2 MiB of original
bytes**, deliberately accommodating an approximately 1.93 MiB purchases reference.
There is no truncation, indexing or summarization. Symlinks, Windows reparse
points, cross-root paths and hard-linked reference files are rejected. Validation
does not certify the correctness of accounting rules; that remains an operator
responsibility. Do not rename a PDF or ZIP to Markdown.

## Register or select metadata explicitly

Stop active runs before changing registration. Inspect current metadata and its
revision:

```powershell
python -m AutoCua.saccade.reference_management registry-status
```

To register an already validated local real client, copy the returned `revision`
into this command. The first registration needs explicit `--activate`. For later
registrations omit `--activate` to preserve the existing active client:

```powershell
python -m AutoCua.saccade.reference_management register-real --client frt --expected-revision "<revision from registry-status>" --activate
```

To select a previously registered client, obtain a fresh revision first:

```powershell
python -m AutoCua.saccade.reference_management activate --client mph --expected-revision "<fresh revision>"
```

Writes are locked across processes, compare the expected current revision, flush
a private staging file and publish registration atomically. Existing client
policies are preserved. Duplicate registration, missing/invalid references, stale
revisions and racing edits fail without replacing the previous registry. Only the
operation's own staging file is cleaned up; reference files are never deleted.
Manual editors do not participate in advisory locks; malicious concurrent local
filesystem writers remain outside the trusted-host guarantee.

`register-real` writes `synthetic: false`, an empty label list and no fake responses.
Registration/activation **does not** grant record binding, PDF access, external
disclosure consent or accounting rights. Real business analysis remains blocked.
It never offers a flag that retags private data as synthetic. A changed active
client invalidates the existing run instead of silently switching its references.

## Offline tests and privacy

The existing trusted synthetic registration/fake provider continues to work. Its
entirely fictional client directory also needs all three valid references. Every
business call checks bundle validity before launching the worker; the worker
independently checks it again. The selected function rereads its full relevant
reference, and PR5 fingerprints all three revisions. Invalid unrelated reference
files therefore cannot be silently ignored during business execution.

Private data, registration/lock/staging files and navigation state inherit the
existing `platforms/*/data/**` Git/wheel/sdist exclusions. Do not force-add files,
paste their contents into chat, upload diagnostics with financial content or
mislabel real data as synthetic. No accounting-reference body is placed in a
receipt, log, SOP, automated test or artifact. Provider authorization remains a
separate, currently unavailable boundary.
