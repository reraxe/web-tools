# DEX v2.2-test Pre-Phase UX Consistency Hotfix Checkpoint

Status: development checkpoint; production approval **NOT GRANTED**; Downstream Intake Bridge not started

## Scope

This checkpoint preserves the complete v2.1 lifecycle and accepted Inbound 2.0 Phases 1–5. It adds only disclosure-state consistency, collapsible purchase sections, and audited acquisition removal/cancellation safety.

## Behavior

- One reusable frontend registry restores operator-controlled disclosure state after rerenders, searches, autosaves, mutations, and result refreshes. Critical/Needs Attention state can force a disclosure open.
- Product Catalog search stays expanded and shows refreshed results immediately. Purchase Details and Purchase Amounts use the same disclosure behavior; unresolved fields and retryable document/receipt failures cannot be silently hidden.
- Incomplete acquisitions without protected downstream history or a confirmed draft allocation may move to Recycle Bin. Restore returns the original draft state and appends a restore event.
- Confirmed unlinked acquisitions may be canceled with a standardized reason and required note. Their authoritative facts and provenance remain intact.
- Linked batches, cards, sealed units, rips, sales, corrections, and economic events block removal. DEX directs the operator to correction/reversal workflows.
- Permanent acquisition purge is not implemented. Source documents, extraction rows, acquisition lines, catalog linkage/provenance, allocations, events, and downstream facts are never orphaned.

## Migration

`0012_v22_prephase_ux_safety_hotfix` adds acquisition recycle/tombstone metadata and one listing index. It is additive, ledgered, transactional, and performs no backfill or business-data mutation.

## APIs

- `POST /api/acquisitions/{id}/recycle`
- `POST /api/acquisitions/{id}/restore`
- Existing `POST /api/acquisitions/{id}/cancel` now permits unlinked `READY_FOR_INTAKE` cancellation.
- Existing `GET /api/acquisitions`, acquisition detail, and `GET /api/recycle` expose backend eligibility and recycled acquisitions.

All mutations require a unique request ID and optimistic acquisition revision. Cancellation/recycle reasons use a bounded standardized vocabulary; confirmed cancellation requires an operator note.

## Verification

- Python: 145 tests pass.
- Frontend: JavaScript syntax, all 9 self-contained `.cjs` regression suites, and the server-backed batch-detail render suite pass against the disposable checkpoint startup.
- New tests cover expanded/collapsed persistence, Needs Attention force-open, Purchase section contracts, draft recycle/restore, confirmed cancellation, downstream blocking, and HTTP Recycle Bin behavior.
- Runtime remains `v2.2-test`; no economics formula or calculation version changed.

## Rollback

Preserve the accepted Phase 5 checkpoint and a matching pre-migration database/document-storage copy. If this checkpoint fails validation, stop only the new disposable/test runtime and restore the matching Phase 5 code plus matching storage copy. Do not delete or rebuild production storage.

## Gate

Operator QA remains required. This checkpoint does not authorize production deployment, the Downstream Intake Bridge, SAM work, or another development phase.
