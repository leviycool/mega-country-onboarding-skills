# Discrepancy checks

## Comparison matrix

Run each applicable comparison for Approved, Revised, and Executed:

| Dimension | Keys |
|---|---|
| Total | country, year |
| Functional | country, year, func |
| Economic | country, year, econ |
| Subnational | country, year, geo1 or admin1 as defined |
| Funding source | country, year, is_foreign |
| Cross checks | country, year, func, econ where the workbook publishes them |

Compute reference value, pipeline value, absolute difference, and percent difference. Define the percent denominator explicitly and handle zero safely.

## Status taxonomy

Use statuses instead of coercing nulls to zero:

- `MATCH`: within absolute and relative tolerances.
- `DISCREPANCY`: both values exist and differ materially.
- `MISSING_REFERENCE`: pipeline value exists but workbook/CCI value is absent.
- `MISSING_PIPELINE`: reference exists but the pipeline value is absent.
- `BOTH_MISSING`: no numeric comparison is possible; retain as coverage evidence.
- `UNSUPPORTED_REFERENCE`: formula or override cannot be reproduced.
- `EXPECTED_EXCLUSION`: a reviewed, named exclusion applies.

Do not let missing CCI subnational rows appear as zero discrepancies.

## Diagnostic sequence

1. Reconcile raw source sums to bronze.
2. Reconcile eligible bronze rows to silver after named exclusions.
3. Measure null economic and functional ownership.
4. Reconcile silver by workbook tag where possible.
5. Reconcile country gold by canonical dimension.
6. Reconcile the cross-country aggregate.
7. Compare dashboard query outputs to the aggregate.

Stop at the first layer where the difference appears. Do not compensate downstream for an upstream mismatch.

## Mandatory foreign-funding checks

Treat `is_foreign` as a published business dimension, not merely a schema field:

1. Document the raw source fields and exact predicate that imply foreign funding.
2. Express the predicate with the restricted predicate config and let the checker independently derive the expected flag from raw fields. Do not pre-copy an expected column from pipeline output.
3. Reject invalid encodings and apply an explicit null policy; do not coerce unknown to domestic.
4. Require zero unexplained row-level mismatches between expected and output flags.
5. For every year and applicable stage, reconcile domestic plus foreign rows and amounts to the all-row total.
6. Compare the same split in country gold, the cross-country aggregate, and any published workbook/CCI reference.

Do not require both boolean values when source evidence shows a country-year legitimately contains only domestic or only foreign funding. Report the observed domain so a surprising single-value result remains reviewable.

## Acceptance

Use the threshold currently documented by the repository and project owner; the mega-boost onboarding guide historically used 5 percent. Also review absolute differences, row counts, and systematic bias. Require individual disposition for every result outside tolerance and every unsupported formula used by published totals.
