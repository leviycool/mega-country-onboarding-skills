# Administrative granularity decision guide

## Distinguish the axes

- `admin0`: central versus regional spending authority.
- `admin1`: first-level spender or central scope under the MEGA contract.
- `admin2`: ministry/agency for central spending or lower-level unit for regional spending.
- `geo0`: central versus regional geographic allocation.
- `geo1`: first-level geographic allocation used by map and per-capita joins.

Do not copy a geographic name into an administrative field without verifying the workbook semantics.

## Build the source matrix

For each source, record:

| Source | Original level | Vintage | Units | Years | Required? | Proposed transform | Loss |
|---|---|---|---:|---|---|---|---|
| BOOST allocation | workbook-defined | source years | count | range | yes | label map or aggregate | describe |
| Boundaries | ADM1/ADM2 | date | count | n/a | yes for maps | target | describe |
| Population | statistical level | source years | count | range | yes for per-capita | aggregate | describe |
| Poverty | survey regions | survey year | count | sparse | optional | exact only by default | describe |
| HDI/outcomes | provider regions | years | count | range | optional | exact only by default | describe |

Choose the target after completing the matrix.

## Selection rules

1. Use the dashboard's real boundary table as the map-side constraint.
2. Select the smallest unit that every required source can map to exactly.
3. Prefer aggregation of finer source units to disaggregation of coarse values.
4. Require a total, one-to-one source-unit assignment for aggregation.
5. Keep a region with missing values as a valid no-data polygon.
6. Version a crosswalk when the source geography changes over time; do not apply a current map backward without evidence.
7. Keep disputed or uncovered areas explicit.

## Decision categories

- `exact_label`: spelling-only harmonization.
- `exact_id`: stable identifier join.
- `exact_aggregate`: complete union of finer units into a target.
- `boundary_vintage_crosswalk`: reviewed mapping across boundary changes.
- `approximation`: non-equivalent areas; requires explicit approval and visible caveat.
- `no_data`: retain target geometry without a value.
- `excluded`: source area is out of scope with a documented reason.

The default for a non-equivalent source is `no_data`, not `approximation`.

## Required checks

- target boundary count and uniqueness;
- non-empty and valid geometry;
- source and mapped distinct-name counts;
- unmatched source labels;
- target units with no source value;
- reviewed reason, owner, evidence, and timestamp for every accepted no-data target;
- source-to-target many-to-one collisions and their aggregation rule;
- duplicate target-year records;
- full mapping coverage for required inputs;
- year coverage and population positivity;
- totals before and after aggregation.

Do not validate an empty dataset list. When subnational data are required, the contract must enumerate the mandatory dataset roles and the auditor must observe each one. When subnational data are not required, use the manifest decision gate instead of fabricating an empty admin contract.
