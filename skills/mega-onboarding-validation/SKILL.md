---
name: mega-onboarding-validation
description: Validate and release a MEGA country across source files, mega-boost, mega-indicators, Databricks pipelines, cross-country aggregates, and rpf-country-dash. Use when checking onboarding completeness; reconciling source, workbook, country-gold, and aggregate values; validating schemas, row counts, geography, maps, narratives, and no-data behavior; collecting staging or production evidence; or preparing the final handoff.
---

# MEGA Onboarding Validation

Walk the data forward from the immutable source to the dashboard. A successful job is one piece of evidence; it does not replace checking the rows and values produced by that job.

## Load the release context

Read [references/release-gates.md](references/release-gates.md), [references/databricks-validation.md](references/databricks-validation.md), and [references/dashboard-validation.md](references/dashboard-validation.md). Load the onboarding manifest, source inventory, specialist reports, and exact repository refs being tested.

## Validate the boundaries in order

### 1. Source and code

- Verify source-inventory and workbook hashes.
- Run the workbook inventory, duplicate audit, parser coverage, overlap audit, foreign-funding check, admin coverage, and formula-patch verification where applicable.
- Run repository syntax, formatting, unit, and configuration or bundle checks.
- Search changed scope for stale country codes, broad exclusions, conflict markers, absolute developer paths, and credentials.
- Confirm final gold field types and semantics against the current aggregate schema.

### 2. Country tables

- Explain bronze, silver, and gold row counts and every intended reduction.
- Check expected stages, years, required fields, nulls, duplicates, and classification coverage.
- Reconcile raw-to-bronze and eligible bronze-to-silver measures after named exclusions.
- Reconcile workbook or CCI values to country gold by total, economic, functional, subnational, and funding-source grain.
- Compare `is_foreign` with the independent source predicate at stable row grain and conserve domestic/foreign counts and amounts by year.

Use `scripts/reconcile_csv.py` for exported comparisons when direct SQL is unavailable. Duplicate or null comparison keys and invalid or null measures are input-grain defects, even when aggregation happens to produce the same total. Keep missing reference and pipeline rows distinct from numeric zero.

### 3. Cross-country and indicators

- Confirm that the country appears once in each required registry and aggregate union.
- Compare country gold with the cross-country table at the same declared grain.
- Check aggregate schema, quality tables, CPI and population joins, per-capita values, and central-scope behavior.
- Validate country metadata, boundaries, population, optional outcomes, geometry, and accepted no-data units.
- Require zero unexpected unmatched region names.

### 4. Dashboard

- Run the full unit suite.
- Verify selector, years, currency, totals, dimensions, maps, narratives, source metadata, translations, and no-data messages.
- Compare dashboard query output with the aggregate rather than checking only rendered text.
- Exercise every map consumer that uses regional names.
- Refresh caches through the authorized application mechanism and confirm the new data is returned.

### 5. Staging and production

Run the country extraction and transform before the aggregate in staging. Record job or pipeline ID, run/update ID, code ref, timestamps, terminal state, table counts, and validation queries. Investigate skipped or missing quality nodes as well as failures.

Start production only with explicit authority and complete staging evidence. Repeat material table and dashboard checks against production; staging results do not prove the production snapshot.

## Use precise gate states

- `passed`: current evidence meets the check.
- `blocked`: a named external dependency or decision prevents the check.
- `in_progress`: validation remains.
- `not_applicable`: only an optional, non-standard check with a recorded reason.

All standard release gates must finish as `passed`.

## Assemble the release evidence

Keep:

- baseline and final refs plus changed-file scope;
- source inventory, workbook hashes, and correction manifest;
- counts, schemas, years, nulls, duplicates, and classification coverage;
- duplicate, parser, overcounting, foreign-funding, discrepancy, and admin reports;
- boundary count, geometry validity, mappings, and no-data units;
- local tests, CI, Databricks staging and production runs;
- dashboard data-backed checks;
- accepted risks and their owners.

Run the orchestrator's manifest checker with `--ready`. Return a concise report by repository with data coverage, discrepancies, geography, run evidence, dashboard evidence, and remaining actions. Finish only when that checker passes and every release-blocking risk is resolved or formally accepted.
