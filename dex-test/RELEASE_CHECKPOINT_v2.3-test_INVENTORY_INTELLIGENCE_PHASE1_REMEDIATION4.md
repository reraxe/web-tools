# DEX v2.3-test Inventory Intelligence Phase 1 Remediation 4

Release status: **ACCEPTED FOR OPERATOR-CONTROLLED DEPLOYMENT**

This immutable checkpoint preserves the accepted Remediation 3 behavior and adds active semantic-state hygiene for repeated receipt extraction. Only the newest valid extraction generation participates in current receipt interpretation. Superseded or removed-document assertions remain durable audit history and cannot influence current receipt lines, math, product matching, allocation, or acquisition confirmation.

The review UI separates the current interpretation from immutable historical assertions, keeps the operator-facing Needs Review count scoped to active items, and exposes extraction/parser provenance. Merchant suggestions refresh from the newest extraction only while preserving operator-entered authority.

## Safety results

Fantasy Bay remains blocked with unresolved `$0.53` evidence; the current receipt math is `UNRECONCILED`, automatic allocation is unavailable, confirmation fails safely, and no basis event is written. A valid reconciled single-product receipt still receives its established allocation path. Mom and Pop remains `POLICY_REQUIRED` with no inferred mixed-purchase policy.

## Database and compatibility

There is no schema change. Migrations remain 0001–0016 with no 0017. Runtime identity remains `v2.3-test`. Remediation 3 is the immediate application-code rollback checkpoint.

## Verification

The complete 229-test Python baseline and 23-test frontend baseline passed from the actual DEPLOY contents. Runtime import, isolated startup/health, migration integrity, package hashes, privacy scans, and the exact Remediation 3 → 4 source diff also passed.

No production deployment was performed.

Packaging note: the frozen candidate intentionally leaves the Docker OCI version label at the prior Remediation 3 identifier. The deployable application and visible runtime identity are `v2.3-test`; use the exact new immutable Remediation 4 image tag in the operator instructions and record its digest. The label was not silently changed after the freeze.
