# DEX v2.2-test — Phase 7 SAM Confirm Correction Hotfix

Status: hotfix complete; operator retest required; production deployment **NOT APPROVED**  
Runtime identity: `v2.2-test`  
Pre-hotfix restore point: preserved Phase 7 SAM Recognition checkpoint/package

## Root Cause

The frontend correctly retained the operator-selected OP16-035 reference and changed the action to **Confirm Correction**, but `decideSam()` then called the native browser `prompt()` to collect the required audit note. The in-app browser does not support `prompt()` and threw before the API call. No request, backend validation, decision event, identity update, response, or queue refresh occurred. The exception was visible only in the browser console, so the operator saw an apparently inert button.

## Fix

- Show standardized correction reason and required operator note controls directly in the SAM review modal whenever the selected reference differs from SAM's original suggestion.
- Validate both fields before submission and expose missing facts in an inline `role="alert"` plus toast.
- Submit exactly one mutation while the action is pending; disable/mark the button busy to prevent double submission.
- Preserve selected reference and entered facts on backend rejection, stale revision, or network failure; keep the modal open and show the exact error inline.
- On success, identify the selected card number in the success message, close the modal, and reload dashboard/review queues.

The existing API and backend contract are unchanged. The selected identity becomes `OPERATOR_CORRECTED`; the original top suggestion remains on the recognition job and decision evidence; the operator-selected reference remains separate in the append-only decision. Recognition engine/rules/index versions and timestamps are preserved.

## Files Changed

- `static/app.js`
- `static/styles.css`
- `static/index.html`
- `tests/test_v22_phase7_sam.py`
- `tests/test_v22_phase7_sam_ui.cjs`
- `tests/test_v22_phase7_sam_correction.cjs` (new)
- Phase 7 README, patch notes, checkpoint, and upload-manifest documentation

No Python application service, schema, migration, recognition rule, confidence threshold, or economics implementation changed.

## Verification

- Python: **167 passed in 16.415 seconds**.
- JavaScript syntax: passed.
- Self-contained frontend regressions: **12 passed**.
- Live authoritative batch-detail frontend regression: passed.
- Desktop/mobile visual rendering: passed without browser console errors.
- Browser reproduction: missing note produced an inline error; valid OP16-035 correction fired once, closed the modal, displayed success, moved the card to Matched as Operator Corrected, and refreshed counts.
- API/database verification: authoritative identity OP16-035; effective state `OPERATOR_CORRECTED`; original top OP16-034 retained; selected reference recorded in the correction decision; batch economics unchanged.
- Failure regression: rejected/stale mutation retains OP16-035 selection, review modal, entered details, inline error, and retry ability.

## Disposable Retest

Use the fresh URL reported with the completion handoff. Open `OP-SAM-P7-CORRECT`, Find Match `OP16-035`, select **Operator Correct Answer**, complete the visible reason/note fields, and choose **Confirm Correction**.

Expected: one successful request, visible confirmation, closed review, Operator Corrected in Matched, OP16-035 authoritative, and OP16-034 preserved in recognition history.

## Rollback

Restore the preserved pre-hotfix Phase 7 package. No database rollback is needed because the hotfix introduces no schema or data migration. A correction successfully recorded under the existing Phase 7 API remains valid append-only history and must not be deleted manually.

## Approval Gate

Operator retest is required. Production deployment, another development phase, JANA, and cross-TCG recognition remain unauthorized.
