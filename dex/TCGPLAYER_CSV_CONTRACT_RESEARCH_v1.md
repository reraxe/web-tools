# TCGplayer Seller CSV Contract Research — v1

Research date: 2026-08-24  
Scope: operator-controlled inventory bootstrap/reconciliation only

## Official contract reviewed

- [Importing and Exporting CSVs to Mass Update Prices and Quantities](https://help.tcgplayer.com/hc/en-us/articles/115002358027-Importing-and-Exporting-CSVs-to-Mass-Update-Prices-and-Quantities)
- [Using Our Pricing Tools](https://help.tcgplayer.com/hc/en-us/articles/115002353707-Using-Our-Pricing-Tools)
- [Setting Prices for Your Channels](https://help.tcgplayer.com/hc/en-us/articles/360001479274-Setting-Prices-for-Your-Channels)
- [How do I process refunds?](https://help.tcgplayer.com/hc/en-us/articles/201399857-How-do-I-process-refunds)

The current official workflow exports Live inventory, permits priced zero-quantity rows, treats `Total Quantity` as reference data, and uses signed `Add to Quantity` values for changes. Imported rows enter Staged Inventory before the operator moves them Live. Duplicate TCGplayer IDs in one upload are rejected. Changed inventory rows require a valid marketplace price. Refund processing may optionally return inventory and can route returned zero-Live-quantity products into Staged Inventory.

## Implemented interpretation

1. Preserve the source CSV byte-for-byte outside SQLite, addressed by SHA-256.
2. Preserve every original header and source row for round-trip output.
3. Reject missing required headers, malformed integers/money, duplicate TCGplayer IDs, invalid encoding, oversized files, and missing trustworthy export time.
4. Treat `Total Quantity` as a marketplace observation. Only the explicitly confirmed first snapshot can create opening DEX quantity events.
5. Treat `Add to Quantity` as a delta on output. Never write a desired total into that column.
6. Do not create owned stock from zero-quantity rows.
7. Preserve marketplace price and all other source values; export only changed rows.
8. Require a fresh source snapshot and fail closed for missing required prices or a material destructive delta.
9. Produce a download only. DEX does not submit, stage, or move inventory Live.

The operator's supplied export did not contain `Pending Quantity`. The parser supports it when present and otherwise preserves the state as Unknown rather than zero.

## Private evidence boundary

The two operator exports used for verification remain in an ignored `private-fixtures/` directory inside the isolated v2.5 worktree. They are not source fixtures, are not named in committed code, and must never enter a release package. Test reports expose hashes and aggregate counts only.
