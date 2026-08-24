# v2.4-live Rollback

Rollback target: the exact accepted TEST/WOLFF operational image tag and digest recorded immediately before cutover.

1. Stop routing new operator intake to the failing LIVE application.
2. Reattach the unchanged LIVE storage lineage to the recorded prior application image.
3. Verify startup and `/api/health`.
4. Keep LIVE `/data`, `/scanner-inbox`, and reference storage unchanged.

Do not delete migration rows, reseed, replace, or restore LIVE storage unless a verified data-level defect exists and the operator separately authorizes that data action after a verified backup. Application rollback is the default and safest recovery.
