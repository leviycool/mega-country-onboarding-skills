# Workbook-to-DLT implementation guide

Start from the source inventory. The workbook's owner, authority, years, stages, currency, amount unit, and local hash should agree with the manifest before any formula or schema assumptions enter the pipeline.

## Workbook reconnaissance

Inspect before coding:

- sheet name, visibility, used range, row/column counts, and likely role;
- raw headers and whether schemas change by year range;
- named ranges and whether they map to raw columns, whole columns, or broken references;
- Approved, Revised, and Executed formula cells and cached values;
- hardcoded numeric values inside otherwise formula-driven regions;
- hidden supplemental sheets and formulas that reference them;
- external workbook links, pivots, tables, merged cells, and macros;
- missing-value markers, localized strings, and fiscal-year types.

Use `scripts/workbook_inventory.py` as a first pass. Its role guesses are heuristic; verify them from formulas and source semantics.

For native ODS, record the current tooling boundary explicitly: use the original file for authoritative cached values and a traceable XLSX conversion for formula inspection when needed. The `.xlsx` duplicate checker does not by itself prove that the original ODS archive has identical structure.

## Duplicate contract

Run `scripts/check_workbook_duplicates.py` before extraction. Configure every workbook sheet or list a genuinely non-ingested presentation/pivot sheet in `excluded_sheets` with owner, timestamp, and reason:

- detect Unicode/case/whitespace-normalized sheet-name collisions across the workbook;
- reject duplicate normalized headers because downstream readers may silently rename or overwrite them;
- test exact populated rows on raw microdata sheets;
- define the smallest stable business key that should be unique, such as source row ID or year plus transaction/code fields;
- list a reviewed duplicate-key exception only when the repeated rows are semantically distinct; record its exact values, owner, timestamp, reason, and distinguishing evidence.

An exact duplicate row, a repeated business key, and an overlapping classification rule are different failure modes. Resolve source duplication before using the overcounting audit so duplicate input rows do not masquerade as rule overlap.

## Rule representation

Represent each classification rule with at least:

| Field | Purpose |
|---|---|
| `stage` | Approved, Revised, or Executed |
| `code` and `category` | workbook tag and label |
| `source_sheet` | raw sheet supplying the measure |
| `measure` | named range or raw measure column |
| `years_covered` | years sharing the same formula shape |
| `criteria_json` | OR branches of ANDed predicates |
| `sample_formula` | provenance and review |
| `formula_cell` | trace back to the workbook |
| `parser_status` | matched, mismatch, or unsupported reason |

Treat `SUMIFS(A, c1, v1) + SUMIFS(A, c2, v2)` as two OR branches. Do not collapse it to the first block. Treat cell additions and subtractions outside `SUMIFS` as separate formula graph nodes; if the parser cannot evaluate them, report the gap.

## Classification architecture

Prefer a line-level silver table:

1. Apply uniform source exclusions once.
2. Evaluate reviewed economic rules and assign the first eligible owner.
3. Evaluate reviewed functional rules independently and assign the first eligible owner.
4. Keep unmatched rows with null owners.
5. Join the reviewed code dictionary to derive canonical labels.

This architecture makes overlap ownership explicit and prevents a tag-level aggregate union from duplicating raw lines. Parent totals belong downstream as aggregates, not as competing line owners.

Prioritize specific subcategories before broad rollups. Use workbook row order only within a reviewed priority tier. Record exceptions as data or constants close to the country code.

## Required output semantics

- `admin0/admin1/admin2`: who spent the funds.
- `geo0/geo1`: where funds were allocated.
- `func/func_sub`: functional ownership.
- `econ/econ_sub`: economic ownership.
- `approved/revised/executed`: numeric local-currency amounts, explicitly cast.
- `is_foreign`: a non-null boolean when derivable, otherwise a documented missing field.

Derive `is_foreign` inside `scripts/check_foreign_funding.py` from the reviewed raw-source predicate config, not from the final label, already-produced flag, or a copied expected column. Include raw predicate fields, stable source-row IDs, and the pipeline flag in the audit export. The final evidence must include the predicate-config hash and source columns, ID uniqueness, flag-domain/null results, mismatch samples, and domestic/foreign row counts and amounts by year.

Read the current aggregate schema and canonical labels before selecting columns. Use null, not invented categories, for unavailable information.

## Common failure modes

- A static bronze schema is shifted by one source column and silently corrupts rows.
- Header normalization produces duplicate column names.
- Repeated exact rows or business keys multiply totals before classification.
- Formula criteria change language or column names across year ranges.
- Hidden-sheet supplements are omitted.
- Direct overrides cannot be reproduced from raw data.
- Cross-tab codes are treated as line owners.
- Broad rollups capture rows before specific categories.
- Missing rows are dropped instead of surfacing as null classifications.
- `approved` or `executed` reaches the aggregate with a non-double type.
- `is_foreign` is populated from a copied output column rather than independently validated source logic.
- A country is added to the aggregate before population or geography dependencies exist.

Pin a bronze schema only after deriving it from the actual extracted CSV and testing every range. Otherwise retain inference with explicit post-read casts and sufficient compute.
