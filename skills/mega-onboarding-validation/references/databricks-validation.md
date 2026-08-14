# Databricks validation

## Preflight

- Verify the active profile, workspace, catalog, schema, repo ref, and compute policy.
- Prefer bundle/job definitions over manual one-off configuration.
- Never print tokens or persist credentials in reports.
- Validate current job and pipeline configuration before starting a run.

## Capture for every run

- object type and name;
- job/pipeline ID and run/update ID;
- Git ref and commit SHA;
- parameters and target catalog/schema;
- compute/cluster identity without secrets;
- creation/start/end timestamps;
- terminal state and failure cause;
- output table counts and validation queries.

## Minimum data queries

Adapt names to the current environment:

```sql
SELECT year, count(*) AS rows,
       sum(approved) AS approved,
       sum(executed) AS executed
FROM <country_gold>
GROUP BY year
ORDER BY year;
```

```sql
SELECT
  count(*) AS rows,
  sum(CASE WHEN func IS NULL THEN 1 ELSE 0 END) AS null_func,
  sum(CASE WHEN econ IS NULL THEN 1 ELSE 0 END) AS null_econ,
  sum(CASE WHEN approved IS NULL THEN 1 ELSE 0 END) AS null_approved,
  sum(CASE WHEN executed IS NULL THEN 1 ELSE 0 END) AS null_executed
FROM <country_gold>;
```

```sql
SELECT country_name, year, count(*) AS rows
FROM <cross_country_gold>
WHERE country_name = '<country>'
GROUP BY country_name, year
ORDER BY year;
```

```sql
SELECT year, is_foreign, count(*) AS rows,
       sum(approved) AS approved,
       sum(revised) AS revised,
       sum(executed) AS executed
FROM <country_gold>
GROUP BY year, is_foreign
ORDER BY year, is_foreign;
```

Also query invalid/null `is_foreign` values and compare the output flag with an independently derived source-rule flag at stable source-row grain. Verify in each year that the domestic and foreign partitions reproduce the all-row counts and amounts; do not coerce null to `false`.

Also query applicable quality tables for total, func, econ, subnational, central-scope, and foreign-funding comparisons.

## Failure handling

Inspect event logs and task outputs. Fix the owning source or code layer; do not bypass a quality node or add a country-year exclusion without a documented source reason and review.

An environment/authentication failure is not a data pass. Record it as blocked and retain the last verified result with its date and SHA.
