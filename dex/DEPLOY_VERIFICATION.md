# DEPLOY Verification — DEX v2.5-live

Build identifier: `DEX-v2.5-live-promotion-20260825`  
Target image: `192.168.2.92:5000/apps/dex:v2.5-live`

The DEPLOY artifact is root-shaped: `app.py`, `Dockerfile`, runtime modules, `static/`, `scripts/`, and `tests/` are directly at its root. There is no nested DEPLOY directory.

Verification gates:

- complete DEPLOY ledger: all entries present and matching;
- authoritative source/package parity: zero unexplained mismatches;
- Python regression: 346/346 passed from DEPLOY;
- frontend regression: 28/28 passed from DEPLOY;
- JavaScript syntax: passed from DEPLOY;
- disposable v2.4-live-like migration: 0019 to 0020 passed;
- pre-existing data facts: preserved;
- startup-created v2.5 business rows: zero;
- SQLite integrity: `ok`;
- foreign-key violations: zero;
- prohibited/private artifacts: zero;
- secrets and machine-local runtime artifacts: zero;
- deployment: not performed.

The committed GitHub `/dex/` tree must be verified against `DEPLOY_SHA256SUMS.txt` before Jenkins.

