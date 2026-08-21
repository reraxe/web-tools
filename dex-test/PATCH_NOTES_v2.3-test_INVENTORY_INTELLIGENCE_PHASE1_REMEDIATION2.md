# DEX v2.3-test Inventory Intelligence Phase 1 Remediation 2

Status: implementation and verification candidate; not packaged and not approved for deployment.

## Scope

- Adds Golden Regression Family #2 using a synthetic/redacted Fantasy Bay receipt structure.
- Fails closed on corrupted percentage-and-amount financial lines before merchandise matching.
- Recognizes tender identity separately from authorization/AID/CVM support metadata.
- Requires transaction context before classifying credit/discount language as a financial adjustment.
- Ranks merchant suggestions using deterministic text quality, header, repetition, and address-proximity evidence.
- Reduces review requests for high-confidence address, transaction metadata, payment metadata, policy, header, and footer lines without deleting source evidence.
- Documents the mandatory GitHub Build-Context and post-deployment provenance gates from `DEPLOYMENT-INTEGRITY-001`.

## Preserved boundaries

No allocation, economics, mixed-purchase `POLICY_REQUIRED`, SAM, Challenger, inventory authority, marketplace, or post-sale rules changed. Migrations remain 0001–0016; there is no migration 0017.
