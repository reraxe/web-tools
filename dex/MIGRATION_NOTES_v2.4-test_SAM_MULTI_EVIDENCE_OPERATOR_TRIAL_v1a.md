# Migration Notes — SAM Multi-Evidence Audited Operator Trial v1a

Migration: `0019_v24_sam_multi_evidence_operator_trial_v1a`

## Additive structures

- `sam_audited_recognition_results`: immutable pre-operator SAM result, source hash, accepted build identity, bounded evidence payload, and result hash.
- `sam_audited_operator_decisions`: append-only confirm, correction, unidentified, review, and rescan decisions linked to the original result.
- `sam_audited_verified_truth`: optional later verification that remains separate from operator decisions and supports later-reversed corrections.
- `sam_audited_recognition_deltas`: append-only before/after forensic records, explicitly labeled Unverified or Verified.
- supporting read indexes and update/delete denial triggers for every audited table.

## Migration behavior

- runs through the established transactional migration runner and preserves its savepoint;
- performs no backfill, inference, recognition, inventory creation, identity write, or economics mutation;
- creates empty audit infrastructure only;
- is deterministic and idempotent after successful ledger registration;
- a forced failure rolls back partial schema work and does not mark 0019 complete.

Compatibility testing covers fresh databases and legacy-shaped databases through migration 0018. Existing cards, batches, acquisitions, sales, WOLFF facts, SAM history, and receipt facts remain byte-for-byte logically unchanged.

## Rollback

Before deployment, retain the currently running WOLFF/SAM Phase 2 image and a verified timestamped `/data` backup. If the new application fails before operational v1a audit records matter, restore only the prior image first and leave storage intact. Do not drop 0019 tables or delete migration rows. If a data-level rollback is genuinely required, preserve the current storage and restore the matching pre-0019 backup only after explicit operator approval.
