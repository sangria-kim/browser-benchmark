# Browser source collection

Run from the repository root with Python 3.9 or later. Install `schemas/requirements.txt` first.

```sh
python -m pipeline.collect --private-dir /absolute/private/state --cutoff 2026-11-16T00:00:00Z
python -m pipeline.collect --private-dir /absolute/private/state --cutoff 2026-11-16T00:00:00Z --resume
```

Use `--source SOURCE_ID` more than once to select registered sources. Omit it to collect every enabled browser source. `--origin` accepts `baseline`, `backfill` or `daily`. The exit code is 0 for complete coverage of the requested sources and 2 for partial coverage. This entry point does not run PM selection.

The library entry point is `pipeline.collect.collect_browsers(repository, private_dir, source_ids=None, cutoff=None, transport=None, origin="baseline", resume=False)`. It returns private per-source results. The lower-level `BrowserCollector(...).collect(source, cutoff, since, origin)` accepts one registry entry. Inject a callable transport that returns `Response(url, body_bytes, status, headers)` for fixed fixtures.

The collectors write validated arrays to `data/source-items/<browser>/<source_id>.json`. IDs use the source ID, canonical response/document URL and item key. Upstream anchors or issue IDs take priority. If an issue or anchor occurs in more than one source unit, section and occurrence distinguish those locations. Distinct observations with the same record ID cause an explicit collision error. A section-local position is the fallback. It is a source location, not proof of feature identity. A changed item appends a revision. A repeated observation preserves the first observation timestamp. Translation URLs and notice IDs remain distinct. The cutoff limits dated source eligibility; the observation timestamp records actual collection time.

HTML adapters use publisher-specific product body boundaries. They retain list entries, table rows and prose, including security and fixes. Unrecognized text or image-only entries get minimal unresolved records. Apple uses official DocC topic sections and structured content. ChromeStatus uses `/api/v0/features` and checks `total_count`. GitHub uses its release API and follows the Link header. The Whale homepage embeds the official notice board; its public script uses the `whalehomepage` service and section 199 at `notice.naver.com`.

The private directory contains source checkpoints, pinned response metadata and raw response bytes. It must be outside the repository. Keep it out of exports. Discovered observations reconcile into processed, duplicate and unparsed counts. Stored record counts are separate. Unknown layouts, missing documents, changed API totals, truncated responses or HTML indexes, pagination loops and circuit-breaker limits leave coverage partial. Last successful source records survive failures. Source absence never creates a removal claim.

Resume uses the same explicit cutoff and cached response bytes. It reparses successful HTML inputs locally and continues the remaining page/document budget. Mutable ChromeStatus and Google blog API pages are refreshed as one enumeration; they are not mixed with earlier partial pages. The Google feed definition is also refreshed. Cached article evidence can still be reused. Changed totals or repeated IDs leave coverage partial. Start a new run to use changed collector code. The daily runner's `--browser-cache-from` verifies raw response hashes and copies no parsed status or output records. No adapter can prove completeness of unpublished source items.

Run the source tests with `python -m unittest discover -s tests -p test_browser_collectors.py -v`. Synthetic fixtures contain product examples only. Live raw pages and validation logs belong in private storage.
