# DEX v2.2 SAM Real-World Validation — OP16 OCR Pass 2

Status: **CONTROLLED PASS COMPLETE — SAFETY GATE PASSED**  
Production approval: **Not implied**  
Recognition thresholds changed: **No**

## Safety result

**FALSE_AUTO_MATCH: 0 of 5 (0.00%)**

The unchanged five physical scans all produced the correct top candidate and a
valid local card-number read. Two scans met every existing authority safeguard
and became correct `AUTO_MATCHED` identities. Three remained in `NEEDS_REVIEW`
because their visual scores were below the unchanged 86% requirement. No result
became authoritative from OCR alone.

## Preserved baseline

- DEX runtime: `v2.2-test`
- Engine: `dex-sam-one-piece-v1`
- Rules: `sam-conservative-2026-08-15-v1`
- Reference index: `sam-reference-index-v1`
- Auto-match threshold: 90%
- Required auto visual score: 86%
- Review floor: 60%
- Auto candidate-margin threshold: 3.5 percentage points
- References: the exact same nine image files and byte hashes used by the first
  validation pass
- Physical inputs: the exact same five image files and byte hashes used by the
  first validation pass
- Ground-truth isolation: physical filenames and source card records contained
  no identity; ground truth did not participate in OCR, candidate selection, or
  scoring
- Environment: disposable local SQLite storage, external disposable reference
  directory, and a loopback-only server; production data and configuration were
  not used

The accepted Phase 7 Correction Hotfix checkpoint and
`SAM_REAL_WORLD_VALIDATION_OP16_2026-08-15.md` were not modified.

## Local OCR implementation

SAM now has an optional local Tesseract 5 adapter specifically for printed One
Piece card numbers. It:

1. preserves the original image;
2. takes three deterministic, bounded lower-right regions;
3. applies grayscale, enlargement, autocontrast, fixed contrast, sharpening,
   and fixed binary-threshold variants;
4. runs bounded single-line/sparse-text attempts with a restricted character
   set;
5. accepts a number only when multiple structurally valid reads produce a clear
   consensus; and
6. deletes every derived crop when the recognition attempt ends.

The runtime dependency is the external `tesseract` executable with English
language data. The Docker image installs `tesseract-ocr` and
`tesseract-ocr-eng` and asserts the executable during the build. Native local
development may point `DEX_TESSERACT_CMD` at Tesseract 5. Setting
`DEX_SAM_OCR_ENABLED=0`, omitting the executable, a timeout, or an unreadable
result leaves OCR non-authoritative and continues through the existing visual
path.

No image, crop, or OCR request is sent to a network service.

## Identifier normalization

Strict normalization accepts the established One Piece forms, including
`OP16-017`, `EB01-001`, `ST27-001`, `PRB02-018`, and `P-105`. Bounded correction
permits `O/0` and `I/1` substitutions only in positions whose prefix/digit
structure is otherwise valid. Missing or OCR-rendered separators may be repaired
only within that same structure. Unstructured text, ambiguous punctuation,
wrong-length numbers, and arbitrary fuzzy matches remain unreadable.

## Conflict and variant safety

- OCR and the independently calculated visual top candidate must agree before
  OCR can support automatic authority.
- An OCR/visual conflict records `CARD_NUMBER_OCR_CONFLICT` and routes to review.
- A valid card number with no indexed reference records
  `CARD_NUMBER_REFERENCE_MISSING`; DEX never invents an identity.
- Multiple plausible images for the same number remain protected by the existing
  variant-ambiguity gate.
- Scan-quality warnings, the unchanged score/margin gates, and operator-corrected
  identity protection remain in force.

The SAM interface shows a concise agreement, conflict, or unreadable status.
Raw text, selected crop, consensus, runtime version, and timings are available
only in the expandable OCR diagnostics.

## Exact blind rerun

| Scan | Ground truth | Baseline state | Baseline confidence | OCR result | OCR confidence | New state | New confidence | Correct? |
|---|---|---|---:|---|---:|---|---:|---:|
| `0807POK_C0999.png` | OP16-017 Little Oars Jr. | `NEEDS_REVIEW` | 86.50% | OP16-017 | 100.00% | `NEEDS_REVIEW` | 93.42% | Yes |
| `0807POK_C1000.png` | OP16-092 Nico Robin | `NEEDS_REVIEW` | 90.17% | OP16-092 | 85.71% | `AUTO_MATCHED` | 95.20% | Yes |
| `0807POK_C1001.png` | OP16-073 Borsalino | `NEEDS_REVIEW` | 84.10% | OP16-073 | 87.50% | `NEEDS_REVIEW` | 92.24% | Yes |
| `0807POK_C1002.png` | OP16-067 Tsuru | `NEEDS_REVIEW` | 92.99% | OP16-067 | 100.00% | `AUTO_MATCHED` | 96.58% | Yes |
| `0807POK_C1003.png` | OP16-097 Yamato | `NEEDS_REVIEW` | 85.48% | OP16-097 | 100.00% | `NEEDS_REVIEW` | 92.92% | Yes |

OCR confidence is the share of valid deterministic OCR attempts supporting the
winning normalized number, not a substitution for the unchanged visual score.

| Scan | Valid-read support | Visual confidence | Total | Preprocess | OCR execution |
|---|---:|---:|---:|---:|---:|
| `0807POK_C0999.png` | 4/4 | 83.54% | 2,473.55 ms | 107.39 ms | 2,041.39 ms |
| `0807POK_C1000.png` | 6/7 | 88.01% | 2,311.23 ms | 108.53 ms | 1,916.44 ms |
| `0807POK_C1001.png` | 7/8 | 80.61% | 2,166.56 ms | 104.31 ms | 1,786.61 ms |
| `0807POK_C1002.png` | 4/4 | 91.45% | 2,107.94 ms | 93.48 ms | 1,755.31 ms |
| `0807POK_C1003.png` | 3/3 | 82.29% | 2,064.64 ms | 96.16 ms | 1,722.06 ms |

All five OCR results agreed with the independently calculated visual top
candidate. The OP16-017 SAMPLE-watermark pair remained correct and in review;
OCR did not bypass its sub-threshold visual score.

## Before/after benchmark

| Metric | Pass 1: visual only | Pass 2: local OCR |
|---|---:|---:|
| Total scans | 5 | 5 |
| Correct top candidates | 5 (100.00%) | 5 (100.00%) |
| Valid card-number reads | 0 (0.00%) | 5 (100.00%) |
| Correct automatic matches | 0 | 2 |
| **False automatic matches** | **0 (0.00%)** | **0 (0.00%)** |
| Needs Review | 5 | 3 |
| Unidentified | 0 | 0 |
| Average overall confidence | 87.85% | 94.07% |
| Average total recognition time | 149.27 ms | 2,224.78 ms |
| Slowest recognition | 157.98 ms | 2,473.55 ms |
| Average preprocessing time | n/a | 101.97 ms |
| Average OCR execution time | n/a | 1,844.36 ms |

Local OCR added an average 2,075.51 ms and made total recognition approximately
14.90 times the visual-only baseline. This is acceptable for controlled human
review validation but is a known performance cost; no unapproved performance or
threshold tuning was attempted.

## Authority and economics isolation

The logical economics snapshot was identical before and after recognition:

- no acquisition, acquisition-line, batch-cost, or line-allocation change;
- no rip session, rip basis, sealed-unit, or quantity change;
- no sale, correction, disposition, post-sale, or portfolio-economic change;
- no market/listed-value change; and
- no operator decision was synthesized.

The only intended authoritative identity effects were the two correct automatic
matches, each applied once to its existing physical card record. The other three
records retained their prior physical identity and remained reviewable.

## Regression coverage

Pass 2 adds coverage for:

- strict supported-number parsing and bounded `O/0` and `I/1` correction;
- unavailable and unreadable OCR fallback;
- blurred, cropped, and low-contrast failure without false authority;
- OCR/visual disagreement routing to review;
- same-number variant protection;
- concise frontend agreement/conflict/unreadable rendering and expandable
  diagnostics; and
- unchanged acquisition/batch economics during recognition.

Final verification: **174 Python tests passed in 22.136 seconds**; the dedicated Phase 7 module
passed all 21 tests; JavaScript syntax passed; and all 12
self-contained frontend regressions passed. The disposable health endpoint
returned HTTP 200 and runtime `v2.2-test`.

## Operator validation

Disposable QA URL:
`http://127.0.0.1:18236/?sam-ocr-pass2=1#sam`

Expected queue result: **2 Matched, 3 Needs Review, 0 Unidentified**. Open any
record to see the card-number agreement; expand OCR diagnostics for its selected
crop, consensus, and timing.

## Limitations and next gate

- The five-scan result is a controlled OP16 validation set, not a broad accuracy
  claim across all One Piece products, foils, languages, lighting, cropping, or
  scanner hardware.
- Physical-scanner and larger adversarial-library validation remain appropriate
  before production approval.
- Tesseract is an additional native runtime dependency and materially increases
  per-card latency.
- No threshold tuning, Janna work, schema migration, deployment, or new feature
  phase is authorized by this result.
