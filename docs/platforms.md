# Web platform configuration and native domain skills

This PR 1 integration uses AutoCua's existing Web Rust loop and native skills.
It provides configuration discovery; it does not start a platform session or
grant business-tool, client-data, navigation, or write permissions. Session
selection, controller scope enforcement, supervision, recovery and learning
remain separate roadmap slices. Do not use this slice for production writes.

## Configuration contract v1

`platforms/<id>/platform.json` requires exactly `schema_version`, `id`, `name`,
`engine`, `start_url`, `allowed_hosts`, `browser`, and `max_steps`. Version is
integer `1`; engine is `web`; browser is `chrome`; steps are an integer from
1 to 1000. IDs match `[a-z][a-z0-9_-]{0,63}` and must equal their directory name.
The start URL must be HTTPS, use an explicitly allowed canonical hostname,
and contain no credentials or nondefault port. Hosts are distinct lowercase
ASCII DNS names; wildcards, trailing dots and implicit subdomains are rejected.
These declarations do not enforce browser actions in PR 1.

From the repository root:

```python
from AutoCua.saccade.platform_config import load_platform
from AutoCua.saccade.platform_registry import list_platforms

platform = load_platform("dext")
procedure = platform.procedure_path.read_text(encoding="utf-8")
platforms = list_platforms()  # sorted, validated immutable configurations
```

`root=Path(...)` supports isolated synthetic fixtures. Invalid registered
configurations raise an error instead of being enabled or silently skipped.
Procedure content is referenced by path, without a second cached copy in the
registry. The sole Dext navigation procedure is the initially empty UTF-8 file
`AutoCua/default_skills/web/domain_skill/dext.md`. The temporary
`platforms/dext/agent.md` is retired; no fallback procedure is loaded.

## Domain manifest contract

The existing native `domain_skill/skills.json` format remains a JSON object
mapping `hostname[/path]` to a simple Markdown filename. Filenames match
`[A-Za-z0-9][A-Za-z0-9_-]*\.md`. Keys use exact canonical hostnames, optionally
followed by a path. Paths permit ASCII letters, digits and
`/-._~!$&'()+,;=:@`; encoded paths, wildcards, duplicate slashes and dot segments
are rejected. A scope matches its path or slash-separated descendants:
`docs.google.com/spreadsheets` matches `/spreadsheets/d/id` but never
`/spreadsheets-evil`. Trailing scope slashes are equivalent; duplicate keys or
equivalent scopes reject the manifest. Subdomains require explicit entries.

Current browser URLs are parsed with the existing Rust `url` dependency.
Only HTTP(S) with no credentials and default ports can select domain knowledge.
Queries and fragments do not widen hostname or path scopes. Ambiguous encoded
paths cannot select path-scoped knowledge; host-only scopes still support
encoded record identifiers. `app.dext.com.evil.test` never selects Dext.
The Web loop already supplies the scanner's actual current URL each step.
An empty procedure adds no empty domain block; generic Web skills still work.

Python validates the complete installed manifest and its targets when loading
a platform. Rust validates the manifest and its directory at run initialization,
then reads only procedures applicable to the actual current URL. An invalid
manifest disables domain injection globally. A missing or unsafe applicable file
suppresses the entire current domain block, including any overlapping applicable
procedures; unavailable files for unrelated sites do not disable a healthy site.
Restoring an applicable file makes its content available on the next prompt read.
Files must be UTF-8, with limits of 64 KiB for JSON and 256 KiB per procedure.
Symlinks and Windows reparse points are rejected on applicable prompt reads,
so a replaced unsafe skill is not injected.
These filesystem checks assume a trusted local installation; they are not a
sandbox against hostile concurrent filesystem modification.

For a registered platform, the native procedure's whole-host mappings must
exactly equal `allowed_hosts`. Configuration or manifest changes alone cannot
silently introduce another host. Domain knowledge never grants tool rights.

## Dext deployment verification

On 10 November 2026 the public
[Dext login page](https://app.dext.com/login) and
[Dext's address migration documentation](https://help.dext.com/en/articles/605229-how-to-update-your-dext-bookmark-and-saved-passwords)
confirmed `app.dext.com` as the main web address. The initial configuration
therefore keeps only `https://app.dext.com/login` and host `app.dext.com`.
There are no sanctioned identity-provider or legacy-host redirects in this
configuration. Before a real run, the operator must verify the intended tenant's
post-login URL in visible Chrome. Unexpected redirects require review and an
explicit configuration plus manifest update; they are never inferred here.
No authenticated tenant session or accounting write was performed for PR 1.

## Local data and verification

`platforms/*/data/` is ignored by Git and excluded from package artifacts.
Git ignore is not a security boundary. Keep real references, credentials,
profiles, PDFs and operational journals local; use synthetic fixtures in tests.

Maturin explicitly includes only `platforms/*/platform.json` beside the installed
`AutoCua` package. Native Web skills already ship inside `AutoCua/default_skills`.
The same paths therefore work in source and in an extracted or installed wheel;
the loader needs no source-checkout fallback or duplicate configuration. Customer
data remains excluded from both wheels and source distributions.

```powershell
maturin build --locked --interpreter python --out .cache/review-wheels
$env:SACCADE_TEST_WHEEL = (Get-ChildItem .cache/review-wheels/*.whl | Select-Object -First 1).FullName
python -m unittest discover -s tests -t . -v
cargo check --locked --manifest-path AutoCua/web/Cargo.toml
cargo test --locked --manifest-path AutoCua/web/Cargo.toml
npm.cmd --prefix AutoCua/ui run typecheck
npm.cmd --prefix AutoCua/ui run build -- --outDir ../.cache/review-ui-build
git diff --check
```

The wheel regression tests compare packaged resources with source, exclude
local data and legacy procedures, then extract into a fresh directory and use
an isolated Python process to load Dext and import the native Web extension.
Without `SACCADE_TEST_WHEEL`, those three artifact tests report an explicit skip.
Empty-procedure onboarding uses isolated fixtures; the repository test permits
the production procedure to contain approved content.

Rust uses the repository's pinned toolchain from `rust-toolchain.toml`.
Windows symlink tests require Developer Mode or the symlink privilege;
Python reports a skip when the privilege is unavailable.
