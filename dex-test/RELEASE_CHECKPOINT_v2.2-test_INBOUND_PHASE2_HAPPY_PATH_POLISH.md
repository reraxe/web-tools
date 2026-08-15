# DEX v2.2-test Inbound 2.0 Phase 2 Happy-Path Polish Checkpoint

Scope: Accounting-by-Default polish for the approved three-screen Guided Acquisition wizard only. The accepted Phase 2 UX Revision package remains preserved as the known-good restore point. Phase 3 UPC/catalog, documents/extraction, SAM, downstream batch projection, global Attention Center, deployment, and production data are not authorized.

## Runtime behavior

- Runtime remains `v2.2-test`; established Phase 3–7C economics calculation version remains `acquisition-rip-v3`.
- Inbound acquisition calculations and audit payloads identify rule version `inbound-acquisition-v1`.
- New Acquisition remains a three-screen, resumable flow. Legacy New Batch remains under Advanced / Legacy.
- Clean one-line acquisitions show automatic 100% landed-cost allocation, backend per-unit cost, **Reconciled exactly**, and one primary **Confirm Acquisition** action.
- Routine Assigned Landed Cost, Allocation Method, allocation checkbox, and separate allocation-confirmation controls are absent from the clean one-line path.
- Unresolved multi-line allocation, missing cost, explicit zero cost, and purchase discrepancies render as **Purchase needs attention**. Manual/protected controls appear only after opening **Resolve**.
- Autosave stores draft facts and wizard position only. It cannot confirm economics, resolve an exception, or advance lifecycle.
- Confirmation stops at `READY_FOR_INTAKE` and creates zero processing batches, cards, sealed units, or rip sessions.

## Automatic accounting and audit evidence

At final confirmation of a one-active-line acquisition with authoritative final USD, the backend atomically:

1. assigns all final USD cents to that line using `SINGLE_LINE_100_PERCENT`;
2. derives deterministic exact-cent per-unit values where quantity is known;
3. writes an append-only automatic-allocation event containing source facts, affected acquisition/line, calculation version, method, result cents, per-unit structure, and timestamp;
4. writes the final `AUTHORITATIVE_CONFIRMATION` event with a link to the automatic-allocation event and the reconciliation facts;
5. transitions only the acquisition to `READY_FOR_INTAKE`.

## Schema and migrations

No migration or schema change is added by this polish. Existing migrations `0006`, `0007`, and `0008` are unchanged. The richer audit evidence uses the existing `acquisition_events.payload_json` field. An already-migrated database receives no new migration-ledger entry at startup.

## API and presentation contract

- Acquisition payloads include backend-generated `attention` metadata with decision level, attention level, reason codes, resolve mode, operator-judgment flag, and future Attention Center compatibility flags.
- Supported decision levels are `AUTOMATIC`, `AUTOMATIC_VISIBLE`, and `NEEDS_ATTENTION`.
- No global notification item is created in this phase.
- The frontend displays and formats backend results; it does not reproduce allocation or reconciliation formulas.

## Verification

- 104 Python regression tests passed.
- Direct JavaScript acquisition-wizard regression passed.
- JavaScript syntax check passed.
- Browser QA passed on a fresh disposable `v2.2-test` database:
  - happy path: three sealed units, `$120.00` final landed cost, `$120.00` automatic line allocation, `$40.00` per unit, exact reconciliation, and one final confirmation;
  - exception path: 90% purchase discrepancy shown as Critical/Extreme Needs Attention with protected controls under Resolve;
  - incomplete path: missing final USD shown as Unknown / Setup incomplete, resumable, and confirmation-blocking.
- Database verification confirmed one automatic allocation event for the happy path and zero downstream batches/cards/sealed units/rip sessions.
- The Phase 7C performance guard remains green at 40 batches / 4,000 cards.

## Known limitations

- Multi-line acquisitions without sufficient evidence still require manual exact-cent allocation under Resolve; automatic receipt-derived proposals belong to a later phase.
- No UPC/catalog, receipt upload/storage/extraction, SAM change, downstream projection, or Attention Center.
- Receipt Take Photo and Upload Receipt controls remain disabled placeholders.
- Product choices remain the current DEX TCG set.
- Production deployment remains operator-controlled and is not part of this checkpoint.

## Rollback

1. Stop only the failed disposable/new runtime; do not alter production without a separate operator-approved deployment step.
2. Restore the preserved Phase 2 UX Revision application checkpoint.
3. Because this polish adds no schema migration, no ledger manipulation or schema rollback is required.
4. Preserve a matching database copy before application rollback if new draft/confirmation events must be retained. Never delete event history or migration rows manually.

## Git upload manifest

Upload the contents of the packaged checkpoint, including root Python source, `static/`, `tests/`, approved `scripts/`, documentation/notes/manifests, `VERSION`, dependencies, and unchanged deployment descriptors.

Do not upload databases or SQLite sidecars; storage or scanner directories; source databases; inventory/card images; disposable QA data; generated output; caches; `__pycache__`; `.pytest_cache`; logs; secrets; credentials; keys; `.env`; or machine-specific files.

## Disposable operator QA

Open the reported disposable URL and use Inbound:

- **Happy Path QA Shop** is confirmed Ready for Intake and shows `$120.00` assigned to one three-unit sealed line at `$40.00` per unit.
- **Severe Attention QA Shop** resumes at Review with a 90% Critical/Extreme mismatch and protected controls under Resolve.
- **Incomplete Unknown-Cost QA Shop** resumes at Review with Unknown / Setup incomplete and disabled confirmation.
