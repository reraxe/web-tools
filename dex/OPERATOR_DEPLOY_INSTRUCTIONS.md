# DEX v2.4-live Operator Deployment

Use [`OPERATOR_DEPLOY_INSTRUCTIONS_v2.4-live.md`](OPERATOR_DEPLOY_INSTRUCTIONS_v2.4-live.md) and [`DAY_ZERO_v2.4-live.md`](DAY_ZERO_v2.4-live.md).

This package prepares the first clean LIVE environment. It does not authorize automatic deployment. Preserve TEST, create separate LIVE writable storage, verify the immutable `v2.4-live` image and Day Zero state, and never reuse this initialization procedure for an ordinary future LIVE upgrade.

Record the resulting GitHub commit SHA. Before Jenkins, verify `app.py`, `static/index.html`, `static/app.js`, `static/styles.css`, `Dockerfile`, and the complete accepted upload manifest against `DEPLOY_SHA256SUMS.txt`. Do not trigger Jenkins if any file is missing or mismatched. A backend/frontend version or deployed-file mismatch is a deployment-integrity failure, not a browser-cache assumption.
