# Internal data import contract 1.1

Import public data into a dedicated subtree of the company repository. Write a new
commit on the company's own history. Do not mirror public commits or branches.
The package contains no workflow or dashboard execution code. This avoids changing
`.github/workflows/dashboard.yml` and does not require workflow-write permission.
The company keeps its own workflows, dashboard, schedules and assessments.

## Source and trust

Choose `main` for owner-reviewed data or `work/browser-benchmark` for an
agent-validated candidate. Record the choice and the exact imported commit.
A work-branch commit is not owner approval. The initial source collection remains
a bounded sample; exported counts do not establish complete browser or Chromium
coverage. Read each report's completeness and evidence limits.

Use a separately reviewed installation of `scripts/export_dataset.py`, its local
`config/export-allowlist.json`, schema validators and their Python dependencies.
Run that installation against a fetched public repository. The package contains
schemas as data, but the importer uses its trusted installed validators. It never
executes Python, JavaScript, workflows or other code from the package. Install
`jsonschema` with the trusted checkout's `schemas/requirements.txt`. Python 3.9 or
later is required. The importer uses POSIX locks and atomic rename on a local
filesystem. Windows and network filesystems require separate validation.

The exporter resolves the chosen Git ref to one commit **before reading source
files**. It reads the Git tree and blob objects at that commit. Dirty working files,
untracked files and later branch movement cannot enter the package. The committed
allowlist must match the trusted tool's policy. A policy change requires review and
a matching tool update. No self-referential commit SHA is stored in source data.

`manifest.json` records contract 1.1, source repository, source ref, source SHA,
link policy, and each file's relative path, kind, SHA-256 and byte length. Its own
SHA-256 is returned by the exporter, outside the manifest. Retain that digest from
the trusted export result. A checksum supplied by an untrusted sender is not proof
of origin. When receiving a package through another channel, reproduce the export
from the fetched expected Git commit and compare manifest hashes, or authenticate
the handoff through a company-approved mechanism. Do not obtain both the expected
SHA and manifest digest solely from the incoming package.

The source repository URI is provenance text, not authentication. The importing
operator selects the known public remote. Git commit IDs bind source content;
the separately trusted manifest digest binds the exact exported inventory.

## Included data

[The allowlist](../config/export-allowlist.json) has positive path rules with fixed
extensions for canonical data. It lists legacy files and interpretation documents
by exact path. New legacy paths require explicit review. It contains no blanket
`**/*` rule. It includes:

- All stored source items, revision evidence, feature and experiment catalogs.
- Feature and experiment events, original legacy events and fact revision archives.
- Immutable assessments, current selections and all dated selection snapshots.
- Current report metadata, all immutable metadata and Markdown revisions, and
  original manual reports and indexes.
- Original feature, release and experiment documents, the legacy compatibility
  index, alias corrections and public Korea support evidence.
- Interpretation documents, public source registries, PM rule data, schema JSON and
  exact normalization, selection and reporting README documents. These README files
  explain the data; no pipeline execution code is included.

`.github/`, dashboard code, scripts, collectors, tests, credentials, private state,
locks, caches and operation logs are excluded. Canonical records pass their schemas
and reference checks. Legacy JSON must parse. Legacy compatibility hashes must
match their original files. Known credential signatures and credential-bearing
JSON keys are rejected even inside allowed paths. These checks do not prove that
arbitrary prose is public. Keep the repository's public-data review boundary;
never place internal PRDs, private analysis, identifiers or logs in an allowed
record or document. A filename blacklist alone is not that boundary.

The manifest file inventory must exactly match the package. Import rejects unsafe
paths, dot components, traversal, case-insensitive aliases, symlinks, special files,
executable files, extra files, missing files, wrong lengths/hashes, unexpected kinds
and unsupported contract versions. Missing `jsonschema` is a hard error.

## References and history

Paths remain relative and bytes are preserved. This exporter selects the
**preserve-relative** option of
`preserve-relative-allowlisted-or-immutable-source-url`. It does not rewrite links.
Every local Markdown, reference-style and HTML `href`/`src` target must exist in the
allowlisted package. Missing or excluded targets reject the export. URL fragments
are retained; anchor spelling and remote HTTP availability are not checked.
Generated report Markdown must match its frozen metadata renderer.

The current graph loader uses current globs only. In particular, do not combine
all selected archives into one selection history. Each snapshot contains its own
history and can repeat change IDs. Validate each separately. Likewise, report
revisions share a logical report ID. The current graph contains current metadata;
validate each archived report separately against facts and selection history.

Report evidence identifies exact stored source revisions and hashes. Reports also
retain assessment, subject, selection and documentation paths. The importer checks
these references, current/archive report equality, prior report revisions, frozen
assessment fields, source evidence snapshots and original legacy provenance hashes.
Historical selection is judgment-time history; it does not prove that today's
normalized facts existed in the repository on that date. Internal assessments must
use a separate namespace and must not overwrite public source assessments.

## Prepare an import

The following shell example assumes a trusted tool installation, an existing public
fetch cache and an existing company checkout. Set the four paths for that environment.
Keep `import_private` outside the company checkout and public repository. Use a fresh
package output path on each export. No internal URL or credentials are needed by
the exporter.

```sh
set -eu
trusted_tools=/opt/browser-benchmark-tools
public_cache=/srv/cache/browser-benchmark
company_checkout=/srv/company-repository
import_private=/srv/private/browser-benchmark-import
source_branch=main
source_ref="refs/remotes/origin/$source_branch"
managed="$company_checkout/vendor/browser-benchmark"
package="$import_private/package-candidate"

mkdir -p "$import_private"
git -C "$public_cache" fetch origin "$source_branch:$source_ref"
source_sha=$(git -C "$public_cache" rev-parse --verify "$source_ref^{commit}")
python "$trusted_tools/scripts/export_dataset.py" export \
  --repository "$public_cache" --ref "$source_ref" \
  --source-repository https://github.com/sangria-kim/browser-benchmark \
  --output "$package" > "$import_private/export-result.json"
manifest_sha=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["manifest_sha256"])' \
  "$import_private/export-result.json")
python "$trusted_tools/scripts/export_dataset.py" verify \
  --package "$package" --expected-commit "$source_sha" \
  --manifest-sha256 "$manifest_sha"
```

Stop on any command failure. In an automation script use `set -eu` and a unique
private candidate directory. The expected SHA check also rejects a ref that moved
between the operator's `rev-parse` and the exporter's pin. Repeat with a new candidate
path after examining the cause. These commands do not collect sources or schedule
future work.

Initialize the managed subtree once. It must be empty. Initialization creates an
explicit ownership marker and a snapshots directory. Never initialize the company
repository root or a directory that contains company files.

```sh
python "$trusted_tools/scripts/export_dataset.py" init --managed "$managed"
```

Then validate, copy and activate. Use the same private lock directory for every
writer to this managed subtree. Serialize the full import and company commit.

```sh
python "$trusted_tools/scripts/export_dataset.py" import \
  --package "$package" --managed "$managed" --private-dir "$import_private" \
  --expected-commit "$source_sha" --manifest-sha256 "$manifest_sha"
snapshot=$(python "$trusted_tools/scripts/export_dataset.py" resolve --managed "$managed")
git -C "$company_checkout" add -- vendor/browser-benchmark
git -C "$company_checkout" diff --cached --stat
```

Review the staged change. Check that it contains only the managed subtree. Run the
company dashboard's own tests against `$snapshot`. Create a company commit with the
source SHA and chosen ref in its message or import metadata. Use the company's
normal pull-request process. Do not push the public work branch into the company
remote. No real company repository or authentication was available for the fixture
validation of this contract; the company must verify its actual CI and dashboard.

## Atomic activation and failure behavior

The managed layout is:

```text
vendor/browser-benchmark/
  .browser-benchmark-import.json
  current.json
  snapshots/<manifest-sha256>/manifest.json
  snapshots/<manifest-sha256>/data/...
  snapshots/<manifest-sha256>/reports/...
```

`current.json` records contract version, source SHA, manifest digest and the exact
content-addressed snapshot path. The reader loads this pointer once per request or
build and resolves all data paths beneath that snapshot. Do not read a mutable
`data/` directory at the managed root, cache two different pointers during one
request, or scan every old snapshot as current data. `resolve` validates the pointer
and the complete active package before returning the snapshot path.

The importer validates the incoming package, stages a private copy and validates
that copy again. It copies into a unique temporary directory under `snapshots/`,
verifies and flushes its files and directories, then atomically renames the package
to its final digest name. It then atomically replaces `current.json` on the same
filesystem. This one replacement is activation. Two directory renames are not a
single atomic transaction. Existing snapshots remain available to readers that
already resolved them. A failed verification or failed pointer replacement leaves
the old pointer and accepted snapshot intact. Repeating an identical verified
package returns without changing the pointer. An unused verified snapshot from a
failed activation can be reused on retry.

A process or machine crash before pointer replacement cannot expose a partial new
dataset through the old pointer. A crash during the copy can leave an unreferenced
`.snapshot-*` temporary directory. Retry uses a new temporary directory and does
not depend on that incomplete copy. A final digest directory is published only
after verification and flushing. Existing final directories are always verified;
invalid or partial final directories from older importers fail closed and require
operator inspection. Never remove an active snapshot. Unreferenced temporary
directories may be removed under the same import lock. Filesystem corruption,
failed durability guarantees and writers using different locks are outside this
local-filesystem guarantee. A
failure after the atomic pointer replacement may require inspecting the pointer to
establish whether activation completed.

Deleted source files disappear only from the new active snapshot. Old snapshots
remain for audit and rollback. Tombstones remain ordinary source data. The importer
does not delete or edit company files, workflows, dashboard code or any sibling of
the marked subtree. Snapshot garbage collection is a separate company retention
operation. Lock files, initial staging candidates and export results stay private;
the final copy uses a transient `.snapshot-*` directory in the managed subtree;
the transient pointer file is removed after success or a handled failure. Do not
commit a failed transaction's temporary files.
