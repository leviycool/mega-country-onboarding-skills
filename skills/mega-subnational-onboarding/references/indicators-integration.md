# `mega-indicators` and dashboard integration

Verify the live architecture before editing; paths and bundle conventions can change.

## Population pipeline

Create or adapt an ISO3-specific extract/transform under `population/<ISO3>/`. Include:

- source URL or volume path and source name;
- HTTP/content validation for downloads;
- raw-to-clean naming rules;
- explicit expected years and unit counts;
- published-total or cross-source checks when available;
- unique region-year and non-null population assertions;
- stable silver table name;
- registration in the aggregate country list and current job dependencies.

Avoid downloading the same large shared source independently for each country when the repository provides a shared bronze/cache pattern.

## Administrative boundaries

Update `geo/admin_boundaries_dlt.py` or the current equivalent only after selecting a contract. Use a reviewed crosswalk and assert that all required source polygons participate. Validate output geometry after any union.

## Other indicators

Review subnational poverty, HDI, health, and education sources independently. They may have sparse years or incompatible regions. Do not make availability of optional outcomes a prerequisite for publishing spending unless the product explicitly requires it.

## Country metadata

Add country zoom or map metadata from actual rendered behavior, not by copying a nearby country. Verify country/currency metadata and any source registry entries.

## Dashboard

Check every map path that consumes region names: spending, per-capita, poverty, HDI/outcomes, and any cached/precomputed datasets. Centralize display harmonization when possible and add tests for mappings, no-data polygons, and unmatched names.

Run the full dashboard unit test suite and, when credentials are available, a data-backed smoke test for the selected country and years.
