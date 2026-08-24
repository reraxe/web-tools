# DEX v2.4-test — WOLFF Simplified Economics + SAM Phase 2

## Scope

This isolated candidate continues from the accepted SAM Phase 1 family/printing foundation. It adds a small read-only economics surface and additive printing-evidence intelligence without changing family matching, OCR, confidence thresholds, authority rules, receipt behavior, or marketplace workflows.

## WOLFF Simplified Economics v1

- derives item cost basis from finalized allocation facts; legacy estimates remain explicitly Estimated
- derives effective sale proceeds, direct recorded costs, sold basis, realized P/L, and ROI
- reports current recorded market value, remaining value, unrealized gain/loss, and ROI
- treats missing acquisition cost, fees, postage, basis, and price as Unknown rather than `$0.00`
- exposes calculation version, timestamp, source record/field, and value state
- excludes unresolved and estimated facts from precise aggregate totals and reports coverage
- stores no calculated dashboard totals and mutates no source financial record

## SAM Phase 2

- gathers all documented commercial printings for an established family
- records append-only artwork, marker, treatment, and reference-quality observations
- supports Present, Absent Confident, and Unresolved evidence states
- excludes printings only when required/incompatible evidence is confidently decisive
- ranks surviving candidates and explains each candidate in Human Review
- flags conflicts, same-family collisions, poor references, and high-confidence suggestions for review priority
- keeps Challenger evidence shadow-only and economic value outside recognition confidence

## Authority and compatibility

- automatic family authority remains governed by the frozen SAM v1 rules
- exact commercial printing remains operator-only even above 99% system confidence
- no existing identity, acquisition, basis, inventory, sale, receipt, or market fact is rewritten
- development candidate only; no packaging or deployment was performed

## Integration hardening and freeze-readiness pass

- keeps JARVIS as a read-only economics service and SAM as the sole identity workflow; economics may be displayed in Human Review but never contributes to recognition confidence or authority
- reports empty, missing, and incomplete economics as Unknown/Unresolved while preserving explicit authoritative `$0.00` facts
- distinguishes current, aging, stale, and unknown market-price freshness without silently substituting listed value for market value
- reconciles partial sales, fully sold inventory, exact-cent allocation, shipping charged to the buyer, fees, postage, sold basis, and realized/unrealized results from backend source facts only
- makes item, sale, aggregate, SAM evidence, and operator decision provenance inspectable in the UI
- validates operator printing assertions against the established card family and preserves system suggestions as immutable evidence
- preserves per-reference evidence within a commercial printing so reference twins or poor assets cannot create false printing authority
- returns privacy-safe JSON errors for unknown or malformed JARVIS API requests
- verifies fresh-start migration order `0017` then `0018`, SQLite integrity, append-only assertions/evidence, and zero automatic card/batch/sealed creation
- preserves the accepted Remediation 5 receipt baseline byte-for-byte; no receipt, acquisition, allocation, sealed, sales, or market-source fact is rewritten
- no packaging or deployment was performed

## Final candidate verification

- operator-facing economics name: WOLFF — Working On Levelling Financial Flows; internal JARVIS contracts remain unchanged
- zero authoritative basis coverage displays Unknown, while covered authoritative zero remains `$0.00`
- item economics labels the batch/purchase total as Parent acquisition cost and keeps Allocated acquisition cost separate
- Python: 299/299 passed
- frontend regression files: 26/26 passed
- JavaScript syntax: passed
- browser validation: partial-sale reconciliation, stale market labeling, item/sale provenance, family-only review, operator conflict/correction, and explicit operator printing confirmation passed without console errors
