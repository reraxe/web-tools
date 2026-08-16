# SAM Challenger v1 Shadow Comparison

Status: **measurement complete; shadow-only; production rollout not approved**  
Date: 2026-08-16  
Challenger: `sam-challenger-v1-candidate-union-shadow`

## Scope and invariants

SAM Challenger v1 changes candidate generation only. The current SAM v1 module is unchanged. The challenger reuses the completed SAM v1 job's frozen OCR evidence and applies the same visual similarity function, confidence formula, thresholds, scan-quality blocks, OCR/visual conflict block, variant-ambiguity block, and authority rules after building a broader candidate pool.

The candidate pool is the deterministic union of:

1. the trusted local-OCR card family, when the existing OCR policy produced a valid result;
2. the 64 strongest card families from a global visual-neighbor search;
3. up to 24 visual families from independently available batch set context; and
4. existing non-OCR number context, when present.

Trusted OCR nominates a family only. It cannot grant authority. TCGplayer normalization is not used for candidate generation, ranking, or authority. Family ranking and printing/variant resolution are returned as separate stages. The challenger performs no writes and cannot apply identity.

No schema or migration was added. Migration `0014_v22_phase7_sam_recognition` remains current. No production setting enables the challenger. The QA panel appears only when a shadow report path is explicitly configured.

## Frozen benchmark evidence

The frozen 50-scan Pass 4 artifacts were the only benchmark evidence. They were read, not regenerated or modified.

| Artifact | SHA-256 |
|---|---|
| `PASS4_50_FROZEN_BLIND_PREDICTIONS.json` | `12df14af91879e622dc85adb59bc1911c508cb25794ea9d4cdd1ea83276010f7` |
| `PASS4_50_PER_SCAN_RESULTS.csv` | `9167372943c7578589ce70f8ca4143ea54ccf920e247392eda6b3684bbebf128` |
| `PASS4_50_EVALUATION_SUMMARY.json` | `ab99348363927a8a5acc412fde5844e991cb8bf6864cebada2cbb1090c0ba583` |
| Frozen disposable database, before and after shadow run | `73d30154b5b271cabc486d6ee7e8a312ba2126ebfcb1d31b9c40358e2e6d8e0c` |

The identical before/after database hash confirms that the shadow run created no jobs, candidates, decisions, identities, inventory changes, or economic changes.

## Results

| Measure | SAM v1 | Challenger v1 | Change |
|---|---:|---:|---:|
| Correct family entered candidate pool | 9/50 (18%) | **50/50 (100%)** | +41 |
| Correct top family | 9/50 (18%) | **49/50 (98%)** | +40 |
| OCR correct | 26/50 (52%) | 26/50 (52%) | unchanged; frozen OCR reused |
| Auto Match | 2 | 0 | -2 |
| Needs Review | 13 | 47 | +34 |
| Unidentified | 35 | 3 | -32 |
| False auto-matches | **0** | **0** | safety gate preserved |
| Original five correct top families | 1/5 | **5/5** | full top-family recovery |
| Average end-to-end latency | 1,365.76 ms | 1,418.10 ms | +52.34 ms |
| Median end-to-end latency | 1,506.43 ms | 1,553.75 ms | +47.32 ms |
| P95 end-to-end latency | 2,222.67 ms | 2,267.07 ms | +44.40 ms |

Challenger-only candidate generation averaged 187.58 ms, with a 181.38 ms median and 248.13 ms maximum. End-to-end challenger latency combines that measured shadow time with the unchanged frozen OCR time. It is therefore a controlled estimate, not a second OCR execution.

The candidate pool averaged 126.04 reference images across exactly 64 card families. All 26 correct OCR reads remained correct top families. Of the 24 scans without correct OCR, global visual search produced 23 correct top families.

The only wrong top-family result was `P4-0036`: expected `OP13-019`, visual top `OP07-019`. It remained `NEEDS_REVIEW`, not authoritative.

## Authority and printing behavior

The broader pool surfaced multiple reference images for the same family in 49/50 scans. The existing variant-ambiguity safeguard therefore blocked automatic authority in those cases. This is expected and desirable for this candidate-generation-only challenger: the family stage improved sharply while the printing stage remained unresolved.

Final challenger disposition was:

- 0 Auto Match
- 47 Needs Review
- 3 Unidentified
- 0 false auto-matches

The three unidentified scans had the correct top family, but existing OCR conflict/reference and variant safeguards kept them below authority. No threshold or exception was relaxed.

## Safety-gate decision

All authorized measurement gates passed:

- **FALSE AUTO-MATCHES = 0:** passed.
- Correct-family candidate inclusion above 9/50: passed at 50/50.
- Correct top-family accuracy above 18%: passed at 49/50 (98%).
- Original five-card regression recovery: passed at 5/5 top-family.

## Recommendation

Keep SAM Challenger v1 in shadow-only mode. Candidate generation is validated strongly enough to continue as the challenger baseline, but it is not ready to replace SAM v1 because printing/variant resolution remains unresolved for 49/50 scans and the candidate pool adds about 52 ms average end-to-end latency.

The next approval, if granted, should be a separate printing/variant-resolution challenger that consumes the selected family without weakening any current authority gate. It should be benchmarked against the same frozen 50 scans plus printing-labeled physical evidence before any production rollout discussion. No threshold tuning is recommended from this run.

## Generated artifacts

- `validation/sam_challenger_v1_shadow/SAM_CHALLENGER_V1_SHADOW_COMPARISON.json`
  - SHA-256: `86b719ed429f35cbf6b26edbb058f4546c9c7987216c1ee122de60febeef09fe`
- `validation/sam_challenger_v1_shadow/SAM_CHALLENGER_V1_SHADOW_PER_SCAN.csv`
  - SHA-256: `4a324c85f4298ec9ee43fc7b91b9d65f083a31eccfade7e28292059d941946dc`

The JSON is the backend source for the disposable QA panel. The frontend formats only these backend-produced comparison facts.
