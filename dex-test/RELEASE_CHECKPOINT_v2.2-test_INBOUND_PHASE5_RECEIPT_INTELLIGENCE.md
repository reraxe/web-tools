# DEX v2.2-test — Inbound 2.0 Phase 5 Checkpoint

Status: development complete; operator QA pending; production approval **NOT GRANTED**

## Scope

This checkpoint preserves the complete v2.1 economics lifecycle and accepted Inbound 2.0 Phases 1–4, then adds receipt intelligence only: provider-neutral extraction, normalized candidate purchase facts, review/edit provenance, receipt-line matching/classification, backend reconciliation, and deterministic allocation suggestions. It does not add SAM, downstream batch/sealed-unit projection, or a global Attention Center.

## Architecture and authority

- `dex_receipts.py` owns extraction contracts, local parsing, candidates, matches, classifications, proposals, and audit provenance.
- The operational provider is `LOCAL_PDF_TEXT` / `receipt-local-pattern-v1` for text-layer PDFs. JPG/PNG image OCR is provider-ready but unavailable. No external transmission or credentials exist.
- High-confidence candidates may populate empty draft fields visibly. Conflicts never overwrite manual or confirmed facts. Confidence changes presentation, never authority.
- Operator edits retain the original candidate and record `OPERATOR_REPLACED` provenance.
- The existing final acquisition confirmation is the only authority gate.
- Frontend code formats backend results and sends explicit decisions; it contains no allocation/reconciliation formula.

## Accounting-by-Default behavior

- Missing stays Unknown; extraction never manufactures zero.
- Single-line confirmation retains `SINGLE_LINE_100_PERCENT` behavior.
- Multi-line method `RECEIPT_VALUE_PROPORTIONAL` / `receipt-landed-allocation-v1` uses direct receipt-line merchandise and allocates shared tax/shipping/fees/duties/brokerage/discounts proportionally by merchandise value.
- Remainder cents are deterministic by immutable acquisition-line ID; allocated total must equal final USD exactly.
- Existing explicit-zero, $5 OR 2% material, 50%+ severe, reason/note, re-entry, and no-FX safeguards remain.
- Personal/nonbusiness, business-noninventory, duplicate, unresolved, ambiguous, or quantity-conflicting lines prevent unsafe automatic allocation.

## Migration ledger

Migrations `0001` through `0011` are ordered. `0011_v22_phase5_receipt_intelligence` creates only empty extraction/candidate/receipt-line/match/allocation/provenance/event structures and indexes. It performs no backfill and creates no business facts. Forced-failure rollback and repeat no-op behavior are tested.

## APIs

- `GET /api/receipt-extraction/providers/status`
- `POST /api/acquisition-documents/{id}/extractions`
- `GET /api/receipt-extractions/{job_uuid}`
- `POST /api/receipt-extractions/{job_uuid}/retry`
- `GET /api/acquisitions/{id}/receipt-intelligence`
- `POST /api/acquisitions/{id}/receipt-candidates/apply`
- `POST /api/receipt-candidates/{id}/disposition`
- `POST /api/receipt-lines/{id}/classification`
- `POST /api/receipt-line-matches/{id}/disposition`
- `POST /api/acquisitions/{id}/receipt-allocation-proposals`

All draft mutations use request IDs and optimistic acquisition revision checks.

## Verification

- Python: 141 tests pass.
- Frontend: JavaScript syntax plus 10 direct `.cjs` regression suites pass.
- Receipt performance fixture: 25 matched receipt/acquisition lines completes in approximately 24 ms on the development workstation (2.5-second guard).
- Browser QA: happy, multi-line, conflict, and failure paths render without console errors; exact paths enable confirmation; conflicts remain visible and blocked; failure retains manual entry and Unknown cost.
- Startup/import/health and forbidden-artifact scans are required again for the packaged copy.

## Privacy and deployment warnings

Receipt files are private operational evidence. Do not package source-document storage, databases, receipt images/PDFs, logs, caches, credentials, or disposable QA data. Persist and back up the configured document directory together with its database metadata. Never enable an external extractor without explicit privacy/provider approval.

This checkpoint does not authorize production deployment. Production remains operator-controlled. Test migrations only against disposable/copy fixtures first.

## Rollback

Preserve the accepted Phase 4 checkpoint unchanged. Before any approved deployment, make a timestamped copy of both SQLite storage and receipt-document storage. If startup or migration validation fails, stop the new application container/code and restore the matching pre-Phase-5 application plus both matching storage copies. Do not delete or recreate production storage because startup fails.

## Disposable QA

Run `python scripts/seed_v22_phase5_receipt_demo.py --output <new-empty-path>`, point all DEX data/document variables at that directory, and open Inbound. Validate acquisition codes `ACQ-20260815-0001` through `0005` in order: clean single-line, exact multi-line, manual conflict, incomplete/Unknown, and retryable extraction failure.

## Approval gate

Operator review of the disposable preview remains required. Downstream intake/projection, SAM, deployment, and subsequent phases are not authorized by this checkpoint.
