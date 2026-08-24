# Migration Notes — DEX v2.4-test JARVIS + SAM Phase 2

Migration: `0018_v24_jarvis_economics_sam_phase2`

## Additive structures

- `jarvis_sale_input_evidence` records whether merchandise, buyer shipping, marketplace fees, and actual postage were explicitly supplied, including explicit zero values. It does not modify the sale.
- `sam_printing_evidence_observations` records independently inspectable Phase 2 evidence with observation ID, job/family/printing/reference links, evidence type/state/confidence/source, explanation, version metadata, and timestamp.
- indexes support job/family review reads.
- update/delete triggers make printing observations append-only.

## Migration behavior

- transactional through the existing savepoint migration runner
- no backfill or inference for legacy sales, cards, recognition jobs, or printings
- no calculated economics totals are stored
- no automatic printing assertion or authority is created
- fresh startup creates empty evidence structures only
- a failed migration rolls back its schema work and does not write the migration ledger marker

## Compatibility and rollback

Existing migrations `0001`–`0017`, source facts, and history remain unchanged. This development lane is not packaged or deployed. Any future deployment must first use a disposable copied database. The safe rollback boundary is the accepted SAM Phase 1 workspace/database backup; never manually remove migration structures from production data.
