# Migration Notes — DEX v2.4-test SAM Phase 1

Migration: `0017_v24_sam_phase1_family_printing`

## Behavior

- additive and transactional through the existing migration runner
- creates normalized family, printing, external-ID, reference-link, assertion, and decision-event structures
- adds nullable family/printing links and certainty fields to cards and recognition jobs
- creates indexes for family, printing, reference, assertion, and event lookups
- creates triggers that reject updates/deletes to identity assertions and decision events

## Compatibility

- no legacy card is assigned a family or commercial-printing ID
- existing `variant`, rarity, language-like, and finish-like values are unchanged
- legacy provenance defaults to `LEGACY_RECORDED`
- existing SAM recognition jobs and decisions remain visible
- no receipt, acquisition, economics, sealed-unit, sale, or marketplace schema is changed

## Rollback boundary

This development lane is not packaged or deployed. Rollback is restoration of the frozen v2.3-test Remediation 5 baseline and its database copy. Do not remove migration structures from a real database manually; use a verified pre-migration backup for any future approved deployment rollback.
