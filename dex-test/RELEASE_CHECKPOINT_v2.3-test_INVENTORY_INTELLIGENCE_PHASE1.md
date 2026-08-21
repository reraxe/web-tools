# DEX v2.3-test Inventory Intelligence Phase 1 Checkpoint

Status: development test checkpoint; not a production release.

## Baseline and scope

This workspace was created as a mechanical copy of the frozen `DEX_v2.2-test_RC3_HF3_ZERO_ENTRY_FULL_CHECKPOINT`. The HF3 source package remains untouched. Phase 1 adds structured semantic facts between local receipt extraction and product matching.

Each normalized source line retains document/job/acquisition linkage, location, text, signed amount, semantic class, confidence, parser/rules/engine versions, timestamp, review requirement, status, and correction lineage. Parser results remain suggestions. Operator confirmation records review provenance but creates no inventory or accounting authority.

## Matching and accounting boundaries

Only current, non-conflicting `MERCHANDISE` assertions may feed newly processed receipt lines into catalog matching. Component, tender, summary, footer, structural, and unresolved lines are excluded. Business-purpose classification remains the separate HF3 workflow.

No allocation formula changed. `receipt-landed-allocation-v1`, the mixed-purchase `POLICY_REQUIRED` boundary, acquisition confirmation, economics, and SAM behavior remain as in HF3.

## Migration and rollback

Migration 0016 is additive, transactional, and deliberately performs no legacy backfill. A disposable HF3-shaped database with existing extraction history is covered by regression tests. Roll back by returning application code to frozen HF3 while preserving storage; the unused additive tables do not require destructive rollback.

## Privacy

The golden regression is synthetic text. No private receipt image, database, scanner content, reference asset, credential, or machine-specific runtime artifact belongs in this checkpoint.

## Deployment status

`NOT PERFORMED`
