# Release gates

## Source gate

- source inventory passes with a verified local snapshot and hash for every listed input;
- authoritative and derived files are clearly separated and lineage is complete;
- country, stages, years, currency, amount unit, fiscal-year convention, and planned products agree with the implementation;
- missing or restricted required sources are resolved or recorded as blockers;
- the workbook in the manifest is the same workbook listed in the source inventory.

## Workbook gate

- source hash and owner recorded;
- raw and formula sheets inventoried, including hidden sheets;
- normalized sheet names and headers are collision-free;
- exact duplicate rows and configured business-key duplicates are absent or narrowly dispositioned;
- hardcoded overrides and unsupported formulas reported;
- parser-to-cached-value checks complete;
- authorized formula rewrites verified at cell and archive-member level.

## BOOST gate

- extraction and DLT code use current conventions;
- bronze/silver/gold counts explained;
- expected years and stages present;
- required fields, numeric types, and booleans valid;
- `is_foreign` source predicate and null policy documented;
- independently derived and output foreign flags have zero unexplained row-level mismatches;
- domestic plus foreign row counts and amounts conserve yearly totals;
- one economic and one functional owner per eligible line;
- null owner coverage measured;
- source exclusions named;
- total/dimension discrepancies within threshold or accepted;
- reconciliation inputs are unique at their declared comparison grain, or each intentional aggregation has a reviewed reason;
- country included in applicable CCI and aggregate checks.

## Subnational gate

- required/not-required decision recorded;
- target level, vintage, and unit list explicit;
- boundaries unique and valid;
- population unit-year coverage valid;
- exact mappings complete;
- approximations approved and caveated;
- zero unexpected unmatched source names;
- missing target values retained as no-data.

## Integration gate

- country code registered once in every required list/job/pipeline;
- job dependencies enforce extract before transform before aggregate;
- aggregate schema union succeeds;
- per-capita and other indicator joins do not drop country-years silently;
- staging tables and quality nodes contain the country.

## Dashboard gate

- full unit suite passes;
- country and years are selectable;
- totals and dimensions match the aggregate;
- every relevant map uses the same target geography;
- no-data is visible and not zero-filled;
- map center/zoom and geometry render correctly;
- narratives, source metadata, and all supported languages render without errors.

## Release gate

- staging run terminal state is successful;
- current evidence is tied to exact refs/SHAs;
- all release-blocking risks resolved or accepted;
- production authority obtained;
- production results rechecked;
- manifest and handoff are complete.
