# Public data layout

Keep existing document paths and IDs. The new canonical layer separates evidence, facts and PM judgments. See [dataset contract 1.0](dataset-contract.md) for record fields and validation.

| Path | Contents |
| --- | --- |
| `config/sources.yml` | Public official source registry for eight browsers. |
| `config/chrome-source-scope.yml` | Fixed-revision Chromium enumeration rules. |
| `schemas/` | Versioned contracts, validation API and synthetic fixtures. |
| `data/source-items/<browser>/` | All collected source items, including fixes, excluded items and unresolved syntax. |
| `data/source-items/chrome-experiments/` | Source items for flags, base features and switches. |
| `data/catalog/features/` | Current feature identities and event references. |
| `data/catalog/chrome-experiments/` | Current experiment identities and source conditions. |
| `data/events/<event-id>.json` | Current feature event records. Preserve the existing 127 IDs and file paths. |
| `data/experiment-events/` | Experiment change events. |
| `data/event-revisions/<kind>/<id>/` | Immutable prior versions when an event is factually corrected. |
| `data/aliases/` | Evidence-backed identity corrections. |
| `data/assessments/<subject-kind>/` | Immutable PM judgments. |
| `data/selected/features/` and `data/selected/flags/` | Current selection materializations and retained change history. |
| `reports/` | Existing Markdown reports plus canonical report metadata. |
| `releases/`, `features/`, `experiments/chrome/` | Existing readable evidence and compatibility indexes. |

New source items and catalogs may use bounded JSON arrays to avoid one file per symbol. Use `<source-id>/<id-prefix>.json` for source items and `<browser-or-kind>/<id-prefix>.json` for catalogs. `id-prefix` is the first two hash digits, or `legacy` for retained IDs without a hash. Records in each shard are sorted by ID. Do not use wall-clock run IDs as filenames. Every source record keeps its own immutable `revisions` array; the containing shard is the latest materialization.

Assessment shards may use `<subject-kind>/<id-prefix>.json`. Never change or remove an existing assessment when rewriting a shard. Experiment events can also use bounded arrays. Preserve existing singleton feature event files. Before a factual correction, archive the old event as `<revision>.json` under `data/event-revisions/`; do not mix archives into the current-event collection. Selected data may use `current.json` with both `current` and append-only `history` arrays. Daily report metadata may use `reports/metadata/YYYY-MM-DD.json`; keep earlier report revisions in a sibling `revisions/` directory. All readers must distinguish current records from revision archives.

The schema applies to each record, whether its file is a singleton or an array. The full dataset validator receives a flat list per record kind. Filename, item count or schema validity alone does not establish collection completeness.

The data flow is official source → source item → feature/experiment and event → assessment → selected materialization → report/dashboard/export. A source item can receive an assessment before it is linked to a feature. No stage may delete source items because PM selection excludes them.

Unknown source history stays `legacy`. Keep all previous reports, evidence links and corrections. The [release index](../releases/README.md), [feature index](../features/README.md), [event index](../data/events/README.md) and [Chrome experiment index](../experiments/chrome/README.md) remain supported entry points.

Keep caches, coverage, parser failures, execution results, checkpoints and retry state outside the repository. Export archives are generated outside tracked data. A consumer must name its source ref and record its imported commit SHA. `work/browser-benchmark` contains agent-validated candidates. Only the owner merges them into `main`; see [repository rules](../AGENTS.md).
