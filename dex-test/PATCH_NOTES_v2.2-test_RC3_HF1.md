# DEX v2.2-test RC3 Hotfix 1 Patch Notes

Release: `v2.2-test-rc3-hf1`  
Status: packaged release candidate; **not automatically deployed**

This targeted hotfix makes legitimate mixed inventory/noninventory purchases confirmable without falsifying inventory basis.

For the operator-trial case, DEX now preserves both reconciliations:

- Purchase components `$136.16` plus adjustment `-$1.99` equals final paid `$134.17`.
- Inventory landed cost `$110.00` plus explicit excluded noninventory `$24.17` equals final paid `$134.17`.

Excluded noninventory remains outside inventory basis. It is not a DEX tax-deductibility, owner-draw, expense-category, or general-ledger decision.

The Review screen displays both equations separately, retains unsaved resolution inputs across line mutations, and marks confirmed line allocations unmistakably in green. Editing a confirmed line cost or method invalidates confirmation and requires reconfirmation.

Migration 0015 is additive and does not alter existing acquisition facts. RC3-r4 remains the rollback checkpoint.
