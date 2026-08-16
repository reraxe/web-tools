# DEX v2.2-test RC3 Hotfix 2 Patch Notes

- Added explicit, audited manual purchase-facts fallback for unsupported/failed receipt image extraction.
- Kept failed extraction failed and non-authoritative; no Receipt Image OCR was added.
- Preserved attached receipt images as viewable evidence.
- Kept both HF1 reconciliation equations and every authoritative confirmation requirement unchanged.
- Removed impossible image-extraction Retry actions.
- Separated active receipt state from removed-document extraction history to prevent ghost retry warnings.
- Preserved line confirmation, unsaved form state, disclosures, viewport, and practical focus across fallback mutations.
- Added no migration and changed no SAM, economics, catalog, pricing, or downstream inventory behavior.
