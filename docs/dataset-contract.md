# Public dataset contract 1.2

This document describes the retained schema version 2 dataset. New collection follows the [browser feature policy](collection-policy.md). The source registry uses contract version 1.0.

## Temporal projection (1.2)

`temporal_scope` is optional on source items, catalogs and current events. It is
projection metadata, separate from immutable source snapshots and PM judgments.
Its `since` and `cutoff` identify the evidence window. `status` is `in_period`,
`before_period`, `after_cutoff`, `unchanged`, `unknown` or `context`.
Only `in_period` is eligible for the bounded current selection. An old record
without a reviewed date becomes context or unknown when the projection is applied.
That does not delete its ID, source snapshots, product events or assessments.

`basis` identifies publication, an item update, an endpoint comparison, a retained
explicit event date, or unknown evidence. `evidence_date` and `precision` distinguish
a printed day, a timezone-aware timestamp and a comparison interval. A timestamp
without timezone retains its printed day; it does not acquire an invented zone.
The observation time and HTTP document update time never prove a product change.

For Chromium, `baseline_revision`, `current_revision` and `change` identify the
same-parser endpoint result. `change` is added, changed, unchanged or unknown.
Unknown syntax, ambiguous correspondence and unresolved dependencies remain unknown.
A failed or incomplete boundary parse cannot prove that a current definition is new.
Generated Blink and Mojo definitions cite their public definition inputs. They do
not claim that a generated build output or installed feature was observed.

Selected outputs, new reports, and dashboard data carry optional
`collection_scope`, with the policy version, window and Chromium endpoint pairs.
`source_windows` lists each source's actual window. The aggregate `cutoff` is the
latest source cutoff, not a claim that all sources share one snapshot time.
Endpoint scopes also retain verified commit timestamps. A current commit after
its declared source cutoff is rejected. Fresh web retries retain their actual
observation time; they do not recreate a historical web snapshot.
Older report revisions stay fixed. A scope exclusion creates a new exclusion
assessment and selection-history entry where needed; it never creates a product
removal event. Parser identity corrections use evidence-backed alias records.

## Scope

[The source registry](../config/sources.yml) defines official sources for Chrome, Edge, Firefox, Safari, Brave, Whale, Opera and Vivaldi. It is JSON-compatible YAML. Load it with `json.load`; no YAML dependency is needed. The registry lists source bounds, parser names, discovery patterns and pagination. Channel and platform lists are not a cross product. Each item needs its own evidence. Unsupported scopes are explicit.

The requested browser period starts on **2026-01-01** and ends at the pinned cutoff. Use official item publication or change evidence. A whole-page update does not date every item on that page. Undated current facts and older accepted records remain context; they do not prove an in-period change. Date-only publications keep the publisher's printed day without an invented time or timezone. Daily collection covers the last 30 days for enabled sources except Brave, Vivaldi and Opera. Weekly reconciliation covers all enabled sources from the policy start date. A page/document limit is a circuit breaker. Hitting it leaves private coverage partial, not complete.

[The Chromium scope](../config/chrome-source-scope.yml) starts from one pinned public main commit. Enumerate the tracked source tree from a local checkout or Gitiles. A required-file sample cannot establish full-tree coverage. Keep the file list, parsing counts and coverage state private. Public records retain their own paths, hashes and revisions.

The requested experiment projection focuses on currently existing definitions with
an added or changed state since **2026-01-01T00:00:00+09:00**
(2025-12-31T15:00:00Z). Compare canonical definition semantics at the verified
boundary and current commits. Whole-file edits, line moves and parser corrections
are not product changes. A current source scan alone does not establish this
temporal comparison. Endpoint comparison excludes deleted/transient-only items
and exact A→B→A reversions; it is not a complete intervening edit history.

Keep these experiment kinds separate:

- `flag_entry`: desktop or iOS flag registrations, descriptions and expiry data.
- `base_feature`: feature definitions, including definitions with no UI flag.
- `command_switch`: command-line switch definitions. These are not UI flags.

Existing Chrome artifacts start at **2026-06-01**, with changes to `about_flags.cc`. Preserve them. They do not establish complete historical coverage for iOS, base features, switches or all metadata. The new catalog starts at the pinned baseline; unknown earlier definitions stay unknown. See the official [configuration guide](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/docs/configuration.md) and [expiry guide](https://chromium.googlesource.com/chromium/src/+/refs/heads/main/docs/flag_expiry.md).

## Record models

| Kind / schema | Meaning |
| --- | --- |
| [source-item](../schemas/source-item.schema.json) | Minimal public evidence for one item, with stable identity and revision snapshots. `parsed`, `unparsed` and `legacy` describe the evidence record, not run success. |
| [feature](../schemas/feature.schema.json) | Product-specific feature identity, aliases, source items and events. |
| [feature-event](../schemas/feature-event.schema.json) | A product change, channel/platform scope, before/after and source references. Existing compatibility selection fields are optional. |
| [experiment](../schemas/experiment.schema.json) | One flag, feature definition or switch. Source defaults, expiry and product-channel evidence are separate. |
| [experiment-event](../schemas/experiment-event.schema.json) | A definition change at an identified public revision. A baseline is not a launch event. |
| [assessment](../schemas/assessment.schema.json) | An immutable public PM judgment for a source item, feature event or experiment event. |
| [selected](../schemas/selected.schema.json) | A materialized current list plus an append-only selection change history. |
| [report](../schemas/report.schema.json) | A KST logical daily report, revision, cutoff, inputs and item references. Markdown stays in `reports/`. |

Null means no supported value. Use `unknown` only where the schema defines it or for unknown channel/platform values. `legacy` identifies retained evidence with incomplete original source enumeration. `partial` and `complete` are private collection coverage states; neither belongs on a source record. No assessment means not yet assessed. It is different from `pending_verification`, which is an actual judgment about insufficient factual evidence.

The schemas reject unknown top-level properties. Nulls and empty relation arrays are acceptable where specified. `scope`, `before` and `after` hold product facts only. Keep their keys stable. They must not contain execution output, credentials or copied third-party document dumps. Add fields through a reviewed contract revision; do not silently bypass validation.

## IDs and duplicate rules

IDs are case-sensitive opaque strings. Preserve all existing `feature_id` and `event_id` values. Consumers must read IDs from records, not derive them from filenames.

New IDs use a readable prefix and the first 24 hex digits of SHA-256 over canonical JSON identity fields. Canonical JSON means UTF-8, sorted keys, compact separators and no ASCII escaping. Detect a truncated-hash collision and fail; do not merge it. Dates of observation never participate in entity or event identity.

| ID | Identity fields |
| --- | --- |
| `source_id` | Stable registry key, such as `chrome-releases`. Migration may use the reserved `legacy` source; Chromium uses `chromium-source`. |
| `source_item_id` | Source ID, canonical document URL and stable item key. Prefer upstream ID, issue key or anchor. Keep the original key after text correction. |
| `feature_id` | Browser plus canonical feature key. Do not merge different browser products. |
| `experiment_id` | Experiment kind plus canonical flag ID or qualified symbol. Preserve aliases when a symbol moves. |
| `event_id` | Subject ID, change type, version, channel, sorted platforms and supported before/after facts. A source registration may also need its change revision. |
| `assessment_id` | Subject kind/ID, input hash, rule version and evaluator/prompt identity. Reuse a successful result for identical inputs. |
| selection `change_id` | Subject kind/ID, previous assessment ID, adopted assessment ID and action. |

Use durable upstream item identities when possible. An ambiguous match remains a separate item until evidence resolves it. Title similarity alone is insufficient. Translation duplicates retain separate source items and can point to one event. Beta to Stable, platform expansion, default change, plan to release, removal and restoration remain separate events. Source observation date changes do not create events.

Source revisions are append-only snapshots inside `revisions`. The last snapshot must match the current title, summary, evidence and dates. `revision_id` identifies the item plus its content hash and source revision. Reobserving the same content/revision retains the snapshot and first observation time. A source edit appends a snapshot. Keep original minimal evidence; do not retain whole pages. A disappeared or inaccessible source does not imply product removal.

A factual correction keeps its event ID and increments `revision`. Preserve the previous record in the event revision archive before replacing the current record. `correction_of` links a distinct correction event when one is needed; it does not authorize ID changes. The event archive is separate from the current-event glob. Alias correction records must retain old IDs, new targets and source evidence. A wrong merge must be recoverable from these records and the revision archive.

## Evidence and assessments

`published_at` or `announced_at` is the source publication date. `effective_at` is a separately supported product date. `observed_at` is a timezone-aware evidence observation timestamp. These fields are not interchangeable. `content_sha256` hashes the evidence input bytes before parsing. Source revision may be null for a web page, but the hash is required. For legacy imports with unavailable original bytes, hash the retained evidence and keep `record_status: legacy`; do not claim an original page hash.

An individual selection can cite the registered publisher's HTTPS URL. The source has
`record_status: reference`, `origin: reference`, and an `official-url:` item key. Its
`content_sha256` hashes canonical JSON with `kind: official_url`, `source_id` and
the normalized `url`. The original page bytes, publication date and excerpt are
unknown. The empty excerpt and null publication date stay intact on retry.
`observed_at` is the first observation of the reference. If classification selects
an observed item and revision, the feature pins that snapshot and its actual hash.

Individual selections carry an optional `feature_facts` object. Its slots are
`version`, `platform` (a list), `channel`, and `rollout_status`. Each confirmed
slot stores `value`, `source_item_id`, and `revision_id` for this feature. An
absent slot has no confirmed value. An empty object identifies a selection with
all four slots open. Older entries may omit the object. A shared source page can
support several features. Their facts are independent. Enrichment fills open
slots and preserves established values and the first confirmed citation.
An additional citation does not by itself establish a product change.

Browser collectors also store optional `item_content_sha256`. It hashes the full
item section and text before excerpt truncation. PM inputs use this digest instead
of the whole-document `evidence.content_sha256`; sibling edits and HTML comments
must not change an unchanged item's judgment. Raw document hashes remain evidence
integrity and provenance fields. Records without the item digest retain their
existing hash semantics, including Chromium item-level hashes. Adding a digest to
an older record can require one conservative reassessment because its old public
excerpt may be truncated.

New browser revisions freeze version, channel, platform, item type, parse status,
lifecycle and item digest with the existing text and evidence. These fields are
optional for historical records. Before replacing an older head, the collector
appends a complete snapshot of that head; existing revisions remain unchanged.
Its `restores_revision_id` identifies the original evidence revision. This snapshot
restores facts only and cannot replace a frozen report's evidence observation.
Assessment fingerprints use `semantic-v2-sha256:` for this distinction. Readers
retain `semantic-sha256:` verification for old immutable assessments and reports.

Source-only evidence cannot prove installed availability. A product channel requires an explicit product revision. Default state and expiry milestone must not imply rollout. Preserve unresolved syntax as an `unparsed` source item with location and hash. Keep exception text, retries and parser diagnostics private.

Assessment `subject_kind` is `source_item`, `feature_event` or `experiment_event`. Every judgment has an input hash, rule version, reasons and source references. The input hash covers normalized factual inputs and evidence revisions, excluding observation timestamps that do not change evidence. Model assessments also need model and prompt versions. Treat source instructions as data.

Statuses are `selected`, `watch`, `pending_verification` and `excluded`. A timeout or invalid model response creates no public judgment. Record `evaluation_failed` privately and preserve the last valid assessment and selected output. Never convert an evaluation error into `pending_verification` or an empty selected list.

Assessments are immutable. A changed input or rule creates a new ID and may `supersedes` an earlier assessment for the same subject. Do not rewrite previous judgments. Revisit evaluation with identical input/rules reuses the existing result unless a versioned assessment policy explicitly changes the inputs. Existing event selection fields are compatibility projections from the adopted assessment, not a second writer.

Selected records contain `current` and `history`. Current entries must reference a `selected` assessment. Deselection removes the entry from current, while history keeps its selected, deselected and reselected changes. Failure is not deselection. `selection_kind: flags` includes all three experiment kinds and requires the item kind. `selection_kind: features` covers regular features and their unlinked source items. The adopted subject may be an event; `catalog_id` links the feature or experiment when known. History entries may also retain `catalog_id`. Current and historical links must use the same feature/experiment owner as their subject. A source-item selection uses its source experiment kind and must be cited by any linked catalog or event. Ordinary source items cannot appear in the flag selection. Event predecessor and correction links must stay within one owner and must not form a cycle.

## Historical reports

The report ID is `daily-YYYY-MM-DD` in `Asia/Seoul`. Revisions of that ID describe corrected or late evidence. Same inputs, rules and cutoff reuse the existing revision. `timing` distinguishes current evidence, late observation, historical backfill, correction and reclassification. A historical selection is not a new product release. Each report item cites one selection change with the same subject and assessment. Its event IDs may be a subset of that change's event IDs, but every cited event must have the same subject owner and evidence relationship. An empty subset is allowed for a reclassification with no new factual event. No-change reports require successful private collection/evaluation evidence; failures must not be described as no change.

## Validation API

Install `python -m pip install -r schemas/requirements.txt`. JSON Schema validation uses `jsonschema` Draft 2020-12 with date/URI format checks. It must fail when the dependency is unavailable; do not skip validation. Runtime collectors can otherwise use the Python standard library.

```python
from schemas.validate import load_config, validate_record, validate_dataset, validate_transition
registry = load_config("config/sources.yml")
validate_record("sources_config", registry)
validate_record("source_item", item)
validate_transition("source_item", old_item, item)  # before replacing latest
validate_dataset(records_by_kind, {s["source_id"] for s in registry["sources"]} | {"legacy", "chromium-source"})
```

`records_by_kind` maps singular kinds such as `source_item`, `feature_event` and `assessment` to lists. Validate the complete candidate graph, not an isolated delta. `read_records(path, kind)` accepts a singleton or bounded array. The CLI is `python -m schemas.validate KIND FILE...`. Run contract tests with `python -m unittest discover -s schemas/tests -v`.

The contract gate checks shapes, dates, stable-reference integrity, selected status, assessment subjects and immutable transitions. Collectors must additionally reconcile enumeration and parsed/unparsed counts in private state.

## Normalization and legacy compatibility (1.1)

The optional experiment `source_definition` has its own `version: 1`. It stores
`semantic_sha256`, the normalized definition `expression`, an `options` array,
and `unresolved_references`. Each option has a `symbol`, source `path`, and full
normalized initializer `expression`. An option can include a `conditions` array of
nonempty strings for a resolved initializer's build branches. The same strict
source-definition shape applies when present in experiment-event `before` or
`after` snapshots and archives. Choices, variations and parameters retain
their C++ expressions and named relationships. An expression is source evidence,
not an evaluated parameter value. Unresolved names stay explicit. The semantic
hash covers the collector's full semantic input, including expanded options; it
is not a hash of this smaller public projection. Do not reconstruct catalog
facts from the truncated source excerpt. The collector's private typed handoff
is the normalization input. The public catalog carries the public facts.

Current feature events are `data/events/*.json`. Current experiment events are
arrays under `data/experiment-events/*.json`. Historical snapshots are under
`data/event-revisions/<event_id>/`; never load them as current events or count
their IDs a second time. `schema-v1.json` preserves each original event. Later
explicit factual corrections use `revision-N.json`, retain the event ID, cite
source items, and increment `revision`. Publication must include the archive and
current replacement in the same validated candidate.

The `origin: legacy` feature-event branch accepts only the observed legacy field
names and types, including string source URLs, nullable channels, and historical
nested evidence. All original values remain intact. New events use the strict
ordinary branch. This exception does not authorize new PM judgments. Existing
selection fields remain unchanged until T5 imports them into assessment records.
The recovered FedCM predecessor event uses its existing monthly source-event ID;
it is a historical reference repair, not a new discovery or release.

`data/compatibility/legacy-index.json` maps retained Markdown and release paths.
It records exact file hashes, feature IDs where explicit, and flag catalog links.
All these old inventories are legacy. The old desktop flag scope can link to a
current flag only through an exact flag ID and an unambiguous desktop registry
owner. Unmatched old flags retain unknown lifecycle, default, expiry and product
availability. Their source hashes describe retained legacy evidence, not source
blob bytes. Original release JSON, flag documents and monthly histories remain
at their existing paths with original judgments and official links.

`data/aliases/corrections.json` is an append-only array. Each entry has `alias_id`,
`subject_kind` (`feature` or `experiment`), `old_id`, `target_id`, public
`source_item_ids`, `reason`, `revision`, and `supersedes`. The first revision is 1
with null `supersedes`. A correction cites the previous alias entry. Lookup uses
the latest revision; old catalog records, event owners and evidence remain
addressable. Cycles, missing targets and missing evidence fail validation. An
alias never authorizes destructive merging or rewriting historical PM subjects.

ChromeStatus records with exact numeric upstream IDs and matching official URLs
can create feature identities. A single exact URL link to an existing legacy
feature preserves that feature ID. This alone does not create a launch event.
Other uninterpreted browser records remain full `source_item` assessment subjects,
including every revision. T5 and T7 must retain this subject kind. Explicit
browser fact normalization requires a supported canonical key, change type,
channel, platform and before/after values; title similarity is not an identity.

The shared collection entry point stages both collector outputs privately,
normalizes the candidate and validates the complete graph before publication.
Validation failure leaves the existing files unchanged. In-process write failure
rolls back replaced files. This is not a multi-file filesystem transaction across
a process crash or power loss; orchestration must use a private execution lock
and retain recovery state. Partial source coverage can add valid evidence but
cannot establish absence, removal, rollout, or complete inventory coverage.

Lifecycle progression uses accepted definition-location revisions and append-only
source snapshot order, never lexical Git SHA order. Removal proof must start at
the currently accepted positive definition revision. Restoration needs a new
positive snapshot after the definition cited by the last removal event. An absent
item retains its old definition evidence, so a matching hash alone cannot prove
restoration. Replaying that older positive bundle preserves the removed source
lifecycle. Replaying an old removal proof cannot remove a later restoration.
Same-semantic observations can advance accepted provenance without a new event;
a later removal can start from that advanced revision.
