# DEX v2.2 SAM Real-World Validation — OP16

Status: **BASELINE COMPLETE — SAFE FOR CONTINUED CONTROLLED TESTING**  
Production approval: **Not implied**  
Recognition rules changed: **No**

## Safety result

**FALSE_AUTO_MATCH: 0 of 5 (0.00%)**

All five physical scans produced the correct top candidate. All five remained in
`NEEDS_REVIEW`; no identity became authoritative and no operator decision was
submitted. This meets the requested safety gate.

## Test environment

- DEX runtime: `v2.2-test`
- Engine: `dex-sam-one-piece-v1`
- Rules: `sam-conservative-2026-08-15-v1`
- Reference index: `sam-reference-index-v1`
- Auto-match threshold: 90%
- Required auto visual score: 86%
- Review floor: 60%
- Auto candidate-margin threshold: 3.5 percentage points
- Data: disposable local SQLite storage and external disposable reference folder
- Server: loopback-only disposable preview; production data/configuration not used
- OCR environment: optional local OCR unavailable (`pytesseract` and Tesseract absent)
- Recognition inputs: blank card identities and neutral physical-scan filenames
- External transmission: none; metadata was supplied locally for the nine known
  reference identities

The attachment transport assigned opaque temporary names. Validation staging
restored the nine supplied reference identities as the catalog filenames needed
by the existing indexer and restored the five directive-provided neutral scanner
filenames. Image bytes were copied unchanged. No image was cropped, rotated,
sharpened, color-corrected, or otherwise altered. Physical scan filenames and
card records contained no ground-truth identity.

## Reference-set inventory

All nine supplied references indexed successfully with no duplicate hashes and
no source-asset mutation:

| Card | Name | Indexed |
|---|---|---:|
| OP16-016 | Ramba | Yes |
| OP16-017 | Little Oars Jr. | Yes |
| OP16-030 | Trafalgar Law | Yes |
| OP16-042 | Prisoner of Impel Down | Yes |
| OP16-045 | Crocodile | Yes |
| OP16-067 | Tsuru | Yes |
| OP16-073 | Borsalino | Yes |
| OP16-092 | Nico Robin | Yes |
| OP16-097 | Yamato | Yes |

Index result: 9 seen, 9 indexed, 0 duplicates, 0 near-duplicates, 0 missing;
102.58 ms.

## Physical-scan inventory and results

All physical images were 1250 × 1750 pixels. SAM reported no scan-quality
warnings for any image.

| Physical scan | Ground truth | SAM top candidate | State / category | Overall | Visual | Card no. evidence | Compared | Margin | Alternate candidates (rank order) | Duration |
|---|---|---|---|---:|---:|---|---:|---:|---|---:|
| `0807POK_C0999.png` | OP16-017 Little Oars Jr. | OP16-017 Little Oars Jr. | `NEEDS_REVIEW` / `CORRECT_REVIEW` | 86.50% | 83.54% | Unavailable, 0% | 9 | 11.64% | OP16-092 (74.86%), OP16-045 (73.92%), OP16-030 (73.31%) | 152.73 ms |
| `0807POK_C1000.png` | OP16-092 Nico Robin | OP16-092 Nico Robin | `NEEDS_REVIEW` / `CORRECT_REVIEW` | 90.17% | 88.01% | Unavailable, 0% | 9 | 14.38% | OP16-017 (75.79%), OP16-073 (75.79%), OP16-030 (75.48%) | 157.98 ms |
| `0807POK_C1001.png` | OP16-073 Borsalino | OP16-073 Borsalino | `NEEDS_REVIEW` / `CORRECT_REVIEW` | 84.10% | 80.61% | Unavailable, 0% | 9 | 8.48% | OP16-097 (75.62%), OP16-092 (75.48%), OP16-017 (74.24%) | 143.41 ms |
| `0807POK_C1002.png` | OP16-067 Tsuru | OP16-067 Tsuru | `NEEDS_REVIEW` / `CORRECT_REVIEW` | 92.99% | 91.45% | Unavailable, 0% | 9 | 15.33% | OP16-030 (77.66%), OP16-042 (76.41%), OP16-073 (75.48%) | 149.68 ms |
| `0807POK_C1003.png` | OP16-097 Yamato | OP16-097 Yamato | `NEEDS_REVIEW` / `CORRECT_REVIEW` | 85.48% | 82.29% | Unavailable, 0% | 9 | 12.35% | OP16-042 (73.13%), OP16-017 (73.03%), OP16-016 (72.69%) | 142.56 ms |

Candidate narrowing was `BATCH_SET` for every scan. The stored exception for
every result was `LOW_RECOGNITION_CONFIDENCE`. That exception is appropriate:
the auto-match contract requires strong card-number evidence as well as visual,
margin, ambiguity, and scan-quality safeguards. The scans had no usable filename
identity and local OCR was unavailable.

## Benchmark summary

| Metric | Result |
|---|---:|
| Total scans | 5 |
| Scans processed successfully | 5 |
| Correct top candidates | 5 |
| Correct top-candidate rate | 100.00% |
| Auto-matched | 0 |
| Correct auto-matches | 0 |
| **False auto-matches** | **0 (0.00%)** |
| Needs Review | 5 |
| Unidentified | 0 |
| Average overall confidence | 87.85% |
| Average recognition time | 149.27 ms |
| Slowest recognition | 157.98 ms |
| Watermark-tolerant correct top candidates | 5 |
| OCR/card-number successes | 0 |
| OCR/card-number misses/unavailable | 5 |

## SAMPLE-watermark validation

The OP16-017 pair was inspected explicitly. Its supplied reference contains a
large `SAMPLE` overlay; its physical scan does not and has real scanner texture,
exposure, border, and geometry differences. With the existing
`IGNORED_AS_REFERENCE_ARTIFACT` policy active, SAM still ranked OP16-017 first:

- overall confidence: 86.50%
- visual confidence: 83.54%
- margin over second candidate: 11.64 percentage points
- result: `CORRECT_REVIEW`
- authoritative identity applied: no

This is the desired conservative result. The watermark did not displace the
correct identity or create false authority. It did reduce/limit visual agreement
enough that the pair did not satisfy the 86% auto visual requirement, but the
missing card-number evidence independently prevents automatic authority.

## Authority and economics isolation

The before/after logical economics snapshots were identical:

- 0 acquisitions and acquisition lines
- 0 rip sessions, rip-basis events, or rip-economic events
- 0 sales or sealed-sale items
- 0 sealed units
- 0 correction/economic events
- 0 post-sale events
- no card market/listing values
- unchanged disposable batch cost facts

Recognition created five recognition jobs only. It created zero operator
decisions, applied zero identities, and created zero source-card authority rows.
No production inventory, storage, or deployment configuration was accessed.

## Operator UI validation

The normal SAM page showed:

- 9 indexed references
- 5 Needs Review records
- 0 Matched and 0 Unidentified records
- each physical scan beside its correct best candidate
- confidence/state, three alternates, candidate count, exception, engine, and
  SAMPLE-watermark policy in every review dialog
- operator actions available, with no action exercised during the baseline

Disposable QA URL:
`http://127.0.0.1:18235/?sam-rwv-op16=1#sam`

## Observed limitations and recommendations (not implemented)

1. Keep the present thresholds and authority safeguards for now. The zero false
   auto-match result is more important than forcing automation.
2. Validate the existing optional local OCR path in a future controlled pass.
   In this environment OCR was unavailable, so even the two scans above 90%
   overall confidence correctly remained in review.
3. Consider crop/geometry normalization and visual fingerprint improvements only
   after preserving this baseline. Three correct pairs were below the current
   86% auto visual threshold.
4. Expand testing to more sets, close artwork variants, parallels/reprints, and
   deliberately difficult or wrong-reference cases before wider use.

No threshold, recognition logic, schema, application behavior, or deployment
configuration was changed during this validation.
