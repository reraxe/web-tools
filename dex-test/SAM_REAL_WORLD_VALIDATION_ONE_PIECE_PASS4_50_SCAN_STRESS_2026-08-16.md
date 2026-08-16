# DEX v2.2 SAM Real-World Validation — One Piece Pass 4 50-Scan Full-Library Stress Test

Status: **VALIDATION COMPLETE — NO TUNING PERFORMED**  
Production approval: **NOT APPROVED**  
Recognition policy changed: **No**

## Primary safety result

**FALSE AUTO-MATCHES: 0 of 50 (0.00%)**

The false-authority safety target passed. The broader full-library recognition gate did not: only 9/50 (18.00%) top candidates matched the independently transcribed card-number family, and the original five-card baseline outcome regressed. This report records the result unchanged; no threshold, OCR, visual, or card-specific adjustment was made.

## Frozen inputs and blind methodology

- Runtime: `v2.2-test` RC2 — Post-SAM hardening candidate
- Engine: `dex-sam-one-piece-v1`
- Rules: `sam-conservative-2026-08-15-v1`
- OCR: `dex-one-piece-card-number-ocr-v2-staged`
- Thresholds: 90% auto, 86% visual, 60% review floor, 3.5-point margin
- Reference index: 5,593 active images; 2,838 normalized card numbers; 2,747 multi-reference families
- Preflight: 50 physical / 50 ground truth / 50 blind, all source and staged hashes verified
- Blind filenames and embedded metadata contained no card identity; the runner read only the blind manifest and staged images
- Ground truth and blind key were joined only after all 50 predictions were frozen
- Exact printing was not independently established for any scan; all 50 are `UNKNOWN_PRINTING` and excluded from exact-print accuracy
- No retry, re-index, curated subset, altered setting, or mid-run correction occurred

## Corpus composition

- Sets: EB04 2, OP12 3, OP13 13, OP15 9, OP16 23
- Rarities: C 20, R 23, SR 2, UC 5
- Types: Character 42, Event 8
- Foil/reflection scanner group: 22; other scans: 28
- Lighting bands used only for analysis: Dark <125 brightness, Nominal 125–170, Bright >170
- Lighting mix: BRIGHT 5, DARK 7, NOMINAL 38
- Name-collision cases: Buggy, Shanks, and Monkey.D.Garp across different card numbers
- Duplicate physical identity: two distinct OP15-012 Buggy scans with different hashes and SKUs

## Aggregate results

| Metric | Result |
|---|---:|
| Correct top candidate / card family | 9/50 (18.00%) |
| Exact printing accuracy | Not evaluable — 0/50 exact-printing ground truth |
| Correct OCR | 26/50 (52.00%) |
| Valid but wrong OCR | 3/50 (6.00%) |
| OCR failure | 21/50 (42.00%) |
| Auto Matched | 2/50 (4.00%) |
| Needs Review | 13/50 (26.00%) |
| Unidentified | 35/50 (70.00%) |
| False auto-match | 0/50 (0.00%) |
| OCR/visual conflict flags | 26/50 |

Classification counts: `CORRECT_AUTO_MATCH` 2, `CORRECT_REVIEW` 6, `CORRECT_UNIDENTIFIED` 1, `WRONG_REVIEW` 7, `WRONG_UNIDENTIFIED` 34.

## Per-scan results

| ID | Source | Expected | OCR | Top candidate | State | Class | Visual | Confidence | Attempts/path | Latency |
|---|---|---|---|---|---|---|---:|---:|---|---:|
| P4-0001 | `0807POK_C0999.png` | OP16-017 Little Oars Jr. | OP16-017 | P-015 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 69.34% | 27.74% | 2 / Fast | 647.94 ms |
| P4-0002 | `0807POK_C1000.png` | OP16-092 Nico Robin | OP16-092 | OP16-092 | `AUTO_MATCHED` | `CORRECT_AUTO_MATCH` | 88.65% | 90.46% | 2 / Fast | 652.25 ms |
| P4-0003 | `0807POK_C1001.png` | OP16-073 Borsalino | OP16-073 | OP15-091 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 71.99% | 28.80% | 2 / Fast | 573.65 ms |
| P4-0004 | `0807POK_C1002.png` | OP16-067 Tsuru | OP16-067 | EB03-008 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 76.54% | 30.62% | 3 / Escalated | 826.21 ms |
| P4-0005 | `0807POK_C1003.png` | OP16-097 Yamato | OP16-097 | OP01-108 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 71.61% | 28.64% | 4 / Escalated | 954.65 ms |
| P4-0006 | `OP072726_4907.png` | OP15-012 Buggy | OP15-012 | OP15-012 | `AUTO_MATCHED` | `CORRECT_AUTO_MATCH` | 91.37% | 91.55% | 3 / Escalated | 705.57 ms |
| P4-0007 | `OP072726_4908.png` | OP15-043 Kelly Funk | OP15-043 | EB01-036 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 70.10% | 28.04% | 3 / Escalated | 714.13 ms |
| P4-0008 | `OP072726_4909.png` | OP16-049 Portgas.D.Ace | OP16-049 | EB01-002 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 74.64% | 29.86% | 2 / Fast | 476.25 ms |
| P4-0009 | `OP072726_4910.png` | OP16-023 Arlong | — | OP16-023 | `NEEDS_REVIEW` | `CORRECT_REVIEW` | 91.05% | 74.66% | 12 / Escalated | 1968.06 ms |
| P4-0010 | `OP072726_4911.png` | OP16-083 Kouzuki Oden | P-163 | OP04-087 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 72.37% | 28.95% | 2 / Fast | 475.08 ms |
| P4-0011 | `OP072726_4912.png` | OP16-047 Donquixote Doflamingo | OP16-047 | EB03-014 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 77.68% | 31.07% | 11 / Escalated | 1868.41 ms |
| P4-0012 | `OP072726_4913.png` | OP16-111 Boa Sandersonia | — | EB03-051 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 73.13% | 59.97% | 12 / Escalated | 2083.12 ms |
| P4-0013 | `OP072726_4914.png` | OP16-018 Rockstar | P-161Q | OP15-029 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 68.96% | 27.58% | 9 / Escalated | 1622.62 ms |
| P4-0014 | `OP072726_4915.png` | OP16-072 Hannyabal | OP16-072 | EB01-017 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 74.64% | 29.86% | 2 / Fast | 475.97 ms |
| P4-0015 | `OP072726_4916.png` | OP16-107 Jesus Burgess | — | OP12-104 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 70.86% | 58.11% | 12 / Escalated | 2081.44 ms |
| P4-0016 | `OP072726_4917.png` | OP16-006 Shanks | OP16-006 | OP06-064 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 72.75% | 29.10% | 6 / Escalated | 1167.45 ms |
| P4-0017 | `OP072726_4918.png` | OP16-075 Monkey.D.Garp | OP16-075 | EB01-036 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 67.07% | 26.83% | 3 / Escalated | 657.62 ms |
| P4-0018 | `OP072726_4919.png` | OP16-051 Mohji & Cabaji | OP16-051 | EB01-033 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 75.02% | 30.01% | 5 / Escalated | 1019.23 ms |
| P4-0019 | `OP072726_4920.png` | OP16-036 Mr.2.Bon.Kurei(Bentham) | — | OP16-036 | `NEEDS_REVIEW` | `CORRECT_REVIEW` | 89.61% | 73.48% | 12 / Escalated | 2001.79 ms |
| P4-0020 | `OP072726_4921.png` | OP16-101 Mahoroba | OP16-101 | EB01-039 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 76.16% | 30.46% | 3 / Escalated | 719.89 ms |
| P4-0021 | `OP072726_4922.png` | OP16-005 Thatch | OP16-005 | OP14-027 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 71.99% | 28.80% | 3 / Escalated | 659.03 ms |
| P4-0022 | `OP072726_4923.png` | OP16-102 Avalo Pizarro | — | OP16-102 | `NEEDS_REVIEW` | `CORRECT_REVIEW` | 88.77% | 72.79% | 12 / Escalated | 2222.67 ms |
| P4-0023 | `OP072726_4924.png` | OP16-031 Buggy | — | OP16-031 | `NEEDS_REVIEW` | `CORRECT_REVIEW` | 85.96% | 70.49% | 12 / Escalated | 2004.39 ms |
| P4-0024 | `OP072726_4925.png` | OP15-012 Buggy | — | EB01-014 | `NEEDS_REVIEW` | `WRONG_REVIEW` | 74.27% | 60.90% | 12 / Escalated | 2038.14 ms |
| P4-0025 | `OP072726_4926.png` | OP15-064 Kotori | — | OP15-064 | `NEEDS_REVIEW` | `CORRECT_REVIEW` | 89.24% | 73.18% | 12 / Escalated | 2007.01 ms |
| P4-0026 | `OP072726_4927.png` | OP15-079 Absalom | OP15-079 | OP08-091 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 73.13% | 29.25% | 3 / Escalated | 624.28 ms |
| P4-0027 | `OP072726_4928.png` | EB04-005 Trafalgar Law | EB04-005 | OP09-082 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 71.99% | 28.80% | 2 / Fast | 501.94 ms |
| P4-0028 | `OP072726_4929.png` | OP15-056 Would You Let Me Eat the Flame-Flame Fruit? | — | EB02-030 | `NEEDS_REVIEW` | `WRONG_REVIEW` | 82.60% | 67.73% | 12 / Escalated | 2159.00 ms |
| P4-0029 | `OP080126_HOLO_5386.png` | OP12-008 Shanks | — | OP07-003 | `NEEDS_REVIEW` | `WRONG_REVIEW` | 79.57% | 65.25% | 12 / Escalated | 1987.21 ms |
| P4-0030 | `OP080126_HOLO_5387.png` | OP12-097 Captains Assembled | — | EB01-009 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 71.23% | 58.41% | 12 / Escalated | 2203.35 ms |
| P4-0031 | `OP080126_HOLO_5388.png` | OP12-047 Sengoku | — | OP05-113 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 66.33% | 54.39% | 12 / Escalated | 2047.51 ms |
| P4-0032 | `OP080126_HOLO_5411.png` | OP15-025 Kuro | OP15-025 | OP15-025 | `NEEDS_REVIEW` | `CORRECT_REVIEW` | 87.34% | 89.94% | 2 / Fast | 448.64 ms |
| P4-0033 | `OP080126_HOLO_5412.png` | OP13-016 Monkey.D.Garp | OP13-016 | EB01-036 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 76.92% | 30.77% | 2 / Fast | 496.95 ms |
| P4-0034 | `OP080126_HOLO_5413.png` | OP13-091 St. Marcus Mars | OP13-091 | ST03-008 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 76.16% | 30.46% | 9 / Escalated | 1621.96 ms |
| P4-0035 | `OP080126_HOLO_5414.png` | OP13-110 Stussy | OP13-110 | EB01-053 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 74.64% | 29.86% | 7 / Escalated | 1336.31 ms |
| P4-0036 | `OP080126_HOLO_5415.png` | OP13-019 But Ace Here Said You Deserved It!! | — | EB02-010 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 71.99% | 59.03% | 12 / Escalated | 2138.50 ms |
| P4-0037 | `OP080126_HOLO_5416.png` | OP13-096 The Five Elders Are at Your Service!!! | — | EB02-007 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 69.34% | 56.86% | 12 / Escalated | 2160.23 ms |
| P4-0038 | `OP080126_HOLO_5417.png` | OP13-037 Roronoa Zoro | OP13-037 | EB02-002 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 72.37% | 28.95% | 11 / Escalated | 1989.71 ms |
| P4-0039 | `OP080126_HOLO_5418.png` | OP13-057 If I Bowed Down to Power, What's the Point in Living? | — | EB01-009 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 73.13% | 59.97% | 12 / Escalated | 2302.35 ms |
| P4-0040 | `OP080126_HOLO_5419.png` | OP13-083 St. Jaygarcia Saturn | OP13-083 | OP12-085 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 75.02% | 30.01% | 2 / Fast | 519.51 ms |
| P4-0041 | `OP080126_HOLO_5420.png` | OP13-017 Monkey.D.Dragon | — | OP05-047 | `NEEDS_REVIEW` | `WRONG_REVIEW` | 79.19% | 64.94% | 12 / Escalated | 1981.48 ms |
| P4-0042 | `OP080126_HOLO_5421.png` | OP13-114 S-Snake | — | EB01-052 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 72.75% | 59.66% | 12 / Escalated | 1929.32 ms |
| P4-0043 | `OP080126_HOLO_5422.png` | OP13-104 Kouzuki Hiyori | — | OP12-108 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 67.82% | 55.61% | 12 / Escalated | 2000.62 ms |
| P4-0044 | `OP080126_HOLO_5423.png` | OP13-076 Divine Departure | — | EB02-010 | `NEEDS_REVIEW` | `WRONG_REVIEW` | 73.89% | 60.59% | 12 / Escalated | 2273.11 ms |
| P4-0045 | `OP080126_HOLO_5424.png` | OP13-080 St. Ethanbaron V. Nusjuro | OP13-080 | EB03-043 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 76.16% | 30.46% | 7 / Escalated | 1390.91 ms |
| P4-0046 | `OP080126_HOLO_5449.png` | OP16-042 Prisoner of Impel Down | OP16-042 | EB03-032 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 70.86% | 28.34% | 2 / Fast | 505.67 ms |
| P4-0047 | `OP080126_HOLO_5450.png` | OP15-077 Lightning Dragon | — | EB01-050 | `NEEDS_REVIEW` | `WRONG_REVIEW` | 78.05% | 64.00% | 12 / Escalated | 2112.80 ms |
| P4-0048 | `OP080126_HOLO_5451.png` | EB04-003 Smoker & Tashigi | — | EB03-039 | `NEEDS_REVIEW` | `WRONG_REVIEW` | 75.02% | 61.52% | 12 / Escalated | 1946.22 ms |
| P4-0049 | `OP080126_HOLO_5452.png` | OP15-066 Satori | P-156 | OP15-066 | `UNIDENTIFIED` | `CORRECT_UNIDENTIFIED` | 90.74% | 36.30% | 2 / Fast | 489.24 ms |
| P4-0050 | `OP080126_HOLO_5453.png` | OP16-048 Buggy | OP16-048 | EB01-033 | `UNIDENTIFIED` | `WRONG_UNIDENTIFIED` | 68.58% | 27.43% | 2 / Fast | 498.76 ms |

## OCR workload

- Correct OCR: 26/50; failure: 21/50; valid-but-wrong: 3/50
- Average attempts: 7.36
- Fast path: 13/50 (26.00%); escalated: 37/50 (74.00%)
- Fast average: 520.14 ms; escalated average: 1662.87 ms
- OCR/visual conflicts: 26

## Full-library workload and variant families

- Candidate universe averaged 135.68 and peaked at 300; 22 scans reached the hard 300-candidate bound.
- No scan visually compared all 5,593 references; narrowing remained bounded by visual bucket or the 300-reference fallback.
- Every exact printing remains unknown, so same-number reference ranking is reported as ambiguity evidence rather than exact-print success.
- Variant ambiguity was flagged on 14 scans.

## Review workload

Primary Needs Review reasons: Candidate margin 3, Missing reference/metadata 1, OCR failure 3, Variant ambiguity 6.

## Lighting and foil/reflection findings

| Group | Scans | Correct OCR | Correct top | States | Avg latency |
|---|---:|---:|---:|---|---:|
| Foil/reflection filename group | 22 | 9 | 2 | {'NEEDS_REVIEW': 6, 'UNIDENTIFIED': 16} | 1562.74 ms |
| Other scans | 28 | 17 | 7 | {'AUTO_MATCHED': 2, 'NEEDS_REVIEW': 7, 'UNIDENTIFIED': 19} | 1210.99 ms |
| Dark | 7 | 4 | 2 | {'NEEDS_REVIEW': 4, 'UNIDENTIFIED': 3} | 1307.31 ms |
| Nominal | 38 | 20 | 6 | {'AUTO_MATCHED': 2, 'NEEDS_REVIEW': 7, 'UNIDENTIFIED': 29} | 1352.74 ms |
| Bright | 5 | 2 | 1 | {'NEEDS_REVIEW': 2, 'UNIDENTIFIED': 3} | 1546.59 ms |

Foil/reflection uncertainty did not create a false automatic match. It did, however, contribute to substantial Review/Unidentified workload and cannot be interpreted as exact-printing performance because printing ground truth is unavailable.

## Duplicate identities and repeated names

The two OP15-012 Buggy scans retained different scan hashes, SKUs, request IDs, recognition keys, and jobs. Neither was replayed or collapsed; both independently resolved through the pipeline.

- **Buggy:** expected numbers OP15-012, OP16-031, OP16-048; resulting top candidates OP15-012, OP16-031, EB01-014, EB01-033; classifications CORRECT_AUTO_MATCH, CORRECT_REVIEW, WRONG_REVIEW, WRONG_UNIDENTIFIED.
- **Monkey.D.Garp:** expected numbers OP13-016, OP16-075; resulting top candidates EB01-036, EB01-036; classifications WRONG_UNIDENTIFIED, WRONG_UNIDENTIFIED.
- **Shanks:** expected numbers OP12-008, OP16-006; resulting top candidates OP06-064, OP07-003; classifications WRONG_UNIDENTIFIED, WRONG_REVIEW.

## Performance

- Average: **1365.76 ms/card**
- Median: **1506.43 ms**
- p95: **2222.67 ms**
- Slowest: **2302.35 ms**
- Pass 3 historical average: 750.56 ms; Pass 4 difference: +615.20 ms/card

## Original five-card regression

- Correct top candidates: 1/5 (Pass 3: 5/5)
- Correct OCR: 5/5 (Pass 3: 5/5)
- States: {'AUTO_MATCHED': 1, 'UNIDENTIFIED': 4} (Pass 3: 2 Auto / 3 Review)
- False auto-matches: 0
- Historical outcome preserved: **NO**

The original-five safety gate remained intact—no false automatic identity—but full-library candidate behavior materially regressed top-candidate accuracy and operator disposition.

## Economics and inventory isolation

Protected facts unchanged: **YES**. Before hash `e234f6b6b2ccee15c4d6b44f09d535387b14df7112be938827d6bb89958d2a56` equals after hash `e234f6b6b2ccee15c4d6b44f09d535387b14df7112be938827d6bb89958d2a56`. Acquisitions, batch/card counts, sealed units, sales, economic events, post-sale events, rip/economic tables, and protected card economics remained unchanged. Only SAM identity/review fields and recognition evidence changed inside disposable validation state.

## Recommendations — no implementation authorized

1. Keep production approval blocked despite zero false auto-matches; the full-library top-candidate and baseline regression is material.
2. Preserve the frozen evidence and perform a separately approved design review of OCR-family candidate use versus the current independent visual-bucket cross-check. Correct OCR often coexisted with an unrelated visual top candidate.
3. Audit reference-family and variant metadata quality before attempting exact-printing authority; this corpus has no exact-print ground truth.
4. Retain the current conservative authority thresholds until a separately approved change can be evaluated against this same frozen corpus plus a holdout corpus.
5. Use the recorded dark/bright/foil and repeated-name failures to prioritize future investigation without card-specific exceptions.

No threshold, OCR stage, visual scorer, reference asset, card-specific rule, economics behavior, schema, or RC2 application file was changed during Pass 4.

## Artifacts

- Frozen blind predictions: external Pass 4 results storage (not packaged)
- Per-scan evaluation CSV: external Pass 4 results storage (not packaged)
- Machine-readable summary: external Pass 4 results storage (not packaged)
- QA highlights: external Pass 4 results storage (not packaged)
- Disposable validation storage: removed after validation and not packaged
