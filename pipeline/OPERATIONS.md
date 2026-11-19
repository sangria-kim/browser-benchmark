# Daily candidate operations

The daily runner defaults to collection and data validation. The report job reads
a validated collection and writes selections and standard reports. Each job has
a separate run ID. Dashboard publication and package export have independent
entry points. Keep the existing schedule until the owner approves the transition.

Install `schemas/requirements.txt`. Use Python 3.9 or later, Git, and a local
filesystem that supports `flock`, durable file writes and atomic file replacement.
Keep the state directory outside the repository, on persistent private storage.
Retain it through retries and recovery. Restrict access to the execution account.

```sh
python -m pipeline.run_daily --private-dir /private/browser-state \
  --run-id baseline-001 --kind all --origin baseline
python -m pipeline.run_daily --private-dir /private/browser-state \
  --run-id baseline-001 --resume
```

The default is shadow mode. It never changes public source data. It freezes all
managed input files, including code, rules, schemas and configuration. Every stage
runs from that snapshot in a separate interpreter. Successful stage checkpoints
include output hashes. A failed or interrupted stage restarts from its preceding
snapshot. Completed stages are reused only if their hashes still match.

`--cutoff` fixes the collection window. After accepting the collection into a
worktree, pass its private run directory to the report job. Choose an explicit
evaluation and report time at or after collection. Reuse that time for a replay.
The report date uses Asia/Seoul. Use `--previous-cutoff` after missed report days.

```sh
python -m pipeline.run_daily --job report --run-id report-001 \
  --private-dir "$PRIVATE_STATE" --collection-run "$PRIVATE_STATE/baseline-001" \
  --report-cutoff "$REPORT_CUTOFF"
```

Both jobs default to private output. Publish each accepted job separately.
The report job checks the collection fact hashes against its input snapshot.
A later collection can use the same `--collection-run` option to carry forward
last successful source cutoffs and hashes. A partial source keeps its preceding
watermark. For v1 Chromium runs, use the revision from the checksum-pinned input
bundle when its coverage matches. Otherwise carry the confirmed sources forward
and mark the handoff partial. Report times must follow the collection cutoff.
Without a preceding checkpoint, its last successful window is unknown.

Browser HTTP responses and source revisions stay in private collector caches.
Chromium pins one commit and resumes that commit. The default Chromium budget is
20 new files and 20 tree requests per call. Use `--max-files`, `--max-trees`, and
`--sample-path` to set an explicit bounded scope. These limits never establish
complete coverage. `--kind browser --source firefox-beta` is a small official
sample, not a full browser baseline. `--chrome-bundle` and `--responses` replay
frozen private inputs; a replay is not fresh network collection.

To use repaired collector code, start a new run. Never edit the old run's frozen
code or checkpoint. `--browser-cache-from /private/old-run/collection/browser`
copies only raw responses after SHA256 checks at the same cutoff. It does not
copy completion status, parsed records, errors, or document-completion judgments.
Every document is parsed again. For Edge policies, cached responses must retain
their original observation timestamps. Start a fresh collection if an older
Edge cache lacks capture times. The new run freezes a private handoff manifest.
Mutable ChromeStatus and Google blog API pages are refreshed as one enumeration so an old
partial page set is not mixed with newly shifted pages.

`--reviewed-attributions /private/review.json` accepts a private mapping from an
exact document SHA256 to a list of reviewed attribution-line SHA256 values. It is
used only for the known Chrome Releases footer position. The public record keeps
the source location and content hash and replaces the reviewed personal text with
an attribution omission label. A different document or line hash remains
unresolved. A short final sentence alone is never sufficient review evidence.
Keep the review input private and inspect the original evidence before adding a
hash. The runner freezes and verifies this input like other private decisions.

The collection period starts on 2026-01-01. Printed publication dates retain the
publisher's calendar day; no time or timezone is invented for date-only evidence.
Private source status separates in-period, before-period, after-cutoff, and
unknown-date observations. Unknown dates are not proof of a 2026 change.
Chromium is observed at actual collection time, not backdated to the browser
window cutoff. The current-existing experiment scope requires a separate January boundary/current-state
comparison. A pinned current scan alone does not complete that temporal projection
and does not establish intervening deletion/revert history. The timestamp boundary
is 2026-01-01T00:00:00+09:00 (2025-12-31T15:00:00Z).

To continue partial source enumeration, use the same run ID with
`--resume --retry-collection`. This keeps the base inputs and pinned source caches,
rebuilds the private collection and validation snapshots. Report jobs read the
accepted data separately. Existing standard report revisions remain immutable.
Do not retry an already published run; start a new run after its commit.
Use `--previous-bundle` to retain the preceding Chromium handoff on a new revision.

The default evaluator uses public deterministic rules. It does not call a model.
An actual model worker can supply `--decisions` and its real `--model-id`; both are
required together and copied into private pinned inputs. Missing or invalid
answers remain evaluation failures. Last good public judgments are retained.

## Candidate review and publication

Exit 0 means complete coverage for the registered browser and Chromium scope.
Exit 2 means a valid partial candidate. An exception or nonzero worker failure is
an execution failure. Inspect private `state.json` and stage logs to distinguish
these states. A partial report cannot claim that no changes occurred.

The final stage checks the data graph. Dashboard payload checks run with the
dashboard build. Export checks run on the selected real Git commit.

Review the candidate under the private `validate` directory. To publish its
managed data and generated reports to a clean worktree:

```sh
python -m pipeline.run_daily --private-dir /private/browser-state \
  --run-id baseline-001 --resume --publish
```

Publication requires a clean starting worktree and unchanged starting inputs,
Git HEAD, rules and code. A dirty tree is permitted only for shadow validation.
If inputs changed during collection, start a new run. Do not discard the edits.
Publication defaults to complete candidates. To deliberately accept useful
partial evidence after review, add `--allow-partial --publish`. The status and
report remain partial; this option does not claim complete collection.

The runner changes only `data/` and `reports/generated/`. It never deletes accepted
files. A failed collection or evaluation can produce a partial private candidate;
public data remains unchanged unless explicit partial publication is requested.
Graph validation failure prevents publication of the candidate.

After publication, follow repository branch rules: validate, fetch, integrate
concurrent work, commit to the work branch and open or update its PR. Leave merge
to the owner. Export again from the actual final commit with
`scripts/export_dataset.py`. Dispatch the dashboard workflow from reviewed `main` to rebuild Pages. Keep the consumer ref and imported real SHA explicit.

## Recovery and limits

A per-run lock protects private checkpoints. All publishers use a common repository
lock during recovery and publication. It records the pending journal location.
A durable write-ahead journal records every changed path and a checksum-verified
backup. The next publisher rolls back an interrupted publication before writing.
A crash after the journal marks publication complete is treated as completed
publication, even if the last checkpoint update was interrupted.

Recovery checks all paths before any rollback. If an unrelated edit or corrupt
backup is found, it stops and retains the journal. Reconcile those bytes manually;
do not delete the lock pointer or private backup to bypass recovery. Keep private
state and the host temporary lock directory through an interrupted publication.
The lock is local to one host and account. Multiple hosts/accounts must use a
single external writer service. Uncooperative editors can race advisory locks;
stop other writers for publication. Public multi-file replacement is not an atomic
read snapshot. Readers must use a committed Git revision or the verified exporter
snapshot, not a working tree while publication is in progress. Filesystem or disk
corruption and deletion of recovery state require manual recovery.

Connect an existing scheduler only after checking its execution environment. It
must be able to check out the repository, execute Python/Git, access official
sources and retain private state. A hosted chat task cannot be assumed to access
local files. Preserve its existing schedule, model and notification settings until
those settings are inspected. Do not create a second recurring job as a substitute.

## Edge policy pilot

Use a full 40-character commit ID. After the owner merges the shard migration,
use its actual main commit. Before that merge, use the local candidate only
for a private comparison. The baseline run must have complete Edge coverage.
Its verified policy bytes must match that commit, including all history.
The initializer accepts the single-file snapshot from before the shard split.
A checkpoint with observed IDs establishes which items were present at that cutoff.
If those IDs are unavailable, the first complete comparison records observations
and compatibility evidence. Semantic comparisons start from that observed set.
For positional units, compare full normalized content and duplicate counts under
the official page URL. Reconcile identical content that moved to another key.
Store the source revision for each content difference. Handle independent anchors
as individual items, including on pages that also use positional keys.


```sh
BASE_TIP=$(python -m pipeline.edge_delta --store "$EDGE_STORE" init \
  --commit "$BASE_SHA" --run "$LAST_GOOD_RUN")
python -m pipeline.run_daily --job collect --private-dir "$PRIVATE_STATE" \
  --run-id edge-pilot --source edge-policies --kind browser --origin daily \
  --collection-run "$LAST_GOOD_RUN" --cutoff "$CUTOFF"
TIP=$(python -m pipeline.edge_delta --store "$EDGE_STORE" compare \
  --parent "$BASE_TIP" --run "$PRIVATE_STATE/edge-pilot")
python -m pipeline.edge_delta --store "$EDGE_STORE" restore --tip "$TIP" --output "$NEW_SNAPSHOT"
```

The Edge-only collection returns 2 for partial global coverage. Check its Edge
status before comparison. If that source is partial, retry the same run and
cutoff with `--resume --retry-collection`. Compare reads the validated full
collector output and the private observation set. It performs no network requests.
Preserve the verified tip separately. Use it as the parent of the next interval.

Each receipt identifies the source, parent, window, resulting inventory and
content-addressed files in application order. A successful no-change window
has a receipt and no change file. Evidence-only updates retain document hashes
and the revision tails needed to reproduce historical references. A removal
records absence from a completely parsed version of the same official page.
An absent page cannot remove a policy. Retired records remain in compatibility
shards. A first observation with an earlier publication day is a backfill.
An undated first observation does not establish a new release.

Replay validates all hashes and writes a fresh private directory. Keep the last
verified tip and snapshot if any link is missing or invalid. Before public
cutover, verify historical reports and newsletter editions in a separate build.
Run `verify-commit --tip "$TIP" --commit "$SOURCE_SHA"` with the same store before
using that SHA for the dashboard or export. The command checks all reconstructed
shards against the actual Git blobs. Reproduce the 1.2 package from the owner-merged commit and exercise the
existing importer. Record local verification and the company Windows import
separately. The pilot writes only private receipts. Keep the full public shards
until consumer validation and owner review are complete. Compare
`stages.validate.result.largest_source_files` in consecutive collection checkpoints
to monitor all eight browsers. Extend to Safari, Brave and Chrome in that order
after the Edge pilot is stable.
