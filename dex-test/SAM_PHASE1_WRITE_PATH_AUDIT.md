# SAM Phase 1 Recognition-to-Inventory Write-Path Audit

Candidate: DEX v2.4-test — SAM Phase 1: Family vs Printing Confidence Foundation  
Baseline: frozen DEX v2.3-test Inventory Intelligence Phase 1 Remediation 5

## Authority boundary

`CARD FAMILY -> COMMERCIAL PRINTING -> REFERENCE ASSETS`

A family decision never grants printing authority. Exact printing is operator-only in Phase 1. Provider IDs, filenames, OCR, visual scores, and reference metadata are evidence—not authority.

## Write paths

| Path | Prior behavior | Phase 1 behavior |
|---|---|---|
| `dex_sam._apply_identity` | One helper copied family fields plus rarity/variant-like reference facts | Writes family fields and `sam_family_id` only. It never writes `cards.variant`, rarity/treatment, language, finish, or `sam_printing_id`. |
| Conservative `/sam/recognize` auto-match | Trusted a single combined identity | Keeps thresholds/rules unchanged and may apply family authority only. Printing result is suggestion/unresolved/conflicting with `authority_granted=false`. |
| SAM operator Confirm/Correct | Confirmed/corrected the combined reference identity | Confirm/Correct Family is independent. Confirm/Correct Printing is a separate operator-only event. Prior suggestions remain immutable. |
| Legacy `/api/cards/{sku}/sam` and batch SAM match | Copied source card number/name/set/rarity/color | Copies family identity and color, but no longer copies rarity. Records a family assertion/event and explicitly grants no printing authority. |
| Direct card editor | Could edit family and variant/rarity text without field-level SAM provenance | Family edits record operator-confirmed family provenance. Variant/rarity edits remain free-text, record non-authoritative printing assertions, and never assign a commercial-printing ID. |
| Reference-library indexing | Inferred `variant`/`printing` descriptions from filenames | May create descriptive family/printing/reference links only. Reference asset twins are links, not inventory authority. Weak Standard/Original metadata does not invent a commercial printing. |
| Metadata providers / TCGplayer bridge | Descriptive cache/reference enrichment | Remains descriptive only; external IDs are schema-constrained to `authority_granted=0`. |
| Challenger | Shadow candidate evidence | Remains shadow-only and has no inventory-write path. |

## Blockers removed

- Family auto-match can no longer populate exact-printing fields.
- Same-family references can no longer force a printing winner by a small score difference.
- Missing positive marker evidence produces Unresolved, not authority.
- Conflicting positive evidence produces Conflicting, not authority.
- Legacy `variant`, language-like, finish-like, and rarity-like text is preserved without backfill.
- Every new family/printing assertion and decision is append-only and includes job/reference/engine evidence where available.

## Intentionally unchanged

- SAM engine `dex-sam-one-piece-v1`
- conservative thresholds and rules version
- Challenger authority (none)
- card SKU and physical scan ownership
- receipts, acquisition allocation, economics, sealed inventory, sales, marketplace, and grading behavior
