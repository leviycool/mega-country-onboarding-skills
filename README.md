# MEGA Country Onboarding Skills

An evidence-gated Codex skill suite for taking a new country from raw fiscal data to validated MEGA tables and dashboard release.

The suite is designed for work that spans `mega-boost`, `mega-indicators`, and `rpf-country-dash`. It treats onboarding as one traceable delivery rather than a collection of repository edits.

## What it covers

```mermaid
flowchart LR
    A["Raw source package"] --> B["Workbook audit"]
    B --> C["Duplicates, formulas, overcounting, is_foreign"]
    B --> D["Subnational decision and admin contract"]
    C --> E["BOOST bronze, silver, and gold"]
    D --> F["Boundaries, population, and indicators"]
    E --> G["Cross-country reconciliation"]
    F --> G
    G --> H["Dashboard and staging"]
    H --> I["Authorized production and handoff"]
```

The release gates cover:

- immutable source inventory, lineage, hashes, years, stages, units, and owners;
- Excel sheet, header, exact-row, and business-key duplicates;
- formula coverage, hardcoded overrides, safe formula rewrites, and workbook discrepancies;
- same-depth classification overlap and within-formula double counting;
- independently derived `is_foreign` flags and yearly amount conservation;
- central-only versus subnational scope and administrative granularity;
- boundary, population, indicator, aggregate, dashboard, staging, and production validation;
- an evidence-backed manifest that another developer can resume without relying on chat history.

## Skills

| Skill | Responsibility |
|---|---|
| `mega-country-onboarding` | Orchestrate the full workflow and release manifest |
| `mega-boost-onboarding` | Audit the workbook and build the country BOOST pipeline |
| `mega-boost-overcounting` | Detect overlaps and document classification ownership |
| `mega-subnational-onboarding` | Decide and validate geography, boundaries, population, and indicators |
| `mega-onboarding-validation` | Reconcile the connected system and collect release evidence |

## Install

Copy the skill directories into your Codex skills directory:

```bash
cp -R skills/* ~/.codex/skills/
```

For repository-local use, keep `skills/` in the workspace and point Codex to the orchestrator:

```text
Use $mega-country-onboarding to onboard <country> from <raw package path>.
```

Start with `skills/mega-country-onboarding/SKILL.md`. The orchestrator routes the specialist skills and creates a schema-v4 onboarding manifest.

## Local requirements

The deterministic checks use Python, pandas, openpyxl, and Shapely. Install the development environment with:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Run the repository checks:

```bash
ruff format --check skills scripts
ruff check skills scripts
python scripts/validate_repository.py
python -B skills/mega-country-onboarding/scripts/run_suite_regression_tests.py
```

## Safety boundaries

- Keep authoritative workbooks and raw country data outside Git.
- Store only safe metadata, configurations, and reports in an onboarding worktree.
- Treat unsupported checks and missing coverage as unresolved rather than passing or zero.
- Require explicit authority before rewriting a source workbook or running production.
- Do not store Databricks tokens, private URLs, or credentials in manifests and logs.

This repository contains workflow automation only. It does not include country source data, production credentials, or deployment authority.

## License

[MIT](LICENSE)
