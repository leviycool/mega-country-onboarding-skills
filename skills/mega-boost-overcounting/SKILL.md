---
name: mega-boost-overcounting
description: Detect, quantify, explain, and validate fixes for BOOST workbook or ETL overcounting. Use when formulas or classification flags may assign one raw line to multiple peer categories; when reviewing SUMIFS overlaps, duplicate tag rules, rollups, cross-tabs, ownership precedence, wrong-year references, or self-double-counting; or when proving that a workbook or DLT correction removed overlaps without changing unrelated data.
---

# MEGA BOOST Overcounting

Audit row membership rather than guessing from aggregate differences. The aim is to identify the exact source rows claimed more than once, distinguish expected hierarchy from real conflicts, and document who owns each confirmed overlap.

## Prepare the audit

Read [references/method.md](references/method.md) and start from [assets/overlap-config.example.json](assets/overlap-config.example.json).

Collect:

- the immutable source workbook and hash;
- raw microdata with a stable source-row ID;
- structured formula rules with every additive branch preserved;
- a reviewed code dictionary with dimension and depth;
- approved, revised, and executed measures where present;
- authoritative cached formula values;
- an explicit list of totals, meta-rollups, cross-tabs, and expected subsets.

Audit stages independently. For ODS, use a converted XLSX only to inspect formulas and keep the original ODS values as the reference.

## Separate the failure modes

Use these labels consistently:

| Type | Meaning |
|---|---|
| `peer_overlap` | one row belongs to two mutually exclusive categories at the same depth |
| `same_value_duplicate` | two codes represent the same category and select the same rows |
| `self_double` | two additive branches in one formula select the same row |
| `formula_defect` | a bad reference, array behavior, broken name, or unsupported operation changes the result |
| `pipeline_ownership` | silver/gold assigns multiple owners, loses an owner, or applies the wrong precedence |

Membership in one economic and one functional category is expected. Parent-child rollups are also expected unless both are incorrectly used as peer line owners. Review subnational cross-cutting tags outside the primary economic and functional peer groups.

## Run the detector

List the full expected code set for every required stage in the config, then run:

```bash
python scripts/detect_tag_overlaps.py \
  --config <overlap-config.json> \
  --tag-rules <tag-rules.csv> \
  --code-dictionary <code-dictionary.csv> \
  --output <overlap-report.json>
```

The audit is incomplete if a stage selects no rules, an expected code is missing, an unexpected code appears, the dictionary repeats a code, or the parser drops a material branch. Zero overlap with zero coverage is a failed audit.

## Quantify what happened

For each peer pair and year, report:

- intersecting source-row count and sample IDs;
- each category's full measure total;
- the amount on intersecting rows;
- overlap ratio against the smaller category;
- relationship type and whether the predicates are identical;
- formula cells, sample formulas, parser status, and unsupported branches.

Also calculate unique affected rows and net excess by dimension and year. A row shared by three categories appears in several pairs, so pairwise exposures cannot be added together and called total overcount.

## Record the ownership decision

For every confirmed conflict, record the chosen owner, losing category, rationale, reviewer, affected stages and years, implementation location, exact exclusion or precedence rule, and expected before/after amounts.

The narrower category is often the better default candidate, but predicate shape alone does not settle business ownership. Escalate when the workbook is internally inconsistent or the label meaning is unclear.

## Implement and prove the fix

- Apply one reviewed rule across stages and years unless evidence supports a versioned exception.
- Evaluate economic and functional ownership independently.
- Order specific subcategories before broader ones.
- Build parent totals downstream instead of assigning them as competing line owners.
- Keep unmatched rows visible and keep each subcategory consistent with its parent.
- Use the authorized formula-rewrite flow in `$mega-boost-onboarding` when the source workbook changes.

Finish only after the corrected scope has zero unresolved peer overlaps and self-doubles, exact expected stage/code coverage, matched supported formula results, explicit unsupported coverage, and one-owner-per-dimension pipeline tests. Re-run workbook, country-gold, aggregate, and discrepancy checks and record the before/after monetary effect.
