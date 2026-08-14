---
name: mega-boost-onboarding
description: Audit a country BOOST Excel or ODS workbook and implement its extraction plus line-level bronze, silver, and gold pipeline in mega-boost. Use when onboarding or repairing a BOOST country, inventorying workbook structure and formulas, detecting duplicate sheets, headers, rows, or business keys, translating SUMIFS logic into Spark, validating foreign-funding flags, reconciling approved, revised, or executed totals, rewriting authorized formulas, or registering the country in BOOST jobs and aggregates.
---

# MEGA BOOST Onboarding

Turn the authoritative workbook into a reproducible line-level pipeline. Keep four things separate throughout the work: what the source says, what is wrong with it, which business decision resolves the issue, and what the pipeline implements.

## Read the workbook before designing the transform

Read [references/workbook-to-dlt.md](references/workbook-to-dlt.md), [references/discrepancy-checks.md](references/discrepancy-checks.md), and [references/formula-rewrites.md](references/formula-rewrites.md).

1. Confirm the workbook hash, owner, currency and scale, fiscal-year meaning, expected stages, and missing-value markers against the source inventory.
2. Run `scripts/workbook_inventory.py` for `.xlsx` or `.xlsm`. For ODS, retain the original cached values and record any XLSX conversion as a derived working file.
3. Inspect every visible, hidden, and very-hidden sheet. Assign each sheet a role: raw, formula output, lookup, supplemental, pivot, or presentation-only.
4. Configure [assets/workbook-duplicate-config.example.json](assets/workbook-duplicate-config.example.json) and run `scripts/check_workbook_duplicates.py`.
5. Account for every sheet. A non-ingested exclusion needs an owner, timestamp, reason, and supporting evidence.
6. Record named ranges, external links, schema changes, formula counts, overrides, volatile functions, and formula errors.

Resolve source duplicates before studying classification overlap. An exact repeated row, a repeated business key, and two rules selecting the same row need different fixes.

Finish this source triage before creating production country modules. When duplicate identity, source classification, cached formula evidence, or published totals need an owner decision, keep source-specific diagnostic code under the onboarding workspace and hand off the blocker. Move reusable logic into the country repository only after the affected source contract is settled.

## Convert workbook logic into reviewable rules

Create one structured record for each formula shape, stage, classification code, and year range. Include the raw sheet, measure, formula cell, label, exact formula, criteria branches, and parser status.

- Preserve every additive `SUMIFS` branch; treat the criteria inside a branch as AND conditions and the branches as OR conditions.
- Keep localized strings exactly as the source uses them.
- Separate economic and functional classification dictionaries.
- Mark totals, cross-tabs, and presentation rollups so they cannot become competing line owners.
- Record direct numbers, cell arithmetic, array constants, broken names, wrong-year references, external workbooks, and hidden-sheet supplements.
- Label a formula `unsupported` when the parser cannot reproduce it. A partial parser is useful evidence, not complete coverage.

Run `$mega-boost-overcounting` after the rules and code dictionary are complete enough to define expected stage and code coverage. Resolve confirmed same-depth conflicts in an ownership ledger before writing precedence into ETL.

## Define foreign funding from source fields

Write the predicate before comparing it with the pipeline flag. Use [assets/foreign-funding-predicate.example.json](assets/foreign-funding-predicate.example.json), then run:

```bash
python scripts/check_foreign_funding.py \
  --data <row-level-audit.csv> \
  --flag-column is_foreign \
  --predicate-config <foreign-funding-predicate.json> \
  --require-independent-predicate \
  --id-column <stable-source-row-id> \
  --year-column <year> \
  --measure <approved> --measure <executed> \
  --report <foreign-funding-report.json>
```

Include every raw field used by the predicate in the audit export. The report should show unique source IDs, the observed boolean/null domain, row-level mismatches, and yearly domestic/foreign row and amount conservation. An all-domestic result is acceptable when the independent predicate supports it; it is not a reason to skip this gate.

## Build the country tables

Follow current repository conventions rather than copying an old country folder blindly.

1. Extract each required raw sheet to a stable machine-readable input. Preserve source row identity and predicate text.
2. Build bronze with explicit schema expectations and a documented source-to-bronze column map.
3. Keep one silver row per eligible source row. Assign at most one economic owner and one functional owner through separate cascades; retain unmatched rows with null ownership.
4. Apply specific subcategories before broader categories. Use workbook order only as a reviewed tiebreaker.
5. Keep `admin*` spender hierarchy separate from `geo*` allocation geography. Route the geographic decision through `$mega-subnational-onboarding`.
6. Produce the current gold contract with explicit numeric and boolean casts.
7. Add expectations for years, stages, required fields, source-row uniqueness, classification coverage, `is_foreign`, and measure conservation.
8. Run local syntax and deterministic checks before using Databricks. Keep audit utilities outside the DLT graph.

## Reconcile before registering the country

Compare source, workbook outputs, and pipeline at total, economic, functional, subnational, and funding-source grain for each stage and year. Start at raw-to-bronze and stop at the first boundary where a difference appears.

Classify each result as a match, numeric discrepancy, missing reference, missing pipeline value, unsupported reference, or named exclusion. Keep a resolution ledger with amount, cause, owner, and disposition. Review both percentage and absolute impact; a small percentage can still be material.

If a workbook formula needs correction, obtain explicit authorization and follow the formula-rewrite protocol. Patch a new copy, verify the exact cells and OOXML archive members, recalculate in a spreadsheet engine when available, and rerun the affected checks.

## Integrate after the country tables pass

- Register the ISO3 code in the current CCI extraction, cross-country aggregate, and job or pipeline definitions.
- Include the country in applicable schema, discrepancy, central-scope, subnational, and foreign-funding checks.
- Run staging and inspect the country table, aggregate table, and quality outputs—not just the pipeline status.
- Return the final refs, input and output counts, stage/year totals, reconciliation reports, run IDs, and unresolved decisions to `$mega-country-onboarding`.

## Exit criteria

Finish this skill when:

- every workbook sheet has been inspected or narrowly excluded;
- duplicate names, headers, rows, and keys are resolved or reviewed;
- published formulas are matched or explicitly unsupported;
- classification ownership and `is_foreign` checks pass;
- bronze, silver, and gold conserve named measures after documented exclusions;
- expected stages and years are present and the gold schema matches the aggregate contract;
- discrepancies are within the approved threshold or individually accepted;
- staging tables and relevant quality checks pass;
- original and corrected workbook provenance is complete.
