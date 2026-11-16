# Pinned Chromium source collector

This module collects public source definitions before PM selection. A source
record is not evidence of a product rollout, account assignment, or installed
behavior. Private Finch configuration is outside the scope.

Use a clean Chromium checkout for a full tracked-tree run. The collector verifies
HEAD and cleanliness, enumerates `git ls-tree -r`, and reads blobs from that commit.
It does not change the checkout. A Gitiles provider can resolve the configured ref
and walk the pinned tree. Tree traversal and downloads resume from private state.
Unsupported pagination or truncated responses prevent completion.

```sh
python -m pipeline.collectors.chrome \
  --checkout /private/chromium/src \
  --state-dir /private/chromium-collection/run-001 \
  --output data/source-items/chrome-experiments/source-items.json
```

For a bounded source sample, omit `--checkout` and pass one or more
`--sample-path` values. Required files are still fetched. `--max-files` limits new
downloads per call. `--max-trees` limits directory requests per call. Exit status
`2` means partial coverage; `0` means complete coverage under the configured
scope. The command prints an operations summary. Keep it outside the public repo.

For the 2026 projection, collect the verified pre-KST-Jan1 commit and the current
commit with the same final parser and scope. Each handoff records the parser code
SHA-256. Compare with `--baseline-bundle /private/boundary/handoff.json
--boundary-time <verified-commit-timestamp> --current-time <verified-current-commit-timestamp>
--cutoff <source-cutoff>` on the current
collection command. The timestamp must precede `2025-12-31T15:00:00Z`.
The current timestamp must not exceed its declared source cutoff. Browser and
Chromium cutoffs may differ; retain both in `collection_scope.source_windows`.
Use a new state directory when parser or scope changes. `handoff.json` then carries
`temporal_comparison` and public per-item scope. Pass that handoff to the daily
runner's `--chrome-bundle`. A current scan without this comparison stays temporally
unknown and cannot complete the bounded collection.

Enumeration, syntax parsing, reference resolution and temporal eligibility are
separate coverage dimensions. A zero syntax-error count does not prove resolved
relationships. The endpoint comparison ignores file hashes, line movement,
comments and declaration formatting. It retains older accepted identities and
does not publish removed/transient-only definitions as current 2026 changes.

Use one state directory per pinned revision. A resumed run reuses its original
revision even if main has moved. For a new revision, use a new directory and pass
`--previous-bundle /private/previous-run/handoff.json`. The previous source
histories survive errors and partial runs. Failed or pending auxiliary reads keep
existing source histories, catalog inputs and semantic facts together at their
last successful revision. New candidates remain unknown/unparsed until their
inputs recover. An unresolved reference or parser regression does not overwrite
a previously resolved record. Known UI exposure is retained during partial
coverage. Raw observations remain in private cache for recovery. Deletion inputs require two complete
same-scope trees. Missing files alone do not prove removal.

## Python API and handoff

```python
from pipeline.collectors.chrome import collect, Gitiles, LocalCheckout
from schemas.validate import load_config

config = load_config("config/chrome-source-scope.yml")
result = collect(config, LocalCheckout("/private/chromium/src"),
                 "/private/chromium-collection/run-001")
```

An injected provider implements `pin() -> commit`,
`enumerate(state_dir, max_trees=None) -> {paths, complete, unsupported}`, and
`read(path) -> bytes`. `Gitiles(..., transport=callable)` accepts a URL-to-bytes
transport for tests and managed networking. Pinning always precedes enumeration.
The collector validates output records against the shared schemas.

`handoff.json` is durable private state with `bundle_version: 1`:

- `source_items`: schema v2 public minimal source records, including unresolved
  candidates and unchanged prior records after partial collection.
- `experiments`: schema v2 catalog inputs with defaults, conditions, expiry,
  relationships, locations, and explicit source-only verification.
- `facts`: one typed fact per source item. Fields are `source_item_id`,
  `experiment_id`, `source_revision`, `semantic_sha256`, `file_sha256`,
  `definition`, `semantic`, and `dependencies`. `dependencies` stores known
  supporting paths and blob hashes. Resume checks follow known relationships
  and preserve prior facts if incomplete enumeration loses any known support.
  Earlier version 1 bundles without this optional field use inferred dependency
  paths from their options, source locations and relationship targets. `definition` holds the parsed candidate fields,
  full normalized definition expression, line range, references, and parser
  disposition. `semantic` holds definition meaning, title, description, default,
  value, conditions, platforms, expiry, relationships, unresolved references,
  and recursively expanded named choice/variation/parameter initializers.
- `removed_candidates`: verified source-absence inputs with before/after commit
  and scope hash. They do not assert a product removal.
- `coverage`: private counts, reconciliation, missing paths, errors, and limits.

`semantic_sha256` excludes commit, observation time, and line positions. It
includes the full definition and expanded options, so meaning changes beyond the
public excerpt limit still change the hash. Public `evidence.content_sha256`
uses that semantic hash; catalog `source_locations.content_sha256` and private
`file_sha256` use the full source blob hash. Repeated observations at the same
commit do not add duplicate source revisions.

T4 consumes this handoff for normalization and writes the public catalog. The
source array alone is not a substitute for the facts bundle. The current shared
experiment schema has no structured choice/parameter field. T4 must preserve
those facts in its versioned public catalog extension before data-only export.
Do not publish the handoff, cache, manifest, or operations summary.

## Parsing and coverage limits

The parser is lexical, not a C++ compiler. It keeps preprocessor branches without
evaluating them. It recognizes feature macros, direct feature definitions and
aliases, registered flag tables, and string switch definitions in switch paths
or a `switches` namespace. It separates declarations and type uses. Unhandled
feature markers, switch string syntax, and flag rows remain unresolved source
items. Candidate totals equal parsed plus unresolved items. Unresolved definition
references also prevent full coverage, even when the enclosing syntax is parsed.

Named auxiliary references require matching namespace and an unambiguous owner.
The collector does not merge two unrelated definitions that share a bare symbol.
Feature defaults and symbolic feature names include supported constant initializer
dependencies. Conditional default definitions must be mutually exclusive and cover
the feature's build conditions. Their initializer values and branch conditions enter
the endpoint comparison. Unsupported function calls, expressions, missing constants,
cycles and ambiguous branches remain unknown, even when the symbol text is unchanged.
Feature wrappers preserve object-macro names for this resolver. They do not select
the last macro definition. Macro redefinitions, `undef`, macro/constant collisions,
and locally defined macros used in build guards remain unknown when their meaning
cannot be proved. `BUILDFLAG(IS_*)` platform predicates remain symbolic conditions.
An unsupported conditional initializer can yield multiple unresolved fragments;
these fragments prevent full coverage and remain available for parser repair.
Arbitrary generated macro families and non-string switch representations are
outside this parser's recognized definition grammar. Configured marker rules
and the private manifest bound coverage; this is not proof of all C++ semantics.

Every configured required file must be available and parse checks must succeed.
All source files with configured extensions are inspected, including hidden and
unlinked features. Unsupported tracked entries block completion only when they
intersect the source/required-path scope. Missing generated outputs are not
invented. Registry-only sampling always remains partial. Full source traversal
and a complete historical baseline are separate work; a sample establishes
neither.

Metadata-only flag names remain as separate minimal source items. They do not
assert UI registration. Metadata is allowlisted to flag name and expiry milestone. Owner fields, emails,
authors, comments, and full metadata documents never enter public records. Public
evidence is limited to normalized definition excerpts, paths, hashes and commit
links. Raw downloads and all operational details stay in private state.
