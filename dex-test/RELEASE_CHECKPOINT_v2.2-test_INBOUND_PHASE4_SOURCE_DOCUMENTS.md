# DEX v2.2-test — Inbound 2.0 Phase 4 Source Documents Checkpoint

Status: **DEVELOPMENT CHECKPOINT — PRODUCTION DEPLOYMENT NOT AUTHORIZED**  
Scope cutoff: Receipt / Source Document Infrastructure  
Runtime identity: `v2.2-test`

## Scope

This checkpoint preserves the accepted v2.1 Phase 7C lifecycle and v2.2 Phases 1–3, then adds acquisition-linked source-document capture only. Product recognition, manual acquisition facts, Accounting-by-Default controls, established batch economics, and downstream inventory behavior are unchanged.

Included:

- multiple camera/file attachments for JPG/JPEG, PNG, and PDF;
- provider-neutral `DocumentStore` operations for store, metadata, retrieve/view, verify, tombstone, and health;
- private local-filesystem provider beneath `DEX_DOCUMENT_DIR` (default: `DEX_DATA_DIR/source-documents`);
- an intentionally unconfigured Google Drive-compatible provider boundary;
- server-side size, signature, image/PDF, MIME/extension, filename/path, duplicate, request-id, and revision validation;
- SHA-256 storage and read-time integrity verification;
- retryable failed attachments, draft removal, confirmed-evidence tombstones, and append-only document events;
- compact Step 2 controls/list and Step 3 attachment summary;
- server-mediated private viewing with no-store, no-sniff, and sandbox response headers.

Not included: OCR/AI extraction, amount suggestions, receipt-line classification UI, product/quantity matching, SAM work, downstream batch projection, a global Attention Center, or any new economics calculation.

## Migration

`0010_v22_phase4_source_documents` is additive and transactional through the existing savepoint/ledger mechanism. It creates:

- `acquisition_documents` — metadata, provider resource identifier, SHA-256, storage/integrity status, retry/replacement linkage, and tombstone facts;
- `acquisition_document_events` — immutable attach/failure/duplicate/retry/verify/integrity-failure/tombstone history;
- acquisition, hash/status, and event-history indexes.

It stores no BLOBs, performs no historical backfill, and changes no batch, card, sealed unit, cost, basis, rip, sale, correction, return, catalog mapping, or portfolio fact. Startup on an existing database creates only empty Phase 4 metadata/history infrastructure and the `0010` ledger marker.

## Lifecycle Rules

- A successful attachment records provider metadata and a verified SHA-256.
- A validation/provider failure remains visible and retryable; manual acquisition entry continues.
- Duplicate bytes on the same acquisition are suppressed by SHA-256 and audited.
- Draft removal deletes the private local artifact but retains tombstoned metadata/event history.
- After confirmation, ordinary removal moves the artifact to private tombstone storage and removes it from normal viewing without destroying history.
- Cancellation does not destroy source-document metadata/history.
- No document operation confirms financial facts, changes reconciliation, or creates downstream inventory.

## APIs

- `GET /api/document-providers/status`
- `GET /api/acquisitions/{id}/documents`
- `GET /api/acquisition-documents/{id}`
- `GET /api/acquisition-documents/{id}/content`
- `POST /api/acquisitions/{id}/documents`
- `POST /api/acquisition-documents/{id}/retry`
- `POST /api/acquisition-documents/{id}/verify`
- `POST /api/acquisition-documents/{id}/tombstone`

Mutation APIs use immutable request IDs. Acquisition-scoped writes use optimistic `expected_revision` checks.

## Verification

- Python: **126 tests passed**.
- Frontend: JavaScript syntax passed; **9 direct `.cjs` regression suites passed**.
- Focused Phase 4 coverage includes JPG/PNG/PDF, camera/multiple-file UI, SHA-256 and tamper failure, MIME mismatch, oversize/malformed artifacts, safe filenames/path traversal, duplicate and idempotent requests, draft remove, confirmed tombstone retention, reload/list/view APIs, provider health, migration rollback, and zero downstream facts.
- Existing large-data guard: Phase 7C read-only portfolio test remained below its threshold (approximately 292 ms for 40 finalized batches / 4,000 cards in the final regression run).
- Disposable seeder syntax/execution passed and refused overwrite by design.

## Known Limitations

- HEIC/HEIF capture is advertised to camera-capable clients but rejected clearly until the runtime has a verified safe decoder. The operator can retry with JPG/PNG/PDF.
- PDF checks are deliberately lightweight (signature, EOF, encryption marker, and bounded page-object count), not a full sanitizer.
- The Google Drive-compatible adapter is a provider-ready boundary only; it is not configured and accepts no credentials in this phase.
- DEX has no user/authentication subsystem of its own. Production/private-network access controls and TLS outside trusted loopback/private transport remain deployment responsibilities.
- Database metadata and private artifacts form one logical backup set. They must be copied/restored together.

## Rollback

Before any separately approved deployment, take a timestamped copy of both the SQLite storage and private source-document directory. If startup fails, stop only the failed runtime and restore the prior v2.2 Phase 3 application plus its matching pre-migration storage copy. After Phase 4 documents exist, rolling back requires restoring both the matching database and document directory. Do not delete tables, ledger rows, or artifact folders manually.

## Disposable Operator QA

1. Create a new disposable directory with `python scripts/seed_v22_phase4_documents_demo.py --output <new-path>`.
2. Launch DEX with `DEX_DATA_DIR=<new-path>`, `DEX_DB_PATH=<new-path>/dex.db`, `DEX_DOCUMENT_DIR=<new-path>/source-documents`, `DEX_WATCH_INBOUND=0`, and a non-production loopback port.
3. Open Inbound and resume **Phase 4 Receipt QA Shop**.
4. Confirm the seeded PNG and PDF appear, open privately, and remain after refresh.
5. Add a camera/photo or JPG/PNG/PDF, add multiple files, and confirm Step 3 reports the correct count.
6. Try an invalid/mismatched file and confirm it is retryable while manual fields remain usable.
7. Remove a draft attachment and confirm the UI retains its removed-history row after refresh.
8. Confirm no batch, card, sealed unit, basis, or portfolio fact was created.

Stop after this QA. Phase 5 receipt extraction/matching is not authorized.
