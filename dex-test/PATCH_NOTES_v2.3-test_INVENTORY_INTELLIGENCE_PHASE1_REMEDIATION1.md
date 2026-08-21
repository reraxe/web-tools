# DEX v2.3-test Inventory Intelligence Phase 1 Remediation 1

Status: implementation candidate; acceptance and deployment not yet approved.

This narrow remediation makes deterministic financial-summary and tender evidence outrank the generic positive-amount merchandise heuristic. Payment, tender, amount-due, balance-due, change, and ambiguous financial OCR lines now fail closed outside product matching. It also reserves `STRUCTURAL` for actual receipt structure and routes unreadable OCR to `UNKNOWN / UNRESOLVED`.

The sidebar obtains `v2.3-test` from the existing `/api/health` runtime authority instead of carrying a separate hard-coded display version.

No schema migration was added. Migration 0016, receipt allocation, mixed-purchase `POLICY_REQUIRED`, economics, inventory authority, SAM, Challenger, and marketplace behavior are unchanged.
