# Safe Excel formula rewrites

Rewrite formulas only when the user explicitly authorizes an upstream workbook correction. Detection and ETL implementation do not imply that authority.

## Required protocol

1. Hash and preserve the authoritative source.
2. Create a correction manifest with sheet, cell, old formula, new formula, old cached value, expected new value, reason, reviewer, and linked discrepancy/overlap evidence.
3. Independently calculate the expected result from raw microdata before editing.
4. Patch only listed cells in a new `.xlsx` copy. Use `scripts/patch_xlsx_formulas.py` for OOXML-safe targeted changes.
5. Set automatic/full calculation, remove stale calculation-chain references, and never claim that a cached value proves Excel recalculated it.
6. Open in a real spreadsheet engine when available, save, and re-read values. Do not use `openpyxl` as a formula evaluator.
7. Run `scripts/verify_xlsx_patch.py` to require exact formula changes, unchanged styles, and no unexpected archive-member changes.
8. Re-run formula-to-microdata, overcounting, discrepancy, and DLT ownership checks.
9. Compare formula-error counts before and after; do not introduce `#VALUE!`, `#REF!`, `#N/A`, or other errors.
10. Store the corrected copy, patch manifest, validation report, and original hash together.

## Patch manifest format

```json
[
  {
    "sheet": "Executed",
    "cell": "J220",
    "old_formula": "=SUMIFS(...) ",
    "new_formula": "=SUMIFS(...) ",
    "old_cached_value": 0,
    "expected_after": 123.45,
    "reason": "Wrong year-header reference",
    "reviewer": "name-or-ticket"
  }
]
```

Trim incidental whitespace in real manifests and preserve exact formulas. The patcher refuses an old-formula mismatch unless explicitly overridden.

## Release rule

Do not replace shared or authoritative copies automatically. Report the corrected artifact and validation evidence, then update each external source location only with the required authorization and a recorded version/hash.
