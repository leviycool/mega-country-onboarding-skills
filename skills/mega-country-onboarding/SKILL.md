---
name: mega-country-onboarding
description: Coordinate a new country onboarding across mega-boost, mega-indicators, and rpf-country-dash from raw-source intake through production validation. Use when a developer must start, resume, audit, or hand off a MEGA country; decide which repository work is needed; track an evidence-backed manifest; route workbook, overcounting, foreign-funding, subnational, discrepancy, dashboard, and release work; or decide whether the country is ready.
---

# MEGA Country Onboarding

Run the onboarding as one delivery, even though the work spans several repositories. Keep the country facts, decisions, evidence, and next action in the manifest so another developer can resume without reconstructing the history from chat.

## Set up the working record

1. Read [references/workflow.md](references/workflow.md), [references/raw-data-intake.md](references/raw-data-intake.md), [references/repository-map.md](references/repository-map.md), and [references/evidence-contract.md](references/evidence-contract.md).
2. Locate `mega-boost`, `mega-indicators`, and `rpf-country-dash`. Read their current instructions and inspect their status before editing.
3. Verify the baseline branch or ref in each repository. Similar countries are useful examples only after the current source structure is understood.
4. For a new onboarding, run `scripts/start_country.py` to create the source inventory, intake report, and schema-v4 manifest in one validated step. The script must start from clean repository baselines and refuses to replace an existing onboarding record.
5. Add original raw files, dictionaries, and any geographic or indicator sources already in scope to the generated source inventory, then rerun `scripts/check_source_inventory.py` after every inventory change.
6. For an existing onboarding, resume its manifest rather than bootstrapping another workspace.
7. Capture workbook and source hashes, repository SHAs, existing country tables, pipeline registrations, and dashboard state before changing anything.

Run a fast source triage before adding country code to a repository: duplicate row identity, formula/cached-value coverage, foreign-funding semantics, published-total reconciliation, and the subnational decision. If one of these changes source identity or business meaning, keep diagnostic extracts and helpers in the onboarding workspace and stop production implementation until the owner resolves it.

Start a country with:

```bash
python scripts/start_country.py \
  --country <name> --iso2 <ISO2> --iso3 <ISO3> \
  --workbook <local-workbook-snapshot> --source-owner <owner> \
  --year <year> --stage <approved|revised|executed> \
  --currency <currency> --amount-unit <unit> \
  --fiscal-year-convention <convention> \
  --repo-root <parent-of-the-three-repositories> \
  --workspace <onboarding-workspace>
```

Use `scripts/check_manifest.py init` only when reconstructing a manifest around an already-reviewed inventory. After every work session, run `scripts/check_manifest.py next --manifest <onboarding-manifest.json>` and leave its first incomplete gate with an executable `next_action`.

Ask for input only when the answer cannot be established safely from source or code: competing authoritative files, ambiguous fiscal or geographic meaning, category ownership, permission to edit the workbook, approval of an approximation, or authority to run production.

## Move through the gates

Use this order, but return to an earlier gate when a later check exposes a bad assumption.

| Gate | Work | Evidence to keep | Stop when |
|---|---|---|---|
| Intake | Lock source snapshots, lineage, scope, years, units, and owners | source inventory and intake report | authority, access, units, or scope is unresolved |
| Workbook | Inventory every sheet and audit duplicate names, headers, rows, and business keys | workbook inventory, duplicate contract, duplicate report | an ingested sheet is unaccounted for or a duplicate lacks disposition |
| Classification | Extract formulas and overrides; test overcounting and foreign-funding logic | rule table, parser coverage, overlap report, ownership ledger, foreign report | a published formula is unsupported or ownership is undecided |
| BOOST ETL | Build extraction plus bronze, silver, and gold; preserve row identity and unmatched coverage | code refs, schema checks, row and amount conservation | a layer drops or duplicates unexplained records |
| Subnational | Decide central-only versus subnational; align geography and indicators when needed | decision report or admin contract and coverage report | target level, mapping, boundary, or population coverage is unresolved |
| Integration | Register the country in current jobs, aggregate lists, quality checks, and dashboard metadata | changed refs, dependency validation, table snapshots | upstream country tables have not passed |
| Release | Reconcile each boundary, test the dashboard, run staging, then authorized production | reconciliation reports, run IDs, dashboard checks, final refs | any standard gate lacks current passing evidence |

Invoke the specialist skills at their owning gates:

- `$mega-boost-onboarding` for workbook analysis, formulas, `is_foreign`, country ETL, and discrepancy work;
- `$mega-boost-overcounting` once structured rules and the code dictionary exist;
- `$mega-subnational-onboarding` during intake, not after the BOOST pipeline is finished;
- `$mega-onboarding-validation` for cross-repository checks, staging, dashboard, and release.

## Keep the main contracts intact

- Preserve the original source snapshot. Put an authorized workbook correction in a new file with its own hash and patch report.
- Resolve source-row duplicates before rule overlaps; the two checks answer different questions.
- Assign at most one economic owner and one functional owner to an eligible line. Parent totals belong in downstream aggregation.
- Derive `is_foreign` from a reviewed raw-field predicate, then compare it with pipeline output at stable row grain.
- Keep `admin*` spender fields separate from `geo*` allocation fields.
- Retain unmatched classifications, missing regions, and unsupported reference values as visible coverage states. A no-data release exception needs reviewed owner evidence; the developer cannot approve it merely by observing the gap.
- Add the country to aggregates only after its country tables and required indicator inputs pass.
- Keep credentials and restricted source data out of committed reports.

## Update the manifest as work moves

For each gate, maintain:

- `status`: `not_started`, `in_progress`, `passed`, `blocked`, or `not_applicable`;
- `evidence`: file, command, run, URL, or decision objects;
- `decisions`: choice, owner, date, and rejected alternatives;
- `risks`: impact, owner, disposition, and release-blocking status;
- `next_action`: one concrete step that another developer can execute.

Run the structural check while working:

```bash
python scripts/check_manifest.py check --manifest <onboarding-manifest.json>
```

Show the next incomplete standard gate:

```bash
python scripts/check_manifest.py next --manifest <onboarding-manifest.json>
```

Run it with `--ready` only for release. Every standard gate must be `passed`; a central-only country passes subnational with a reviewed decision report rather than `not_applicable`.

## Hand off the country

Provide the manifest and a short summary containing:

1. outcome and final ref for each repository;
2. source versions, years, stages, rows, units, and geographic coverage;
3. duplicate, parser, overcounting, foreign-funding, discrepancy, and subnational results;
4. staging and production run evidence;
5. accepted limitations and open decisions;
6. the exact next action, if work remains.

Call the onboarding complete only after `$mega-onboarding-validation` passes and the manifest checker succeeds with `--ready`. Run `scripts/run_suite_regression_tests.py` before publishing changes to this skill suite.
