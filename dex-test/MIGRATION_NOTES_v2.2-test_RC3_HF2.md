# DEX v2.2-test RC3 Hotfix 2 Migration Notes

Migration required: **No**

The schema and migration ledger remain at `0015_v22_rc3_hf1_mixed_purchase_reconciliation`. Hotfix 2 records an operator's manual-receipt fallback using the existing `receipt_extraction_events` table with event type `MANUAL_FALLBACK_SELECTED`.

The event states that extraction was unavailable and the receipt remains evidence. It does not confirm financial facts, accept a receipt proposal, allocate product-line basis, or bypass HF1 reconciliation.

Existing acquisitions, receipt documents, extraction records, batches, inventory, economics, and migration rows receive no startup rewrite or backfill.
