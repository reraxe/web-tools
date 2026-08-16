# DEX v2.2-test — Phase 7 SAM Recognition + Human Review Checkpoint

Status: implementation complete; operator QA required; production deployment **NOT APPROVED**  
Scope cutoff: One Piece SAM identity recognition and human review only  
Runtime identity: `v2.2-test`  
Known-good predecessor: accepted Inbound 2.0 Phase 6 Downstream Intake Bridge checkpoint

## Included Scope

- One Piece-only recognition attached to existing physical card/SKU, acquisition-line, batch, rip, processed-scan, and source-image records.
- Provider-neutral structured metadata interface with an OPTCG adapter, local normalized cache, explicit provenance, and graceful provider failure.
- Externally configured local One Piece reference library with incremental/resumable SHA-256 indexing, duplicate/near-duplicate evidence, and derived visual fingerprints.
- Layered candidate reduction using TCG/acquisition context, scan-quality observations, normalized card-number evidence, cached/local metadata, bounded visual families, and variant-aware ranking.
- Versioned conservative states: `AUTO_MATCHED`, `NEEDS_REVIEW`, `UNIDENTIFIED`, `OPERATOR_CONFIRMED`, and `OPERATOR_CORRECTED`.
- Non-blocking matched/review/unidentified lanes, side-by-side review, alternates, local Find Match, correction reason/note, and Leave Unidentified.
- Operator-QA hotfix: correction reason/note are visible modal controls; missing facts and rejected/stale/network failures remain visible in-place, and successful correction refreshes the queue with an explicit success message.
- Immutable recognition job IDs, retry protection, ranked candidates, original suggestions, evidence, provider/reference/engine/rules/index versions, timestamps, and append-only operator decisions.
- Strict identity-only boundary: no acquisition cost, basis, rip, sale, sealed-unit, or portfolio economics are assigned or changed.

Not included: JANA pricing, marketplace listing, cross-TCG recognition, global Attention Center, autonomous retraining, authentication changes, production deployment, or production-data work.

## Migration Ledger

Latest migration: `0014_v22_phase7_sam_recognition`

It adds nullable recognition fields to `cards` and the empty tables `sam_metadata_cache`, `sam_metadata_refresh_runs`, `sam_reference_index_runs`, `sam_reference_records`, `sam_recognition_jobs`, `sam_recognition_candidates`, and `sam_recognition_decisions`, plus lookup/de-duplication indexes.

The migration is additive, uses the established transactional savepoint/ledger contract, and performs no historical identity backfill. A forced-failure test verifies partial schema and the `0014` marker roll back together. Existing Phase 1–6 acquisition and all Phase 3–7C economics facts remain unchanged.

## Recognition Authority and Evidence

- `AUTO_MATCHED` requires normalized card-number evidence, strong visual agreement, an adequate candidate margin, acceptable scan quality, and no unresolved variant ambiguity.
- Plausible but conflicting/ambiguous evidence becomes `NEEDS_REVIEW`; absent trustworthy evidence becomes `UNIDENTIFIED`.
- Thresholds and rule version `sam-conservative-2026-08-15-v1` are backend-owned. JavaScript formats backend facts and does not calculate confidence.
- An operator can confirm SAM's proposed reference, search/select a different local reference and record a reasoned correction, or leave the scan unidentified.
- Later actions never erase the original SAM suggestion or ranked alternates. Operator-confirmed/corrected identity cannot be silently replaced by provider refresh or the legacy SAM path.
- A retry for the same request/processed scan replays the existing job. Two separate physical card/SKU records remain separate even if their scans and identities are identical.

## Provider, Cache, and Reference Privacy

- The OPTCG adapter sends structured card lookup/search requests only. It never transmits physical scans or local reference images and stores no credentials.
- Normalized cache records retain provider, source key, provider/version metadata, fetch/refresh timestamps, payload, and active/stale/missing state.
- Provider failure does not block scanning, local recognition, review, or Find Match.
- Reference originals remain outside SQLite and Git and are never renamed, moved, resized, overwritten, or watermarked. SQLite stores source references, dimensions, hashes/features, normalized metadata, duplicate relationships, provenance, and index state.
- Configure the reference root with `DEX_ONE_PIECE_REFERENCE_DIR`; it defaults to the established `DEX_SOURCE_DB_DIR` and `/source-database` Docker mount.

## Verification

- Python suite: **167 passed** in 16.415 seconds after the correction hotfix.
- JavaScript syntax: passed.
- Frontend contracts/regressions: **13 passed**, including the executable SAM correction success/rejection path and live authoritative batch-detail renderer.
- Visual browser suite: desktop and mobile rendered without browser console errors.
- Phase 7 performance regression: 5,000 reference rows inserted in **54.42 ms**; exact narrowed search **2.67 ms**; 5,000 metadata-cache rows **33.40 ms** with **0.05 ms** exact lookup; 1,000-card review queue **227.44 ms**.
- Final disposable fixture timings: six-image initial index **39.85 ms**; unchanged incremental index **3.49 ms**; four-card metadata refresh **0.22 ms**; per-card recognition **3.51–24.12 ms**.
- Migration coverage: clean install, legacy/no-backfill behavior, ordered `0001`–`0014` ledger, idempotent replay, and forced rollback passed.
- Disposable browser checks: mixed queue counts, high-confidence match, provider-missing fallback, variant review/alternates, wrong-top manual correction path, unidentified poor scan, and identity/economics boundary text passed.

## Disposable Operator QA

Create new disposable storage/reference fixtures:

`python scripts/seed_v22_phase7_sam_demo.py --output <new-empty-path>`

Launch DEX with `DEX_DATA_DIR` and `DEX_DB_PATH` using the created storage, `DEX_ONE_PIECE_REFERENCE_DIR` using the reported external reference folder, and scanner watching disabled. Never point Phase 7 QA at production or real ShonenRiot data.

- `OP-SAM-P7-HIGH`: expect Matched with correct number/name/reference and strong confidence even though the local reference contains a SAMPLE watermark that the physical scan lacks.
- `OP-SAM-P7-FALLBACK`: expect local automatic recognition with provider metadata explicitly missing/unavailable.
- `OP-SAM-P7-AMBIG`: expect Needs Review with side-by-side comparison and plausible alternate printing.
- `OP-SAM-P7-CORRECT`: expect Needs Review with intentionally wrong top suggestion; Find Match `OP16-035`, select it, Confirm Correction with reason/note, then verify the original suggestion remains in history.
- `OP-SAM-P7-UNKNOWN`: expect Unidentified with no authoritative guessed identity; Leave Unidentified remains available.
- Verify all five cards coexist in the queue and one unresolved card never blocks additional intake.

## Known Limitations

- One Piece only. Later games require separately approved provider/rule/reference adapters and fixtures.
- Local OCR is optional and not bundled. Without it, printed card-number evidence comes from existing intake facts or filenames; visual/context evidence can still route to review.
- Visual matching uses conservative perceptual/frame fingerprints, not a trained embedding or card-grading model. Physical scanner accuracy and false-positive rates require representative operator QA.
- Metadata refresh is operator-triggered for requested card numbers; there is no scheduled full provider sync.
- Local reference coverage, filenames, and variant quality affect results. Missing metadata stays Unknown and is never invented.

## Rollback

Do not delete recognition evidence, unlink card jobs, drop Phase 7 tables, or remove the migration marker manually.

- Before Phase 7 evidence exists: restore the preserved Phase 6 application checkpoint with its matching pre-`0014` database copy.
- After Phase 7 evidence exists: restore the matching pre-Phase 7 database copy and Phase 6 application checkpoint together. Older code cannot expose the new evidence/history safely.
- The external reference library is unchanged by DEX and does not require rollback.
- Production rollback remains an operator-controlled deployment action and is not authorized by this checkpoint.

## Approval Gate

Run disposable operator QA and representative physical One Piece scanner checks before any release promotion. Production remains operator-controlled. JANA, cross-TCG recognition, global Attention Center, autonomous retraining, or another phase requires separate explicit approval.
