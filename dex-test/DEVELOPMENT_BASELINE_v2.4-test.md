# DEX v2.4-test development baseline

Status: **FROZEN DEVELOPMENT BASELINE**  
Frozen: 2026-08-22  
Identifier: `DEX-v2.4-test-WOLFF-SAM-Phase2-development-baseline-20260822`

This worktree is the approved post-hardening development baseline after the final presentation fixes. It is not a release package and is not deployment authorization.

## Included presentation fixes

- Operator-facing `JARVIS Simplified Economics` naming is now `WOLFF Simplified Economics`.
- `WOLFF` means **Working On Levelling Financial Flows**.
- Internal JARVIS module, API, route, test-contract, calculation, and historical names remain unchanged.
- A value with zero authoritative coverage displays `Unknown`; an authoritative covered zero displays `$0.00`.
- Item-level `Acquisition cost` is labeled `Parent acquisition cost`, while allocated acquisition cost remains a separate fact.

## Verification at freeze

- Python regression suite: **299/299 passed**.
- Frontend regression suite: **26/26 passed**.
- JavaScript syntax check: **passed**.
- Protected Remediation 5 receipt baseline: **234/234 hashes matched**.
- Protected baseline ledger SHA-256: `c999537d62f5e668d35c7dbbb81bf07a442d3fc3faa2ea789bfcafc1fd555c35`.
- Browser validation covered missing basis, authoritative `$0.00`, stale economics, partial coverage, SAM/economics coexistence, and item labels with no console errors.
- False printing authority gate: **passed**.
- Economics false-precision gate: **passed**.

## Baseline integrity fingerprint

The deterministic development-baseline aggregate covers **247 files** and is:

`3c22c2aa997315e4874e466fc8a99c788cd58f89e9bc7f3f88aeb5f86040d32a`

Reconstruction rule:

1. Recursively select regular files beneath this worktree.
2. Exclude `.git`, `__pycache__`, `.pytest_cache`, `*.pyc`, `*.pyo`, `*.db`, `*.sqlite`, `*.sqlite3`, `*.log`, this file, and `FROZEN_DEVELOPMENT_BASELINE_SHA256SUMS.txt`.
3. For every included file, produce `lowercase_sha256`, two spaces, and the worktree-relative path using `/` separators.
4. Sort records by relative path using case-sensitive ordinal ordering.
5. Join records with LF and include one final LF.
6. SHA-256 the resulting UTF-8 byte sequence without a byte-order mark.

Any future development must branch or copy from this baseline without mutating this frozen worktree.

## Release status

- Packaging: **NOT PERFORMED**.
- Deployment: **NOT PERFORMED**.
