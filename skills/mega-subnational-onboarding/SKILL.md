---
name: mega-subnational-onboarding
description: Determine whether a MEGA country needs subnational data, choose the supported administrative granularity, and align boundaries, population, BOOST geography, poverty, human-development, and dashboard joins. Use when a workbook contains regional or local fields; admin0, admin1, admin2, geo0, or geo1 semantics are unclear; sources use different boundary vintages or levels; maps have unmatched names or missing regions; or subnational indicators must be added to mega-indicators and the country dashboard.
---

# MEGA Subnational Onboarding

Make the geography decision early. The target level should be the finest stable geography that every required source can support without inventing allocation.

## Decide whether this branch is needed

Read [references/admin-granularity.md](references/admin-granularity.md) and [references/indicators-integration.md](references/indicators-integration.md).

Inspect the workbook and current pipeline for:

- candidate geographic columns listed in `auxiliary_data/sub_national_info_sheet_column_BOOST.csv`;
- distinct non-central values in region fields;
- formulas or tags for decentralized spending;
- evidence that `admin*` means spending authority, `geo*` means allocation geography, or both;
- dashboard features that need regional boundaries, population, per-capita values, poverty, or other outcomes;
- central ministry names that look geographic but do not represent regional allocation.

Choose one of two outputs:

- **Central-only:** create a reviewed `subnational_decision` report with the inspected fields, value evidence, affected products, owner, and timestamp.
- **Subnational required:** create an admin contract from [assets/admin-contract.example.json](assets/admin-contract.example.json) and continue with source alignment.

Absence of a familiar column name is not enough to call a country central-only.

## Choose a target geography

Build a source matrix before selecting the level. Record each source's original level, vintage, unit count, years, identifiers, names, required status, and possible transformation.

1. Inspect the boundary table actually used by the dashboard.
2. Select the smallest unit that all required sources can map to exactly.
3. Prefer stable IDs; otherwise create a source-specific label mapping.
4. Aggregate finer units only through a complete reviewed crosswalk.
5. Version the crosswalk when boundaries change over time.
6. Mark target units absent from a source as no-data.
7. Escalate non-equivalent mappings and approximations for explicit approval.

Keep these axes separate:

- `admin0/admin1/admin2`: who spent the funds;
- `geo0/geo1`: where the funds were allocated.

Do not split a coarse value across smaller polygons or relabel a combined area as one component to make the map look complete.

## Align the required datasets

### Boundaries

Use one selected level and vintage. Check unique target IDs/names, expected unit count, non-empty geometry, geometry validity, and documented unions or exclusions.

### Population

Prefer an official national source when available. Keep provenance and exact year coverage; require unique unit-year rows, numeric nonnegative values, expected counts, and published-total reconciliation where possible.

### Poverty and other outcomes

Join only semantically equivalent regions and retain survey years. Sparse or incompatible optional outcomes should remain no-data unless the product owner approves an approximation.

### BOOST and dashboard

Apply the reviewed mapping to BOOST geography, boundaries, population, and every map consumer. Define the per-capita year policy and keep display-name harmonization at the presentation boundary when possible.

## Run the coverage audit

Populate the admin contract and run:

```bash
python scripts/audit_admin_coverage.py \
  --contract <admin-contract.json> \
  --output <admin-coverage-report.json>
```

When subnational data are required, set `subnational_required=true`, list every required dataset name, and include BOOST geography plus population for subnational or per-capita outputs. Record each accepted no-data target as a reviewed object with its reason, owner, evidence, and timestamp. Observing that a source lacks a region is evidence of the gap, not authority to accept it for release.

Use an environment with pandas and Shapely for a release audit. Missing geometry validation, an empty dataset list, a missing required dataset, duplicate unit-years, invalid geometry, or unexplained unmatched names blocks this gate.

## Exit criteria

Return to `$mega-country-onboarding` with either a passing central-only decision or a passing admin coverage report. For a subnational country, also provide the target level and vintage, unit list, source provenance, mappings, no-data units, indicator pipeline refs, and remaining geography decisions.
