# DEX v2.5.1-live — SAM Operator Fallback Hotfix

Status: release candidate; not deployed.

This narrow release carries the accepted v2.5-live TCGplayer Inventory Bootstrap + Reconciliation V1 behavior forward unchanged and adds the accepted SAM operator fallback correction.

## Corrected behavior

- Trusted exact-number OCR may nominate an exact frozen-catalog One Piece family for operator review even when a local reference image is unavailable.
- A valid catalog family is no longer forced to `Unidentified` solely because it is absent from the bounded visual-reference candidate list.
- Family availability and reference-image availability are reported separately.
- Search Local Reference now displays `SEARCHING`, `RESULTS FOUND`, `NO RESULTS`, and `SEARCH ERROR` states.
- Catalog-family results are selectable without a reference image.

## Authority boundary

The fallback is suggestion-only. Operator confirmation remains required. It does not grant automatic family authority, printing authority, or treatment authority. Recognition thresholds, confidence thresholds, correction history, and existing SAM/WOLFF/JANA behavior are unchanged.

## Data impact

No schema migration was added. The migration sequence remains 0001–0020.

