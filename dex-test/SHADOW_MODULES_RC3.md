# RC3 Shadow and Research Modules

These modules are present for reproducible research and review only:

- `dex_sam_challenger.py`: SAM Challenger v1 shadow comparison path already isolated from authoritative decisions.
- `research/sam_challenger_v2/`: printing/variant challenger design, harness, and tests.
- `research/geometry_challenger_v1/`: geometry normalization experiment, reports, and tests. It is not automatically routed.
- `research/tcgplayer_commercial_printing_catalog_bridge_v1/`: read-only descriptive commercial-printing provider. It does not select a physical printing and has no recognition authority.
- `research/challenger_v2_variant_gauntlet_harness/`: tooling only; physical scans, ground truth, blind stages, and results are excluded.

These components must not alter operator-visible RC3 behavior. Any future integration requires separate approval, frozen-benchmark evaluation, and the zero-false-authoritative-identity safety gate.

