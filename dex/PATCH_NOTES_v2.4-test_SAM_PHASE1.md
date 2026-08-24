# DEX v2.4-test — SAM Phase 1

## Scope

This isolated candidate separates card-family recognition from exact commercial-printing identity. It preserves the frozen Receipt Remediation 5 baseline and the current authoritative SAM thresholds.

## Added

- normalized card families, commercial printings, provider-neutral external IDs, and reference-asset links
- independent family, printing, language, finish, and reference certainty/provenance assertions
- separate family/printing blocks in recognition results
- operator actions for Confirm/Correct Family and Confirm/Correct/Unresolved/Conflict Printing
- positive and negative printing-marker evidence states: Present, Absent Confident, and Unresolved
- append-only identity assertions and decision events

## Safety behavior

- automatic SAM can update family identity only
- exact printing is operator-only
- legacy printing-like text is not backfilled or treated as confirmed
- same-family collisions and missing/conflicting marker evidence cannot force a printing
- Challenger remains shadow-only

## Migration

Migration `0017_v24_sam_phase1_family_printing` is additive and transactional. It does not rewrite or infer identities for existing cards.

## Release status

Development candidate only. Packaging and deployment were not performed.
