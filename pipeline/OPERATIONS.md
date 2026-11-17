# Daily candidate operations

Use `python -m pipeline.run_daily` as the only scheduled writer. Stop the old
writer before activation. Do not run the lower-level collection, selection or
report commands against the same public tree while this runner is active.
The runner does not create schedules, commit, push, open PRs or merge branches.

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

`--cutoff` fixes the collection window. Assessment time is the actual time that
assessment starts. Report cutoff and KST date are frozen when reporting starts.
Thus a long collection cannot backdate a new judgment to its start time. Resume
uses those stored values; it does not replace them with current CLI defaults.
`--previous-cutoff` supports a report window after missed runs. A collection that
crosses midnight uses its actual report completion day in Korea.

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
Every document is parsed again. The new run freezes a private handoff manifest.
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
invalidates downstream snapshots, and uses new actual judgment/report times.
Previously completed private stage snapshots are replaced. An existing public
report is preserved in the base and receives a new immutable revision when needed.
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

The final stage validates the whole graph, builds the dashboard, checks selected
and report payload consistency, and verifies a fixed-commit data export. That
commit exists only in the private validation checkout. Its SHA, package and
built document links are **validation only**. Do not send them to consumers or
claim they are published source provenance.

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
Whole-graph or export validation failure prevents all publication.

After publication, follow repository branch rules: validate, fetch, integrate
concurrent work, commit to the work branch and open or update its PR. Leave merge
to the owner. Export again from the actual final commit with
`scripts/export_dataset.py`. The existing workflow rebuilds Pages from reviewed
`main`. Keep the consumer ref and imported real SHA explicit.

## Recovery and limits

A per-user, per-repository global lock serializes runs even when callers choose
different private state directories. It records the pending publication location.
A durable write-ahead journal records every changed path and a checksum-verified
backup. A new run rolls back an interrupted publication before doing more work.
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
