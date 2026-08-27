# Accepted TEST Source Verification

Accepted source: `v2.5-test` TCGplayer Inventory Bootstrap + Reconciliation V1  
Source-ledger entries: `157`  
Source-ledger SHA-256: `02a491a0f7fd5d9e8488ccc3a4c149ce020f3db03e795836376c18589e1c4f75`

The accepted TEST worktree was not modified during promotion. The LIVE worktree was created separately.

Exactly ten accepted-source files differ in LIVE, all for release identity, packaging verification, or its assertions:

- `app.py`
- `Dockerfile`
- `DEPLOY_VERIFICATION.md`
- `static/index.html`
- `VERSION`
- `tests/test_app.py`
- `tests/test_inventory_intelligence_phase1_remediation2_ui.cjs`
- `tests/test_inventory_intelligence_phase1_remediation1_ui.cjs`
- `tests/test_v22_phase1_inbound.py`
- `tests/test_v25_tcgplayer_inventory_ui.cjs`

All other accepted files in the source ledger match. Promotion-only files are documentation, manifests, and the disposable migration-verification helper. There is zero unexplained drift.
