# Operator Deployment Instructions — Separate Approval Required

Suggested immutable image tag: `192.168.2.92:5000/apps/dex:v2.3-test-inventory-intelligence-phase1-remediation1`.

1. Open `DEX_v2.3-test_INVENTORY_INTELLIGENCE_PHASE1_REMEDIATION1_DEPLOY`.
2. Select everything inside it and upload those contents directly into the GitHub `dex-test` root. Do not upload the outer DEPLOY folder.
3. Confirm the immutable image tag above.
4. Use the normal Jenkins **Build Now** action.
5. Confirm the build and registry push succeed.
6. Update the Portainer stack to the new immutable image tag.
7. Update the stack, hard refresh DEX, and verify `/api/health` and the visible `v2.3-test` identity.

No deployment was performed while creating this candidate.
