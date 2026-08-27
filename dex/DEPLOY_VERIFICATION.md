# DEPLOY Verification — DEX v2.5.1-live

Build identifier: `DEX-v2.5.1-live-SAM-operator-fallback-20260827`  
Target image: `192.168.2.92:5000/apps/dex:v2.5.1-live`

The DEPLOY artifact is root-shaped: `app.py`, `Dockerfile`, runtime modules, `static/`, `scripts/`, and `tests/` are directly at its root. There is no nested DEPLOY directory.

Final verification was performed from the actual DEPLOY contents. Results:

- complete ledger with zero missing, mismatched, or unexpected payload files;
- accepted v2.5-live plus approved SAM hotfix provenance with zero unexplained drift;
- Python regression: 348/348 passed;
- frontend regression: 29/29 passed;
- Phase 7 SAM focused regression: 24/24 passed;
- JavaScript syntax: passed;
- OP13-055 family/reference fallback regression: passed;
- v2.5 TCGplayer, quantity-pool, reconciliation, protection, SAM intake, sealed identity, WOLFF, and audit regressions: passed;
- migrations 0001–0020 with no later migration;
- disposable v2.4-live-like migration through 0020: passed;
- existing data facts preserved: passed;
- startup-created v2.5 business rows: zero;
- SQLite integrity: `ok`;
- foreign-key violations: zero;
- prohibited/private artifacts zero;
- deployment not performed.

The committed GitHub `/dex/` tree must be verified against `DEPLOY_SHA256SUMS.txt` before Jenkins.
