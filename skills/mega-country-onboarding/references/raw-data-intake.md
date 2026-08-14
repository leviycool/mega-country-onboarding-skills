# Raw-data intake contract

The intake should answer three questions before implementation starts: what is authoritative, what will be published, and which source limitations must remain visible.

## Separate the source layers

Record each file once in the source inventory:

| Layer | Typical contents | How to treat it |
|---|---|---|
| Primary source | official workbook or transaction-level export | authoritative input for published amounts |
| Supporting source | codebook, label dictionary, methodology note | evidence for interpretation and mappings |
| Derived working file | converted XLSX, normalized CSV, extracted sheet | reproducible intermediate with `derived_from` lineage |
| Geographic source | boundary, population, poverty, HDI | evaluated through the subnational contract |

A converted XLSX is not a new authority when it only exposes formulas from an ODS file. Keep the original file and record the conversion as derived.

## Build the source inventory

For a new country, run `scripts/start_country.py` first. It creates a validated one-workbook inventory and manifest without overwriting prior work. Use [../assets/source-inventory.example.json](../assets/source-inventory.example.json) as the field-level example when adding the remaining sources:

- country name and ISO codes;
- stages and expected years;
- currency, amount unit, and fiscal-year convention;
- planned published products;
- one stable ID, owner, role, authority level, format, local snapshot, and SHA-256 for every source;
- lineage for every converted or normalized file;
- data classification without recording credentials or access tokens;
- known exclusions, missing files, and uncertain interpretations.

Rerun after each inventory change:

```bash
python scripts/check_source_inventory.py \
  --inventory <source-inventory.json> \
  --output <reports/source-intake.json>
```

The intake report must pass before the manifest's `intake` gate can pass.

## Set the initial scope

Use the source evidence to define the first delivery contract:

- `approved`, `revised`, and/or `executed` stages;
- expected year range and known gaps;
- BOOST country gold, cross-country aggregate, dashboard, and optional indicator products;
- whether subnational evidence is absent, a candidate, or already known to be central-only.

`subnational_review: pending` is acceptable at intake. Resolve it through `mega-subnational-onboarding` before integration.

## Stop intake when

- two files both appear authoritative and no owner has selected one;
- the local snapshot or hash cannot be established;
- units, currency, fiscal-year meaning, or stage labels are ambiguous enough to change totals;
- a required source is missing or access is not authorized;
- source restrictions prevent the intended publication.

Record the blocker and owner in the manifest. Continue with independent reconnaissance only when it cannot bake the unresolved assumption into code.

## Keep a small working record

Use this layout unless a repository already defines one:

```text
onboarding/<iso3-lower>/
  onboarding-manifest.json
  source-inventory.json
  reports/
  decisions/
```

Do not copy restricted raw data into Git. The inventory may point to an approved local or volume snapshot; commit only safe metadata and reports.
