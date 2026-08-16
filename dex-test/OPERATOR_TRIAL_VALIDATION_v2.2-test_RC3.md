# RC3 Post-Upload and Operator-Trial Validation

## Source/package validation

1. Upload exactly the files listed in `GIT_UPLOAD_MANIFEST_v2.2-test_RC3.txt`.
2. Confirm none of the entries in `GIT_EXCLUSION_MANIFEST_v2.2-test_RC3.txt` were uploaded.
3. Verify `SHA256SUMS.txt` and `PACKAGE_AGGREGATE_SHA256.txt`.
4. Confirm `VERSION`, `/api/health`, and the frontend identify `v2.2-test`.
5. Confirm migrations `0001` through `0014` are present in order.
6. Build the Docker image on the deployment host and confirm Tesseract plus all sibling Python imports.
7. Start against disposable or copied storage first; verify inventory counts before and after.

## Manual four-pack OP13 trial

1. Create **New Acquisition**.
2. Select **Pack Product**, identify One Piece OP13, and enter quantity **4**.
3. Enter the real purchase and receipt facts; confirm Accounting-by-Default reconciliation.
4. Confirm the acquisition and choose **Continue Intake**.
5. Start the intended Rip/Open workflow explicitly.
6. Scan the physical cards and review SAM outcomes.
7. Correct only through Human Review when required.
8. Verify inventory identities, batch/rip reconciliation, assigned basis, and Operational Economics.

Stop the trial and preserve evidence if any authoritative identity, quantity, or economic fact is incorrect. Operator trial success does not itself approve production or v2.2-stable.

