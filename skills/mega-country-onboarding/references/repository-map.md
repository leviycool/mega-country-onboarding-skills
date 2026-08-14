# Repository map and stable contracts

Verify all paths against the current checkout before editing. These are routing hints, not permission to assume a stale implementation.

## `mega-boost`

Owns country BOOST extraction, bronze/silver/gold transformation, CCI quality ingestion, cross-country aggregation, and discrepancy checks.

Inspect first:

- `README.md`
- existing country folders with similar workbook structure
- `cross_country_aggregate_dlt.py`
- `quality/extract_cci_approved_executed.py`
- `quality/` discrepancy and availability logic
- the current bundle/job configuration

Stable gold concepts include country, year, `admin0/admin1/admin2`, `geo0/geo1`, `func/func_sub`, `econ/econ_sub`, funding source, and approved/revised/executed measures. Read the current schema instead of copying this list blindly.

## `mega-indicators`

Owns country metadata, administrative boundaries, subnational population, and other outcome indicators used by the dashboard and BOOST per-capita aggregates.

Inspect first:

- `country.py`
- `geo/admin_boundaries_dlt.py`
- `population/subnational_population_official_dlt.py`
- representative `population/<ISO3>/` pipelines
- subnational poverty and human-development transforms
- `resources/` job and pipeline definitions

Require unique `(country_name, adm1_name, year)` rows, explicit source provenance, expected unit/year counts, and no silent loss during aggregation.

## `rpf-country-dash`

Owns queries, server-side data mapping, map rendering, narratives, translations, and application tests.

Inspect first:

- `queries.py`
- `data_mapping.py`
- `utils.py`
- map components and home page
- translation files
- unit tests and any current source-metadata registry

Validate country presence, year range, no-data behavior, boundary validity, name matches, map center/zoom, narratives, and all supported languages.

## Cross-repository join contract

Treat the following relationship as a hard contract:

`BOOST geo1` ↔ `indicator adm1_name` ↔ `boundary admin1_region` ↔ dashboard region key.

Normalize spelling only through an explicit mapping. Preserve a no-data boundary when a source lacks it. Aggregate finer data only with a complete, reviewed crosswalk. Never disaggregate or allocate coarse values to finer polygons without an approved method.

## Integration order

Use the dependency order below unless the current repositories define a stricter one:

1. finish the country extraction and country-level BOOST tables;
2. finish required boundaries, population, and other indicator tables;
3. register the country in BOOST and indicator aggregate jobs;
4. validate cross-country and per-capita outputs;
5. add or update dashboard metadata, mappings, narratives, and translations;
6. run staging end to end before production.

Preparing code in parallel is fine. Publishing an aggregate or dashboard entry before its upstream country and indicator tables pass is not.
