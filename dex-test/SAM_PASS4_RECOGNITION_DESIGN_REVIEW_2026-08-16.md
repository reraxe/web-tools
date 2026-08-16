# DEX v2.2 SAM Pass 4 Recognition Design Review

Status: **DESIGN REVIEW ONLY — NO RECOGNITION CHANGE AUTHORIZED**  
Date: 2026-08-16  
Production approval: **NOT APPROVED**

## Decision summary

Pass 4 did not expose a primary ranking problem. It exposed a candidate-generation problem.

- The correct card family was present in the scored candidate pool for only **9 of 50 scans**.
- Whenever the correct family was present, it ranked first: **9 of 9**.
- It was absent before ranking for **41 of 50 scans**.
- Trusted OCR was correct on **26 of 50 scans**, but the current recognizer deliberately withheld that card number from candidate selection. In 23 of those 26 cases, the correct family was consequently absent from the scored pool.
- All 22 `BOUNDED_FALLBACK` runs excluded the correct family. That fallback is the first 300 active reference rows ordered by database ID, not the 300 visually nearest families.
- All 14 `MULTIPLE_PLAUSIBLE_VARIANTS` flags compared two files for the same card number, usually `card.jpg` and `card_small.jpg`. The accepted 5,593-reference index contains no independently modeled commercial-printing variants.

The existing recognizer is therefore flat at the wrong level: it scores individual image files, uses an exact four-hex visual bucket as a hard candidate boundary, and treats asset-level duplicates as possible variants. The recommended challenger should solve **card family first**, then **printing/variant**, with separate evidence and separate authority gates.

No threshold should be relaxed to address this result. The current conservative authority safeguards prevented every incorrect automatic match and should remain in force.

## Evidence boundary and method

Outcome analysis used only the frozen Pass 4 artifacts:

- `PASS4_50_FROZEN_BLIND_PREDICTIONS.json`
- `PASS4_50_PER_SCAN_RESULTS.csv`
- `PASS4_50_EVALUATION_SUMMARY.json`
- the preserved 50-row `ground_truth.csv`

The accepted 5,593-reference SQLite index was opened read-only only to determine whether each expected card-number family was inside the candidate pool selected by the frozen job. No scan was recognized again, no score was recalculated, and no index/reference file was changed.

The accepted Pass 3 report and its archived run evidence were inspected only to explain the already-reported five-card regression. They were not treated as new Pass 4 benchmark observations.

### First-failure ordering

Each scan is assigned exactly one earliest failure point using this order:

1. engine-detected scan-quality failure;
2. OCR produced no valid card number or a wrong valid number;
3. trusted OCR was correct, but the correct family was absent from the selected candidate pool;
4. correct family was present but did not rank first;
5. correct family ranked first but genuine printing/variant ambiguity blocked authority;
6. correct family ranked first but visual evidence remained below the authority threshold;
7. no failure: correct automatic match.

This ordering distinguishes a first failure from later safeguards. For example, 14 jobs carried `MULTIPLE_PLAUSIBLE_VARIANTS`, but all had an earlier OCR/candidate-generation issue or were comparing duplicate-sized assets rather than independently modeled commercial printings.

## Failure taxonomy

| First point | Count | Meaning |
|---|---:|---|
| OCR failure or incorrect read | **24** | 21 scans produced no valid number; 3 produced a wrong valid number. |
| Correct family absent from candidate set | **23** | OCR was correct, but the exact visual bucket or ID-limited fallback did not contain that family. |
| Correct family present but misranked | **0** | Every present correct family ranked first. |
| Variant-family ambiguity | **0 first failures** | 14 secondary flags existed, but they were asset twins, not proven commercial variants; three correct-family cases were conservatively held for review. |
| Visual-feature weakness | **1** | Correct OCR, correct family, correct top rank, but the combined score remained just below authority. |
| Engine-detected scan-quality issue | **0** | No frozen job carried `POOR_SCAN_QUALITY` or a scan warning. Dark/bright/foil correlations are observational, not proven first causes. |
| No failure / correct automatic match | **2** | OP16-092 Nico Robin and OP15-012 Buggy. |
| **Total** | **50** | One first-point classification per scan. |

### Structural candidate-pool findings

| Finding | Count |
|---|---:|
| Exact visual-bucket candidate mode | 28 |
| First-300 bounded fallback mode | 22 |
| Correct family present in pool | 9 |
| Correct family absent from pool | 41 |
| Present and ranked first | 9 |
| Present but misranked | 0 |
| Correct OCR with family present | 3 |
| Correct OCR with family absent | 23 |
| OCR problem with family nevertheless present | 6 |
| OCR problem with family absent | 18 |

The 41/50 candidate-absence figure is a structural diagnostic across all scans. The mutually exclusive first-failure table assigns 18 of those scans to OCR because OCR failed earlier.

## Representative examples

### OCR failure or incorrect read

- **P4-0009 / OP16-023 Arlong:** OCR produced no valid number. Visual selection nevertheless included OP16-023 and ranked it first with a 0.9105 visual score. The result correctly stayed in review because the two leading assets were the full and small files for the same family.
- **P4-0030 / OP12-097 Captains Assembled:** OCR failed and the run fell to the first-300 fallback. The OP12 family was not in that pool, so the later visual stage could not recover it.
- **P4-0049 / OP15-066 Satori:** OCR incorrectly normalized to `P-156`; visual evidence ranked OP15-066 first at 0.9074. The OCR/visual conflict safeguard kept the card unidentified. This is desired containment and must not be weakened.

### Correct family absent from candidate set

- **P4-0001 / OP16-017 Little Oars Jr.:** OCR correctly read OP16-017. The exact scan bucket selected only P-015 and OP03-050 assets; OP16-017 references were in different buckets. The job correctly reported `CARD_NUMBER_REFERENCE_MISSING` even though the family existed elsewhere in the index.
- **P4-0004 / OP16-067 Tsuru:** OCR correctly read OP16-067. No exact visual bucket was found, so the recognizer scored database IDs 1–300. OP16-067 references were IDs 4156 and 4157 and could never participate.
- **P4-0034 / OP13-091 St. Marcus Mars:** OCR correctly read OP13-091. The scan selected bucket `dd9a`; the family references were in `9d9a`, so the family was excluded before scoring.

### Correct family present but misranked

There are no Pass 4 examples. Correct-family presence predicted top-family correctness perfectly: **9/9**. Ranking changes are not the first design priority.

### Variant-family ambiguity

No scan has genuine commercial-printing ambiguity as its first demonstrated failure because exact printing ground truth is `UNKNOWN_PRINTING` and the index does not model independent printings.

Secondary examples show why the current flag is misleading:

- **P4-0009 / OP16-023:** `OP16-023.jpg` and `OP16-023_small.jpg` occupied ranks one and two.
- **P4-0022 / OP16-102:** `OP16-102_small.jpg` and `OP16-102.jpg` occupied ranks one and two.
- **P4-0025 / OP15-064:** `OP15-064_small.jpg` and `OP15-064.jpg` occupied ranks one and two.

These are multiple reference assets for one apparent printing, not two confirmed commercial printings. Their small margin should not be interpreted as printing ambiguity or as the family-level margin.

### Visual-feature weakness

- **P4-0032 / OP15-025 Kuro:** OCR was correct, the family was present and ranked first, and visual score was 0.8734. Combined confidence was 0.8994—six basis points below the unchanged 0.90 automatic threshold—so `NEEDS_REVIEW` was correct.

### Scan-quality issue

No scan crossed the recognizer's own scan-warning thresholds. The analysis-only lighting groups and filename-based foil/reflection grouping show correlation, not causation:

- foil/reflection scans: 9/22 correct OCR and 2/22 correct top family;
- other scans: 17/28 correct OCR and 7/28 correct top family.

The darkest and brightest scans still had no engine quality warning. A future challenger may improve glare/foil robustness, but Pass 4 does not justify labeling scan quality as the first failure for any row.

## Why the original five regressed from 5/5 to 1/5

The regression is explained by candidate context, not by a deterioration in the OCR stage or by a top-five ranking inversion.

### Pass 3

- The disposable batch carried `set_code=OP16`.
- The reference input contained only nine OP16 images.
- Because trusted OCR is excluded from candidate selection, `_candidate_rows` used `BATCH_SET` and scored all nine OP16 references.
- The correct family was therefore available on every scan and ranked first on all five.

### Pass 4

- The 50-card mixed-set batch correctly carried a blank set code.
- The index contained 5,593 assets across 2,839 card-number families.
- Trusted OCR was still excluded from candidate selection.
- Candidate formation therefore used an exact four-hex visual bucket or the first 300 rows by database ID.

| Original scan | Correct OCR | Pass 3 pool/result | Pass 4 pool/result | First Pass 4 failure |
|---|---|---|---|---|
| Little Oars Jr. OP16-017 | Yes | All nine OP16 refs; correct top | Bucket `c292`; expected refs in `8692`/`8a92` | Family absent |
| Nico Robin OP16-092 | Yes | All nine OP16 refs; correct top | Bucket `9a18`; one expected ref also in `9a18` | None; correct auto |
| Borsalino OP16-073 | Yes | All nine OP16 refs; correct top | Bucket `9e9a`; expected refs in `9892`/`989a` | Family absent |
| Tsuru OP16-067 | Yes | All nine OP16 refs; correct top | First 300 IDs; expected refs IDs 4156/4157 | Family absent |
| Yamato OP16-097 | Yes | All nine OP16 refs; correct top | Bucket `c25a`; expected refs in `82d0`/`92d0` | Family absent |

The exact-bucket key is brittle: a small visual-hash change in the first 16 frame bits places a scan in a disjoint pool. The fallback is also corpus-order dependent. Adding earlier-indexed sets changes which 300 records are scored even when the physical scan and OCR result do not change.

## Flat-reference diagnosis

The current recognizer is effectively flat in four important ways:

1. **Candidate unit:** each image file is a candidate. A full image and its `_small` derivative compete as separate identities.
2. **Hard bucket boundary:** only records with the identical first four frame-hash characters are considered unless the run falls back.
3. **Order-dependent fallback:** fallback takes the first 300 active rows by ID rather than the nearest 300 visual families.
4. **Single-stage authority:** family identity and printing identity share one ranked list and one margin.

The index confirms the mismatch:

- 5,593 reference assets represent 2,839 normalized card-number families.
- 2,742 families contain exactly two assets, overwhelmingly full/small pairs.
- 1,183 families span more than one exact visual bucket.
- no family has more than one distinct stored `variant|printing` label;
- filename inference labels ordinary files `Standard / Original`, so this is not a verified commercial-printing taxonomy.

This does not mean individual reference images are useless. They should remain visual evidence beneath a family or printing. They should not be the recognition identity or the unit used for the family-level margin.

## TCGplayer/catalog normalization review

The accepted v2.2 implementation does **not** yet contain a usable individual-card commercial-printing hierarchy:

- `catalog_products` and UPC mappings are deliberately scoped to `PACK_PRODUCT` and `SEALED_PRODUCT` acquisition products.
- `source_cards` is unique on `(game, card_number)` and has no printing, finish, language, or provider-product hierarchy.
- `sam_reference_records` stores flat filename-inferred `variant` and `printing` strings but no verified family/printing relationship.
- the accepted Pass 4 index contains zero TCGplayer product/variation identifiers and zero cached provider metadata rows.

TCGplayer normalization can still be valuable as a **commercial taxonomy**, provided it never becomes recognition authority. The useful role is to enumerate and label known sellable printings after a card family has been established:

- provider product/variation identifiers stored as opaque external IDs;
- normalized art/parallel/reprint, finish, language, release/set, and promotional attributes;
- links from one commercial printing to one canonical card-number family;
- mapping provenance, verification status, effective timestamps, and supersession history;
- no pricing field, provider rank, or product title allowed to decide scan identity.

Provider mappings should be suggestions until operator-confirmed or verified by a separately auditable import/crosswalk. A provider outage or stale catalog must not prevent family recognition or human review.

## Proposed SAM Challenger architecture

### Pipeline overview

```text
Physical scan
  -> scan-quality observations
  -> OCR evidence (unchanged staged Tesseract)
  -> family candidate union
       exact trusted OCR family, when present in the catalog
       global/multi-probe visual family neighbors
       optional batch/set context as a boost, never a hard exclusion
  -> family scoring and family-to-family margin
  -> conservative family authority gate
  -> within-family printing candidates
  -> printing/variant scoring and printing-to-printing margin
  -> printing authority gate or explicit operator review
```

### Stage 1: card-family recognition

The family identity should be the normalized game/card number, not a reference filename.

Candidate generation should form a bounded union:

1. If OCR has trustworthy consensus, include that exact family in the scored set. Inclusion is not authority.
2. Retrieve global nearest **family prototypes** or multi-probe neighboring hash buckets. Do not use an exact four-hex bucket as a hard boundary.
3. Include set-context candidates when batch/acquisition facts are trustworthy, but never exclude other families solely because context is blank or wrong.
4. Deduplicate all assets into families before calculating rank and margin.

Family visual evidence should aggregate multiple assets without allowing asset count to dominate. Recommended initial aggregation: maximum verified asset similarity plus a bounded secondary-support term, with deterministic tie-breaking by immutable family ID. Full/small derivatives of the same image should form one asset group.

Family automatic authority remains stricter than candidate inclusion:

- trustworthy OCR consensus;
- OCR family equals visual top family;
- family visual score meets the unchanged visual threshold;
- combined family confidence meets the unchanged threshold;
- margin is measured against the next **different family**;
- no OCR conflict, missing-family, severe-quality, or stale-evidence exception;
- no operator-confirmed identity may be overwritten.

If OCR is correct but visual evidence is weak, route to review or unidentified. Never auto-match from OCR alone.

### Stage 2: printing/variant recognition

Only after family selection should DEX evaluate printings within that family.

- Compare only verified printing candidates linked to the selected family.
- Aggregate multiple local images beneath each printing.
- Keep art/parallel/reprint, finish, language, and release distinctions explicit.
- If printing truth is unknown, report `FAMILY_MATCHED_PRINTING_UNKNOWN`; do not pretend `Standard / Original` is known.
- A family may be authoritative while printing remains unresolved, if the inventory data model and downstream listing safeguards explicitly preserve that distinction.
- Exact-printing auto-authority should remain disabled until a variant-labeled physical holdout demonstrates zero false printing matches.

### Preserved safeguards

- Existing 90% family confidence threshold, 86% visual threshold, 3.5-point family margin, and 60% review floor remain the challenger starting policy.
- OCR/visual disagreement remains a hard automatic-match blocker.
- Trusted OCR with no known family remains `REFERENCE_MISSING`, never a fabricated identity.
- Variant/printing ambiguity remains a blocker at the printing stage.
- Poor/unreadable scans cannot receive automatic authority.
- Original recognition evidence, challenger version, candidate sets, and operator decisions remain immutable/auditable.
- Zero false automatic matches remains the non-negotiable primary gate.

## Additive data/model changes required

Suggested conceptual tables/relationships; names are provisional and no migration is authorized:

| Model | Purpose |
|---|---|
| `card_families` | Canonical game + normalized card number, canonical set/name/type facts, provenance. |
| `card_printings` | Family child for art/parallel/reprint, finish, language, release, promo and verification state. |
| `card_printing_external_ids` | Provider-specific product/variation IDs with provenance, status, effective time and supersession. |
| `sam_reference_assets` | Existing reference file facts linked to a family and nullable verified printing; includes asset role and derivative group. |
| `sam_family_feature_sets` | Versioned family prototypes or search features derived from reference assets. |
| `sam_recognition_family_candidates` | Immutable family rank, OCR score, aggregated visual evidence, context and margin inputs. |
| `sam_recognition_printing_candidates` | Separate within-family printing evidence and rank. |

Compatibility/backfill rules:

- Additive only; preserve existing recognition jobs, decisions, references, and inventory identities.
- Backfill families deterministically from normalized `sam_reference_records.card_number`.
- Group obvious full/small derivatives as assets of one `UNKNOWN_PRINTING`; do not infer a commercial variant.
- Preserve filename-derived variant/printing strings as low-trust legacy evidence, not verified facts.
- Keep provider crosswalk events append-only and reversible through linked correction events.
- Run the challenger in shadow/read-only mode first; it must not update cards or operator decisions.

## Source participation and authority boundaries

| Source | Challenger role | Must not do |
|---|---|---|
| Local reference library | Primary visual evidence; multiple assets grouped under family/printing; hashes/features computed locally. | A file count or filename alone must not create identity authority. |
| Local OCR | Printed card-number evidence and exact-family candidate inclusion. | OCR alone must not auto-match. |
| OPTCG metadata | Canonical number/set/name/type enrichment, family existence checks, human-readable review context. | Provider metadata must not override visual/OCR conflict or operator decisions. |
| TCGplayer normalization | Commercial printing/finish/language hierarchy and marketplace crosswalk after family recognition. | Product titles, prices, popularity, or provider rank must not decide identity. |
| Operator decisions | Final authority for corrections and unresolved printings; durable provenance. | Later automated runs must not overwrite them. |

## Challenger benchmark plan

### Frozen 50-scan comparison

1. Preserve the current predictions and report as Baseline `sam-conservative-2026-08-15-v1`.
2. Freeze a challenger engine/rules/index-feature version before its first scored run.
3. Use a copied disposable database and the same 50 blinded scan bytes and 5,593 reference bytes.
4. Run baseline and challenger as separate immutable jobs; challenger is shadow-only and applies no inventory identity.
5. Keep ground truth unavailable to candidate generation, scoring and authority.
6. Join predictions to ground truth only after all 50 challenger results are frozen and hashed.
7. Do not tune during the run. Any later change becomes a new challenger version and a new immutable result set.

Required reporting:

- false family auto-matches and false printing auto-matches;
- family candidate recall, top-1 family accuracy and family rank;
- correct-family auto/review/unidentified distribution;
- printing accuracy only where printing truth is independently known;
- OCR failure, incorrect OCR and OCR/visual conflict containment;
- family-to-family and printing-to-printing margins;
- candidate counts, latency, memory and deterministic replay;
- original five-card regression results;
- foil/reflection and lighting slices without treating filename groups as causal labels.

Recommended acceptance gates for a first challenger candidate:

- **0 false automatic family matches**;
- **0 false automatic printing matches**; preferably no exact-printing automation in this corpus because truth is unknown;
- correct family included for at least **45/50** scans;
- correct top family for at least **40/50** scans;
- original five restored to **5/5** correct top family;
- every OCR/visual conflict remains non-authoritative;
- deterministic rerun produces identical family/printing candidate order and decisions;
- P95 latency is measured and explicitly accepted rather than hidden by asynchronous behavior.

Because this 50-scan corpus has now informed the design, it is a required regression corpus but no longer sufficient as the sole production-approval proof. A separately collected, variant-labeled blind holdout is required before exact-printing authority, and a new unseen family-level holdout is recommended before production SAM approval.

## Risks

- **Overfitting:** the frozen 50 now informs architecture. Preserve it as regression evidence and require an unseen holdout.
- **OCR over-trust:** including the OCR family in candidates could look like authority. Keep independent visual agreement and unchanged blockers mandatory.
- **Provider taxonomy drift:** TCGplayer/OPTCG mappings can change or conflict. Store versioned provenance and never silently remap inventory.
- **False family aggregation:** unrelated printings or promos can share a card number in provider data. Operator-verified crosswalks and language/release facts remain necessary.
- **Asset imbalance:** families with more reference images could dominate. Use bounded aggregation and derivative grouping.
- **Latency:** global family retrieval is broader than exact-bucket lookup. Use a versioned approximate/multi-probe index, bounded family count, and deterministic fallback.
- **Compatibility:** existing card identities and decisions cannot be rewritten during backfill. Challenger shadow mode must be isolated from authoritative inventory writes.
- **Partial printing truth:** the current Pass 4 corpus validates families, not exact commercial printings. Do not infer printing performance from it.

## Recommendation requiring approval

Approve a separately scoped **SAM Challenger Foundation** only if the operator wants implementation to begin. That scope should be limited to additive family/printing data structures, deterministic family aggregation, shadow-only candidate generation, and benchmark tooling. It should not change current SAM authority, thresholds, operator workflow, or inventory writes until the challenger passes the approved gates.

## Per-scan first-failure appendix

| Scan | Source | Expected | OCR | First point | Selected top | State |
|---|---|---|---|---|---|---|
| P4-0001 | 0807POK_C0999.png | OP16-017 | OP16-017 | Family absent | P-015 | UNIDENTIFIED |
| P4-0002 | 0807POK_C1000.png | OP16-092 | OP16-092 | No failure | OP16-092 | AUTO_MATCHED |
| P4-0003 | 0807POK_C1001.png | OP16-073 | OP16-073 | Family absent | OP15-091 | UNIDENTIFIED |
| P4-0004 | 0807POK_C1002.png | OP16-067 | OP16-067 | Family absent | EB03-008 | UNIDENTIFIED |
| P4-0005 | 0807POK_C1003.png | OP16-097 | OP16-097 | Family absent | OP01-108 | UNIDENTIFIED |
| P4-0006 | OP072726_4907.png | OP15-012 | OP15-012 | No failure | OP15-012 | AUTO_MATCHED |
| P4-0007 | OP072726_4908.png | OP15-043 | OP15-043 | Family absent | EB01-036 | UNIDENTIFIED |
| P4-0008 | OP072726_4909.png | OP16-049 | OP16-049 | Family absent | EB01-002 | UNIDENTIFIED |
| P4-0009 | OP072726_4910.png | OP16-023 | — | OCR failure | OP16-023 | NEEDS_REVIEW |
| P4-0010 | OP072726_4911.png | OP16-083 | P-163 | OCR incorrect | OP04-087 | UNIDENTIFIED |
| P4-0011 | OP072726_4912.png | OP16-047 | OP16-047 | Family absent | EB03-014 | UNIDENTIFIED |
| P4-0012 | OP072726_4913.png | OP16-111 | — | OCR failure | EB03-051 | UNIDENTIFIED |
| P4-0013 | OP072726_4914.png | OP16-018 | P-161Q | OCR incorrect | OP15-029 | UNIDENTIFIED |
| P4-0014 | OP072726_4915.png | OP16-072 | OP16-072 | Family absent | EB01-017 | UNIDENTIFIED |
| P4-0015 | OP072726_4916.png | OP16-107 | — | OCR failure | OP12-104 | UNIDENTIFIED |
| P4-0016 | OP072726_4917.png | OP16-006 | OP16-006 | Family absent | OP06-064 | UNIDENTIFIED |
| P4-0017 | OP072726_4918.png | OP16-075 | OP16-075 | Family absent | EB01-036 | UNIDENTIFIED |
| P4-0018 | OP072726_4919.png | OP16-051 | OP16-051 | Family absent | EB01-033 | UNIDENTIFIED |
| P4-0019 | OP072726_4920.png | OP16-036 | — | OCR failure | OP16-036 | NEEDS_REVIEW |
| P4-0020 | OP072726_4921.png | OP16-101 | OP16-101 | Family absent | EB01-039 | UNIDENTIFIED |
| P4-0021 | OP072726_4922.png | OP16-005 | OP16-005 | Family absent | OP14-027 | UNIDENTIFIED |
| P4-0022 | OP072726_4923.png | OP16-102 | — | OCR failure | OP16-102 | NEEDS_REVIEW |
| P4-0023 | OP072726_4924.png | OP16-031 | — | OCR failure | OP16-031 | NEEDS_REVIEW |
| P4-0024 | OP072726_4925.png | OP15-012 | — | OCR failure | EB01-014 | NEEDS_REVIEW |
| P4-0025 | OP072726_4926.png | OP15-064 | — | OCR failure | OP15-064 | NEEDS_REVIEW |
| P4-0026 | OP072726_4927.png | OP15-079 | OP15-079 | Family absent | OP08-091 | UNIDENTIFIED |
| P4-0027 | OP072726_4928.png | EB04-005 | EB04-005 | Family absent | OP09-082 | UNIDENTIFIED |
| P4-0028 | OP072726_4929.png | OP15-056 | — | OCR failure | EB02-030 | NEEDS_REVIEW |
| P4-0029 | OP080126_HOLO_5386.png | OP12-008 | — | OCR failure | OP07-003 | NEEDS_REVIEW |
| P4-0030 | OP080126_HOLO_5387.png | OP12-097 | — | OCR failure | EB01-009 | UNIDENTIFIED |
| P4-0031 | OP080126_HOLO_5388.png | OP12-047 | — | OCR failure | OP05-113 | UNIDENTIFIED |
| P4-0032 | OP080126_HOLO_5411.png | OP15-025 | OP15-025 | Visual weakness | OP15-025 | NEEDS_REVIEW |
| P4-0033 | OP080126_HOLO_5412.png | OP13-016 | OP13-016 | Family absent | EB01-036 | UNIDENTIFIED |
| P4-0034 | OP080126_HOLO_5413.png | OP13-091 | OP13-091 | Family absent | ST03-008 | UNIDENTIFIED |
| P4-0035 | OP080126_HOLO_5414.png | OP13-110 | OP13-110 | Family absent | EB01-053 | UNIDENTIFIED |
| P4-0036 | OP080126_HOLO_5415.png | OP13-019 | — | OCR failure | EB02-010 | UNIDENTIFIED |
| P4-0037 | OP080126_HOLO_5416.png | OP13-096 | — | OCR failure | EB02-007 | UNIDENTIFIED |
| P4-0038 | OP080126_HOLO_5417.png | OP13-037 | OP13-037 | Family absent | EB02-002 | UNIDENTIFIED |
| P4-0039 | OP080126_HOLO_5418.png | OP13-057 | — | OCR failure | EB01-009 | UNIDENTIFIED |
| P4-0040 | OP080126_HOLO_5419.png | OP13-083 | OP13-083 | Family absent | OP12-085 | UNIDENTIFIED |
| P4-0041 | OP080126_HOLO_5420.png | OP13-017 | — | OCR failure | OP05-047 | NEEDS_REVIEW |
| P4-0042 | OP080126_HOLO_5421.png | OP13-114 | — | OCR failure | EB01-052 | UNIDENTIFIED |
| P4-0043 | OP080126_HOLO_5422.png | OP13-104 | — | OCR failure | OP12-108 | UNIDENTIFIED |
| P4-0044 | OP080126_HOLO_5423.png | OP13-076 | — | OCR failure | EB02-010 | NEEDS_REVIEW |
| P4-0045 | OP080126_HOLO_5424.png | OP13-080 | OP13-080 | Family absent | EB03-043 | UNIDENTIFIED |
| P4-0046 | OP080126_HOLO_5449.png | OP16-042 | OP16-042 | Family absent | EB03-032 | UNIDENTIFIED |
| P4-0047 | OP080126_HOLO_5450.png | OP15-077 | — | OCR failure | EB01-050 | NEEDS_REVIEW |
| P4-0048 | OP080126_HOLO_5451.png | EB04-003 | — | OCR failure | EB03-039 | NEEDS_REVIEW |
| P4-0049 | OP080126_HOLO_5452.png | OP15-066 | P-156 | OCR incorrect | OP15-066 | UNIDENTIFIED |
| P4-0050 | OP080126_HOLO_5453.png | OP16-048 | OP16-048 | Family absent | EB01-033 | UNIDENTIFIED |
