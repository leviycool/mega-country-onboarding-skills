# Manifest evidence contract

Schema version 4 ties release readiness to the complete source package as well as the workbook. Every passed gate needs at least one `file`, `command`, or `run` object; prose alone cannot pass a gate.

## Evidence shapes

File reports must exist when `--ready` runs and their hash must match:

```json
{
  "kind": "file",
  "path": "reports/workbook-duplicates.json",
  "sha256": "<64-hex-digest>",
  "checked_at": "2026-01-01T00:00:00Z"
}
```

The intake, duplicate, overcounting, foreign-funding, subnational, and cross-country gates additionally need a matching JSON report with `passed: true`. Use these `check` values:

| Gate | Accepted `check` value |
|---|---|
| intake | `source_intake` |
| workbook duplicates | `workbook_duplicates` |
| overcounting | `overcounting` |
| foreign funding | `foreign_funding` |
| subnational | `subnational` or `subnational_decision` |
| cross-country | `cross_country` or `reconciliation` |

For a central-only decision, store a reviewed report with `check: "subnational_decision"`, `passed: true`, `required: false`, source evidence, owner, and timestamp.

Commands must record the exact command and successful exit code:

```json
{
  "kind": "command",
  "command": "pytest -q",
  "exit_code": 0,
  "checked_at": "2026-01-01T00:00:00Z"
}
```

Remote runs must be traceable to code and a successful terminal state:

```json
{
  "kind": "run",
  "system": "databricks",
  "run_id": "<run-or-update-id>",
  "ref": "<commit-sha>",
  "status": "succeeded",
  "checked_at": "2026-01-01T00:00:00Z"
}
```

Use `decision` for reviewed human judgment and `url` for stable external evidence. These may supplement but never replace machine evidence for a passed gate.

## Readiness rules

- Require all standard gates to be `passed`; do not use `not_applicable` to bypass a required check.
- Record a central-only geography determination as a passed subnational decision.
- Preserve local immutable snapshots for the source inventory and workbook even when the authority is a URL. Verify their hashes and record final repository refs.
- Give every accepted release-blocking risk an accepter, timestamp, and rationale.
- Keep evidence paths relative to the manifest where practical so another developer can re-run the checker.
