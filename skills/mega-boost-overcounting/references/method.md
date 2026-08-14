# Overcounting method

## Membership model

Translate each workbook tag into a boolean mask over raw microdata. A `SUMIFS` block ANDs its criteria. Additive `SUMIFS` blocks generally OR their memberships for classification, but their monetary contributions must still be evaluated separately to detect a line counted twice within one formula.

For two peer codes `A` and `B`:

- `mask_A & mask_B` identifies duplicated rows.
- `sum(measure[mask_A & mask_B])` is pairwise duplicated exposure.
- `sum(mask_A & mask_B)` is duplicated line count.

For a dimension with membership count `k_i` on row `i`, net excess is:

`sum(measure_i * max(k_i - 1, 0))`

This prevents triple-membership rows from being misreported by summing pairwise intersections.

## Pairing rules

Compare only codes with the same tag kind and classification depth:

- econ rollup vs econ rollup where both `econ_sub` are null;
- econ subcategory vs econ subcategory where both `econ_sub` are populated;
- func rollup vs func rollup where both `func_sub` are null;
- func subcategory vs func subcategory where both `func_sub` are populated.

Compare subcategories even when parents differ: two subcategory labels are still claims about exclusive ownership. Annotate whether canonical values are equal or different.

Exclude parent-child pairs, economic-vs-functional pairs, and reviewed aggregate-only codes. Route subnational cross-cutting tags to a separate audit group.

## Formula coverage

Support or explicitly report:

- named ranges and direct ranges;
- equality, inequality, comparison, wildcard, and array criteria;
- multiple year-range schemas;
- localized values;
- additive and subtractive cell references;
- hidden-sheet and external references;
- estimates that source another stage;
- residual formulas such as total minus children.

Never infer a pass from cached Excel values alone. Independently evaluate the parsed predicate against raw microdata, compare to the authoritative cached value, and label every cell `MATCH`, `MISMATCH`, or `UNSUPPORTED`.

Treat coverage as a release condition. Configure every expected stage and code. A missing stage, empty selected-rule set, missing expected code, or uncontracted code is a failure even when the reported overlap count is zero.

## Resolution hierarchy

1. Remove totals/meta-rollups from ownership.
2. Consolidate exact duplicate rules.
3. Obtain a reviewed owner for cross-category intersections.
4. Encode precedence or an exclusion predicate.
5. Version the rule by year only when the source taxonomy genuinely changes.
6. Preserve null/unmatched classifications as coverage gaps.

Do not “fix” the result by subtracting a magic amount, excluding an entire country-year, or dropping intersecting source rows.

## Validation layers

1. Parser reproduces workbook formula values.
2. Corrected masks have the intended ownership.
3. Workbook patch contains only intended edits.
4. DLT applies the same ownership to line-level output.
5. Country totals and dimensions reconcile.
6. Cross-country aggregation does not duplicate the country.

Retain before/after reports so reviewers can distinguish a resolved conflict from a detector regression.
