# Normalize historical evidence

For new browser updates, use the [collection and storage workflow](../OPERATIONS.md). This module also reads the earlier experiment and event formats.

`normalize_chrome(bundle, sources, experiments, events, observed_at=...)` retains
source facts and history. Stable events ignore global commits, observation times
and line offsets. Defaults, options, platforms and other semantic changes create
separate events. A removed candidate requires the collector's complete-tree proof
and an explicit observation time. Stale handoffs cannot roll back current facts
or evidence locations. Lifecycle transitions also require progression from the
accepted definition revision: a new source snapshot after removal for restoration,
and a proof starting at the accepted positive revision for removal. Same-semantic
observations advance provenance without creating events. Git SHAs are never sorted
to infer time. Source-only does not mean product availability.

`AliasIndex` resolves reviewed, evidence-backed mappings. It keeps old records
addressable. Append an alias correction instead of overwriting an earlier entry.
`correct_event` returns a corrected fact and its previous snapshot; include both
in the publication candidate. `correction_files` returns the archive path and
value. Replace the existing event shard; do not write a duplicate singleton next
to an existing array entry.

`load_dataset` and `validate_graph` load only current record globs. Revision
archives and the compatibility index are separate. `publish` validates the whole
graph, source history prefixes and alias/archive immutability before writing. It
rolls back in-process failures and rejects edits detected while publishing. The
caller must serialize full daily runs; crash recovery and orchestration belong
to T9. Data source availability and PM success are separate states.

Legacy documents and release files remain at their old paths. The compatibility
index gives exact hashes and links. Source inventories imported from those paths
are incomplete legacy evidence. Neither their count nor the bounded T2/T3
samples establish a full baseline. See the [dataset contract](../../docs/dataset-contract.md).
