# Migration 0016 — Receipt Semantic Foundation

Migration ID: `0016_v23_inventory_intelligence_phase1_receipt_semantics`

The migration is additive and transactional through the existing migration ledger. It creates:

- `receipt_semantic_lines`: versioned semantic assertions linked to extraction job, acquisition, source document, and optionally the normalized merchandise row.
- `receipt_semantic_events`: immutable classification, confirmation, correction, and unresolved-decision history.
- lookup and single-successor indexes.

No existing acquisition, receipt line, extraction job, inventory record, allocation, or economic fact is rewritten. Existing receipt history receives no inferred backfill. Legacy jobs remain compatible and retain HF3 matching behavior until a receipt is newly processed through the semantic engine.

Rollback is application-first: return to the frozen HF3 application/package and preserve the database. Migration 0016 tables may remain unused; do not delete production storage. No production migration or deployment was performed for this checkpoint.
