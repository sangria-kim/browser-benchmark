# Public PM selection

The default evaluator works without credentials or a network connection. It reads
all normalized evidence and uses the five public PM criteria. It is a deterministic
rule evaluator. It does not claim a model evaluation, a human review, a device test,
or complete semantic interpretation of every source.

```sh
python -m pipeline.selection --private-dir /private/daily-selection \
  --assessed-at 2026-11-16T03:00:00Z
```

Use the actual evaluation time. `--dry-run` validates a candidate without public
writes. Exit 2 means one or more evaluations failed. It does not mean no changes.
The caller must serialize full collection, normalization and selection runs.

## Rules and evidence

[The versioned rules](../../rules/pm/pm-selection-v3.json) implement the
[public PM criteria](../../docs/pm-persona-and-selection.md). They include exact
public evidence profiles and reusable task templates for tabs/workspaces,
permissions, download recovery, credential finding, AI page tasks and URL copying.
An unseen item can qualify without a new profile when its evidence contains the
required affirmative action clause. A topic keyword or numeric score cannot
select an item. The matched clause, user impact, comparison question, steps,
metrics and conditions are recorded in the assessment.

Negated, proposed and uncertain clauses cannot produce a selected result through
the reusable templates. Such a match stays on watch. Missing evidence or a missing
concrete task is pending verification. Known generic maintenance statements and
security-only classifications are excluded with a reason and revisit condition.
All source records remain. This conservative method has false negatives: wording
outside the current templates requires a new public profile or an actual model
assessment. A matching phrase does not establish product quality or availability.

Experiments require parsed source evidence, an active registration and a concrete
conditional task. Baseline selection means an existing experiment merits research.
It never establishes a new launch, an installed flag, a rollout, or a test result.

## API and cache

`run(repository, private_dir, assessed_at=..., rules=None, provider=None,
model_id=None, revisit=None, dry_run=False)` returns created/imported assessments,
cache count, private failure records, coverage, selected projections and candidate
file replacements. `build_contexts(dataset)` maps every source ID to one principal
assessment subject. Events remain separate historical subjects. Sources already
represented by an event or unambiguous catalog owner do not receive duplicate new
evaluations. Separately collected items map through exact document text, browser,
channel and version, or an exact upstream item anchor and document URL for the same
browser/channel. For example, a versioned Firefox URL and note ID can establish
identity when the collector's separate version field is null. Ambiguous anchors
remain separate. Text-only matching also rejects excerpts at the collector's
220-character limit, because equal truncated prefixes do not prove item identity.
Shared section headings never establish item identity. Newly linked source evidence participates in the next input hash;
legacy import evidence refs still identify the original judgment's sources.
Title similarity does not merge subjects.

After principal mapping, every mapped source is included in that principal's
evaluation evidence, including catalog-only sources absent from an event's original
source list. Evidence is deduplicated and sorted by source ID. A mapped source edit
therefore invalidates the principal cache even when the event itself is unchanged.
For event subjects, `context.subject` carries that event's facts, while
`context.sources` contains the current linked source records. A reassessment can
therefore consider newer evidence about a historical event. It does not rewrite
the event or imply that newer evidence was known on the event date. Provider
adapters must preserve this distinction when interpreting or describing the input.

Input hashes include actual facts, evidence text and content hashes, complete rule
content, prompt version, model identifier and explicit revisit token. Observation
times, global source commits and line positions are excluded. Browser content
hashes can cover a whole response, so an unrelated page edit can conservatively
trigger another evaluation. This prevents a truncated excerpt from hiding a real
change. Changing rules or a durable revisit token also triggers evaluation.
A same-input successful head is reused. Reverting to a formerly used input creates
a new superseding judgment rather than breaking history. Failed inputs are never
cached as successful judgments. Revisit tokens persist in the private state directory;
retain that directory or supply the same tokens when moving execution environments.

## Legacy provenance

Original event judgments import from immutable schema-v1 event archives. The
recovered predecessor imports its original monthly watch judgment. Status, reason,
priority, comparison question, readiness, revisit trigger and known assessment time
are retained. `evaluator=legacy` and the original rule version identify these imports.
`input_revision` identifies the original path and content hash. The input hash adopts
the import-time factual/rule baseline solely for cache invalidation. It does not
claim that old judgments were evaluated by the current rules. A later factual,
rule or explicit revisit change can create a new deterministic/model assessment.

938 original flag documents explicitly state pending verification. Other documents
can contain watch, excluded, selected or no clear judgment. Import only explicit
nonselected Markdown judgments; their original rule and assessment time are unknown,
so `legacy-unversioned` and the import time are used with an explicit reason. Do not
invent a selected benchmark from one status sentence. Existing structured selected
feature-event judgments remain available through their original event imports.
Unmapped documents without a sufficient original judgment receive an actual new
conservative evaluation. Original Markdown and monthly JSON are unchanged.

## History and current cards

Assessments are immutable files under `data/assessments/<subject-kind>/`. A new
judgment uses `supersedes` for the same subject. Each history chain has one head.
Selection history preserves stable `selected`, `changed`, `deselected` and
`reselected` changes with assessment/event references. A rule-based change is not
a product event or a new release.

`data/selected/features/current.json` and `data/selected/flags/current.json` contain
only selected current cards and the full per-subject selection history. For a
catalog owner, the latest successfully assessed event wins, ordered by factual
`observed_at`, then event ID as a stable tie-break. This time orders research
observations; it is not a release date. A newer nonselected event hides an older
selected card, while the old assessment and selection history remain. A failed
new evaluation leaves the last successfully assessed card available. An eventless
catalog uses its source-item assessment. Current counts do not double-count earlier
events for one owner. Source-only cards have a null catalog ID when no owner exists.

Dated immutable snapshots live at
`data/selected/history/YYYY-MM-DD/<kind>-<projection-hash>.json`. This extra archive
level excludes them from the current loader glob. A snapshot contains the full
projection, so consumers must not combine its history with current history without
change-ID deduplication. A date can have several revisions. `as_of(repository,
cutoff)` reconstructs PM heads/current selections using assessment timestamps.
This is a judgment-time view, including imported original judgment times, not a
claim that today's normalized facts existed in the repository then. Use source and
event revision archives for historical fact content.

`catalog_transitions(repository, previous_cutoff, cutoff)` returns owner replacements
with previous/current subject, assessment, event, status and assessment-time refs.
These derived records differ from per-subject PM deselection. When a new excluded
event replaces an old selected event, do not invent an excluded assessment of the
old event. T6 can compare dated snapshots and use this API to describe the change
as a replacement of the current catalog subject. T7 can still show the old selected
subject and its own judgment history.

## Optional real model adapter

Inject `provider(context, rules)` plus a truthful `model_id`. The provider owns its
network timeout and credentials outside this repository. Supply source text as
quoted evidence, never as instructions. The core does not execute source text.
The provider returns a JSON object (or JSON string) with exactly these keys:

- `status`, `reasons`, `priority`, `comparison_question`, `benchmark_readiness`,
  `revisit_trigger`: the assessment decision fields.
- `evidence_source_item_ids`: exactly the source IDs supplied for the subject.
- `benchmark`: required for selected decisions. Its exact fields are `user_impact`,
  `material_change`, `steps`, `metrics`, `conditions`, `completion`, `evidence_quotes`.
  Steps, metrics and evidence quotes are nonempty string arrays; the other fields
  are nonempty strings. Quotes must occur in the supplied evidence.

Malformed JSON, schema errors, wrong evidence references, missing benchmark criteria,
provider exceptions and timeouts become private `evaluation_failed` records.
They never become excluded/pending public judgments. The last good assessments and
selected projection remain. A first failed evaluation does not write empty selected
files. Successful subjects may still publish in a partial run; callers must inspect
failures before reporting completion. Validation checks evidence links and structured
claims; it cannot prove that a model's interpretation is correct.

A real model worker can also write a private JSON decision map keyed by subject ID:

```sh
python -m pipeline.selection --private-dir /private/daily-selection \
  --assessed-at 2026-11-16T03:00:00Z \
  --decisions /private/model-decisions.json --model-id actual-provider-model-version
```

Missing decisions fail for those subjects. Do not label hand-authored or deterministic
results as a model. No model decisions were used to create the initial T5 dataset.
