# DEX v2.4-test rollback

Immediate application rollback authority is the image tag and digest actually running immediately before the v2.4 cutover. The operator must record both before deployment.

1. In Portainer, restore that exact prior image tag/digest.
2. Update the stack without changing ports, volumes, environment, or storage.
3. Verify `/api/health`, the visible version, and inventory access.

Do not restore or delete production storage merely because the new image failed to start. If a verified data-level problem requires storage rollback, obtain explicit operator approval, preserve the current storage as a recoverable copy, and restore the verified pre-cutover backup as a whole. Never remove migration rows or authoritative facts manually.

Preserved prior software checkpoint: `DEX_v2.3-test_INVENTORY_INTELLIGENCE_PHASE1_REMEDIATION5_FULL_CHECKPOINT`. Use it only if it corresponds to the operator-confirmed prior image/build.
