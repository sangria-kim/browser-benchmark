# Browser source collection

Run from the repository root with Python 3.9 or later. Install `schemas/requirements.txt` first.

```sh
python -m pipeline.collect --private-dir /absolute/private/state --cutoff 2026-11-16T00:00:00Z
python -m pipeline.collect --private-dir /absolute/private/state --cutoff 2026-11-16T00:00:00Z --resume
```

Use `--source SOURCE_ID` more than once to select registered sources. Omit it to collect every enabled browser source. `--origin` accepts `baseline`, `backfill` or `daily`. The exit code is 0 for complete coverage of the requested sources and 2 for partial coverage. This entry point does not run PM selection.

The library entry point is `pipeline.collect.collect_sources`. It runs the adapters in a private directory. Raw observations stay under `work/candidates/`. Follow the [feature classification workflow](../../OPERATIONS.md) to save accepted features and evidence.

IDs use the source ID, canonical response/document URL and item key. Upstream anchors or issue IDs take priority. If an issue or anchor occurs in more than one source unit, section and occurrence distinguish those locations. Distinct observations with the same record ID cause an explicit collision error. A section-local position is the fallback. It is a source location, not proof of feature identity. A changed item appends a revision. A repeated observation preserves the first observation timestamp. Translation URLs and notice IDs remain distinct. The cutoff limits dated source eligibility; the observation timestamp records actual collection time.

HTML adapters use publisher-specific product body boundaries. They retain list entries, table rows and prose, including security and fixes. Unrecognized text or image-only entries get minimal unresolved records. Apple uses official DocC topic sections and structured content. ChromeStatus uses `/api/v0/features` and checks `total_count`. GitHub uses its release API and follows the Link header. The Whale homepage embeds the official notice board; its public script uses the `whalehomepage` service and section 199 at `notice.naver.com`.

The collector replaces explicit image-credit fields and contributor links after a
photo-credit label with a neutral marker. A line break can start a photo credit.
Standalone paragraphs labeled `Written by:`, `Authored by:` or `Posted by:` can
contain inline markup such as author links. Standalone bold bylines with the role
`Product Manager` or `Product Director` also use a neutral marker. The collector
keeps the source unit and surrounding product text. It removes the attribution
before reading headings and parent blocks.

The private directory contains source checkpoints, pinned response metadata and raw response bytes. It must be outside the repository. Discovered observations reconcile into processed, duplicate and unparsed counts. Stored record counts are separate. Unknown layouts, missing documents, changed API totals, truncated responses or HTML indexes, pagination loops and circuit-breaker limits leave coverage partial. Last successful source records survive failures. Source absence never creates a removal claim.

Resume uses the same explicit cutoff and cached response bytes. It reparses successful HTML inputs locally and continues the remaining page/document budget. Mutable ChromeStatus and Google blog API pages are refreshed as one enumeration; they are not mixed with earlier partial pages. The Google feed definition is also refreshed. Cached article evidence can still be reused. Changed totals or repeated IDs leave coverage partial. Start a new run to use changed collector code. No adapter can prove completeness of unpublished source items.

Run the source tests with `python -m unittest discover -s tests -p test_browser_collectors.py -v`. Synthetic fixtures contain product examples only. Live raw pages and validation logs belong in private storage.

## Brave publication inventory

REST, monthly HTML and metadata reconciliation use the same publication timestamp policy before excluding a release. The Jan 1 KST boundary is `2025-12-31T15:00:00Z`; the exact boundary and exact cutoff are included. Day-only evidence keeps its printed calendar date.

GitHub release `createdAt` is a commit date. Monthly creation-date searches cannot prove coverage of releases published this year from older commits. A complete public metadata inventory closes this gap. Authenticate the GitHub CLI separately, then capture metadata outside the repository:

```sh
python -m pipeline.collectors.browser.brave_metadata --cutoff 2026-11-16T12:53:40.560982+00:00 --output /absolute/private/brave-release-metadata.json
```

The helper invokes `gh api graphql` without a shell. It retains only public release IDs, tags, URLs, creation/publication dates and draft state. It verifies cursor continuity, unique IDs/tags, creation order, total counts and a first-page recheck. A separate ascending-order query must agree on the total and the oldest 100 records. This checks the opposite endpoint instead of trusting one count alone. Version 1 private bundles lack this check and must be captured again. The new output has mode 0600. It does not read or print tokens. An authentication, pagination or consistency failure writes no complete bundle. GitHub does not provide a historical snapshot; this inventory records its actual observation interval.

Pass the file through `--brave-release-metadata /absolute/private/brave-release-metadata.json` to `pipeline.collect` or a new `pipeline.run_daily` collection. Its cutoff must match the run. Keep the original metadata with the private run inputs if a retry needs it. The collector reconciles publication timestamps and fetches only missing eligible official release bodies. Missing, invalid or incomplete metadata leaves the older-created/newly-published gap explicit.

Source: [GitHub release API](https://docs.github.com/en/rest/releases/releases#get-the-latest-release) and [GraphQL release fields](https://docs.github.com/en/graphql/reference/objects#release).

In windowed collection, the private v3 metadata includes each release's official
modification timestamp. The collector compares the release ID, URL and publication
with the frozen inventory. It checks old releases with recent edits and the
creation-month HTML partitions needed for their existing item keys. If a release
appears in search but is missing from the inventory, coverage is partial. A v2
inventory still supplies publication dates. Old releases beyond REST coverage
with no verified modification date keep a v2 run partial. Capture a new v3
inventory for the same cutoff before starting a new run. The collector never
invokes the capture helper itself. [GitHub release fields](https://docs.github.com/en/graphql/reference/releases)
