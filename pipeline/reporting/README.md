# Daily selected changes

Generate a report from stored public facts and PM judgments. No network fetch or
model call occurs here. Run collection, normalization and selection first. Serialize
these stages and report publication with the same private transaction directory.

```sh
python -m pipeline.reporting --private-dir /private/daily-browser \
  --date 2026-11-16 --cutoff 2026-11-16T03:05:09Z \
  --collection partial --evaluation complete
```

`collection` and `evaluation` default to `unknown`. Supply `complete` only after
checking the corresponding private run result. `partial`, `failed` and `unknown`
never produce a no-change conclusion. The CLI exits 2 for any incomplete stage,
including a successfully written partial report. A publication error is an error,
not an empty or no-change report. No private logs, run IDs or error text are stored.

## API and time

`run(repository, private_dir, day=..., cutoff=..., previous_cutoff=None,
collection='unknown', evaluation='unknown', dry_run=False)` returns `report`,
`created`, JSON `replacements` and `text_files`. `render(report)` renders the frozen
public snapshot. `window(day, cutoff, previous_cutoff=None)` validates the KST day.

The default window includes midnight in Asia/Seoul through the inclusive cutoff.
A caller can supply an earlier previous cutoff to recover a missed day. The cutoff
must include a timezone and fall on the report date in Korea. Equivalent timezone
strings normalize to the same UTC cutoff. A daily logical ID is `daily-YYYY-MM-DD`.
Changed inputs or a later cutoff append a revision. Same inputs reuse that revision.
A current cutoff cannot move backwards; read the stored earlier revision instead.

New selection, reassessment, deselection and reselection use T5's actual selection
change IDs. Unchanged selected lists are linked, not repeated. Multiple judgments
of one subject within the window appear in one section, with the last judgment and
all earlier change IDs. Events for different releases or platforms remain distinct.
Catalog owner replacements use separate typed `catalog_transitions`, with old/new
subjects, judgments and statuses. A replacement is not a fabricated deselection of
the earlier subject. A newly assessed excluded event can replace a selected card.

`discovered_at` is the selection change time. `observed_at` is the fact observation
time. `announced_at` and `effective_at` retain known public dates or null. Neither
observation nor selection time is called a release date. Baseline/backfill selection
is research of existing material. Source experiments do not establish product
availability, Korea support or device test results. Retirement plans retain their
fact type and known future effective date.

## Stored contract

Canonical records use schema 2 and public dataset contract 1.1. Optional report
extensions retain compatibility with existing schema-2 report fixtures. Generated
reports contain public completeness, outcome, item snapshots, source revision/hash
references, linked selection snapshots and typed catalog transitions.

- `data/reports/current/daily-YYYY-MM-DD.json`: latest metadata per logical report.
- `data/reports/history/YYYY-MM-DD/revision-N.json`: immutable metadata revisions.
- `reports/generated/YYYY-MM-DD/rN.md`: immutable Markdown revisions.
- `reports/generated/YYYY-MM-DD/newsletter-rN.json` stores the Korean one-page edition, its creation date in Korea, the collection date and the report revision. The dashboard archives editions by both dates. The next report also saves older card days without a report as newsletter-r0.json. Unsaved previews do not have a publication date.
- `reports/generated/README.md`: latest revision index.
- `data/selected/history/YYYY-MM-DD/<kind>-<hash>.json`: fixed judgment-time snapshots.

Only current report metadata joins the graph loader. History files therefore do
not create duplicate report IDs. JSON, snapshots, Markdown and the generated index
publish together through the rollback-protected storage publisher. Existing manual
reports are never replaced. The transaction protection has the same power-loss and
single-private-lock limitations as normalization; it is not a database transaction.

Item snapshots retain assessment rule versions, public reasons and comparison
questions, fact types/dates, benchmark candidates when structured data exists, and
source evidence revision IDs/hashes. The report generator's own `rule_version` is
separate. Local links identify source records, subjects, immutable assessments,
selection changes, documentation when present, and fixed report/snapshot files.
T8 can retain allowlisted relative links or rewrite them to the source commit.

Assessed event content is resolved by its semantic hash, including revision archives
when the current fact was corrected. Legacy event judgments resolve their original
archive/hash. Unavailable assessed facts stop generation. Source evidence uses the
latest stored revision at judgment time, or the earliest available evidence window
when an imported judgment predates materialization. Such a snapshot records public
evidence available by the report cutoff; it does not claim historical repository
materialization. The current record retains its source revision history. Archived
report metadata remains the exact record of what a report said.

## Initial materialization and downstream use

The initial 2026-11-16 report uses the bounded collection candidate. Collection is
`partial`; evaluation is `complete` for that candidate. It is not a full registered
source or Chromium definition baseline. It includes only actual selection changes
in the day, including source baseline selections, with their timing labels.

T7 should use `report.items` for item/report links, `related_change_ids` for combined
same-day judgments, and `catalog_transitions` for current-card replacement links.
The former selected subject and its immutable assessment remain accessible. Use
`details.workstreams`/`ai_related` only when known; do not infer product support
from source OS masks. T8 must include fixed report revisions, referenced selection
snapshots, source records with revision history, and assessment/event references.
