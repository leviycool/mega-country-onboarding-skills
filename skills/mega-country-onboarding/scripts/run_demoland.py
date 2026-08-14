#!/usr/bin/env python3
"""Run a synthetic first-hour MEGA onboarding without live-system access."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from openpyxl import Workbook


SUITE_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR = Path(__file__).resolve().parent
BOOST = SUITE_ROOT / "mega-boost-onboarding" / "scripts"
OVERCOUNTING = SUITE_ROOT / "mega-boost-overcounting" / "scripts"
NOW = "2026-01-01T00:00:00Z"
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def write_csv(path: Path, rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        csv.writer(stream).writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[object]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [str(item) for item in command],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Command failed: {' '.join(map(str, command))}\n{detail}")
    return completed


def require_failure(command: list[object], expected_text: str) -> None:
    completed = subprocess.run(
        [str(item) for item in command],
        text=True,
        capture_output=True,
        check=False,
    )
    detail = completed.stdout + completed.stderr
    if completed.returncode == 0 or expected_text not in detail:
        raise RuntimeError(
            "Expected command to fail safely with "
            f"{expected_text!r}: {' '.join(map(str, command))}"
        )


def make_repository(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "README.md").write_text(f"# Synthetic {path.name}\n", encoding="utf-8")
    run(["git", "init", "--quiet", path])
    run(["git", "-C", path, "add", "README.md"])
    run(
        [
            "git",
            "-C",
            path,
            "-c",
            "user.name=MEGA Demo",
            "-c",
            "user.email=demo@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "Synthetic baseline",
        ]
    )


def make_workbook(path: Path) -> None:
    workbook = Workbook()
    raw = workbook.active
    raw.title = "Raw Data"
    raw.append(["row_id", "year", "funding_code", "approved", "executed", "is_foreign"])
    raw.append(["DL001", 2023, "10", 100, 90, False])
    raw.append(["DL002", 2023, "27 A", 50, 45, True])
    raw.append(["DL003", 2024, "10", 120, 110, False])
    summary = workbook.create_sheet("Published")
    summary.append(["year", "stage", "total"])
    summary.append([2023, "approved", "=SUMIFS('Raw Data'!D:D,'Raw Data'!B:B,A2)"])
    summary.append([2024, "approved", "=SUMIFS('Raw Data'!D:D,'Raw Data'!B:B,A3)"])
    workbook.save(path)
    cache_formula_values(path, {"C2": 150, "C3": 120})


def cache_formula_values(path: Path, values: dict[str, int | float]) -> None:
    worksheet = "xl/worksheets/sheet2.xml"
    replacement = path.with_name(f"{path.stem}.cached{path.suffix}")
    ET.register_namespace("", MAIN)
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(replacement, "w") as output:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == worksheet:
                root = ET.fromstring(payload)
                for cell_ref, value in values.items():
                    cell = root.find(f".//{{{MAIN}}}c[@r='{cell_ref}']")
                    if cell is None or cell.find(f"{{{MAIN}}}f") is None:
                        raise RuntimeError(
                            f"Synthetic formula cell is missing: {cell_ref}"
                        )
                    cached = cell.find(f"{{{MAIN}}}v")
                    if cached is None:
                        cached = ET.SubElement(cell, f"{{{MAIN}}}v")
                    cached.text = str(value)
                payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            output.writestr(info, payload)
    replacement.replace(path)


def update_manifest(workspace: Path, reports: dict[str, Path]) -> dict:
    manifest_path = workspace / "onboarding-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    evidence_gate_map = {
        "workbook_audit": "workbook_inventory",
        "subnational_scope": "subnational_decision",
        "workbook_duplicates": "workbook_duplicates",
        "overcounting": "overcounting",
        "foreign_funding": "foreign_funding",
        "subnational_data": "subnational_decision",
    }
    for gate, report_name in evidence_gate_map.items():
        report = reports[report_name]
        manifest["gates"][gate].update(
            {
                "status": "passed",
                "evidence": [
                    {
                        "kind": "file",
                        "path": str(report),
                        "sha256": sha256(report),
                        "checked_at": NOW,
                    }
                ],
                "next_action": None,
            }
        )
    manifest["subnational"].update(
        {
            "required": False,
            "decision_evidence": [
                "Synthetic workbook has no allocation-geography fields or regional products."
            ],
        }
    )
    manifest["handoff"]["next_action"] = manifest["gates"]["boost_etl"]["next_action"]
    write_json(manifest_path, manifest)
    return manifest


def run_demo(root: Path) -> dict:
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty demo output: {root}")
    root.mkdir(parents=True, exist_ok=True)
    repo_root = root / "repositories"
    for name in ("mega-boost", "mega-indicators", "rpf-country-dash"):
        make_repository(repo_root / name)

    workbook = root / "demoland.xlsx"
    make_workbook(workbook)
    workspace = root / "onboarding" / "dml"
    start_command = [
        sys.executable,
        "-B",
        ORCHESTRATOR / "start_country.py",
        "--country",
        "DemoLand",
        "--iso2",
        "DL",
        "--iso3",
        "DML",
        "--workbook",
        workbook,
        "--source-owner",
        "MEGA demo team",
        "--year",
        "2023",
        "--year",
        "2024",
        "--stage",
        "approved",
        "--stage",
        "executed",
        "--currency",
        "DLC",
        "--amount-unit",
        "units",
        "--fiscal-year-convention",
        "Calendar year",
        "--repo-root",
        repo_root,
        "--workspace",
        workspace,
    ]
    run(start_command)
    require_failure(
        start_command, "Refusing to overwrite an existing onboarding record"
    )

    reports_dir = workspace / "reports"
    decisions_dir = workspace / "decisions"
    reports = {
        "workbook_inventory": reports_dir / "workbook-inventory.json",
        "workbook_duplicates": reports_dir / "workbook-duplicates.json",
        "overcounting": reports_dir / "overcounting.json",
        "foreign_funding": reports_dir / "foreign-funding.json",
        "subnational_decision": reports_dir / "subnational-decision.json",
    }
    run(
        [
            sys.executable,
            "-B",
            BOOST / "workbook_inventory.py",
            workbook,
            "--json",
            reports["workbook_inventory"],
            "--sheet-csv",
            reports_dir / "workbook-sheets.csv",
        ]
    )

    duplicate_config = decisions_dir / "workbook-duplicate-config.json"
    write_json(
        duplicate_config,
        {
            "check_normalized_sheet_names": True,
            "sample_limit": 25,
            "excluded_sheets": [],
            "sheets": [
                {
                    "name": "Raw Data",
                    "role": "raw",
                    "header_row": 1,
                    "check_duplicate_headers": True,
                    "check_exact_rows": True,
                    "key_columns": ["row_id"],
                    "ignore_columns": [],
                    "normalize_key_text": False,
                    "require_complete_key": True,
                    "allowed_duplicate_keys": [],
                },
                {
                    "name": "Published",
                    "role": "formula_output",
                    "header_row": 1,
                    "check_duplicate_headers": True,
                    "check_exact_rows": True,
                    "key_columns": ["year", "stage"],
                    "ignore_columns": [],
                    "normalize_key_text": True,
                    "require_complete_key": True,
                    "allowed_duplicate_keys": [],
                },
            ],
        },
    )
    run(
        [
            sys.executable,
            "-B",
            BOOST / "check_workbook_duplicates.py",
            workbook,
            "--config",
            duplicate_config,
            "--report",
            reports["workbook_duplicates"],
        ]
    )

    audit_csv = workspace / "decisions" / "row-level-audit.csv"
    write_csv(
        audit_csv,
        [
            ["row_id", "year", "funding_code", "approved", "executed", "is_foreign"],
            ["DL001", 2023, "10", 100, 90, "false"],
            ["DL002", 2023, "27 A", 50, 45, "true"],
            ["DL003", 2024, "10", 120, 110, "false"],
        ],
    )
    foreign_predicate = decisions_dir / "foreign-funding-predicate.json"
    write_json(
        foreign_predicate,
        {
            "description": "Synthetic funding codes beginning with 27 are foreign.",
            "branches": [
                {
                    "all": [
                        {
                            "column": "funding_code",
                            "operator": "starts_with",
                            "value": "27 ",
                        }
                    ]
                }
            ],
        },
    )
    run(
        [
            sys.executable,
            "-B",
            BOOST / "check_foreign_funding.py",
            "--data",
            audit_csv,
            "--flag-column",
            "is_foreign",
            "--predicate-config",
            foreign_predicate,
            "--require-independent-predicate",
            "--id-column",
            "row_id",
            "--year-column",
            "year",
            "--measure",
            "approved",
            "--measure",
            "executed",
            "--report",
            reports["foreign_funding"],
        ]
    )

    rules = decisions_dir / "tag-rules.csv"
    dictionary = decisions_dir / "code-dictionary.csv"
    overlap_config = decisions_dir / "overlap-config.json"
    write_csv(
        rules,
        [
            [
                "code",
                "row_type",
                "sheet",
                "measure",
                "criteria_json",
                "sample_formula",
                "formula_cell",
            ],
            [
                "ALL",
                "TAG",
                "Approved",
                "approved",
                json.dumps([{"field": "year", "op": ">=", "value": 2023}]),
                "=SUMIFS(...) ",
                "C2",
            ],
        ],
    )
    write_csv(
        dictionary,
        [
            ["code", "tag_kind", "econ", "econ_sub", "func", "func_sub"],
            ["ALL", "primary", "All spending", "", "", ""],
        ],
    )
    write_json(
        overlap_config,
        {
            "country": "DemoLand",
            "expected_stages": ["Approved"],
            "minimum_rules_per_stage": 1,
            "expected_codes_by_stage": {"Approved": ["ALL"]},
            "ranges": [
                {
                    "name": "all-years",
                    "input": str(audit_csv),
                    "format": "csv",
                    "measures": ["approved"],
                    "measure_dispatch": ["approved"],
                    "field_map": {"year": "year"},
                }
            ],
        },
    )
    run(
        [
            sys.executable,
            "-B",
            OVERCOUNTING / "detect_tag_overlaps.py",
            "--config",
            overlap_config,
            "--tag-rules",
            rules,
            "--code-dictionary",
            dictionary,
            "--output",
            reports["overcounting"],
        ]
    )
    write_json(
        reports["subnational_decision"],
        {
            "check": "subnational_decision",
            "passed": True,
            "country": "DemoLand",
            "required": False,
            "decision": "central_only",
            "owner": "MEGA demo team",
            "checked_at": NOW,
            "evidence": [
                "No allocation-geography fields or subnational products in the synthetic source."
            ],
        },
    )

    manifest = update_manifest(workspace, reports)
    run(
        [
            sys.executable,
            "-B",
            ORCHESTRATOR / "check_manifest.py",
            "check",
            "--manifest",
            workspace / "onboarding-manifest.json",
        ]
    )
    next_result = json.loads(
        run(
            [
                sys.executable,
                "-B",
                ORCHESTRATOR / "check_manifest.py",
                "next",
                "--manifest",
                workspace / "onboarding-manifest.json",
            ]
        ).stdout
    )
    passed_gates = [
        name
        for name, gate in manifest["gates"].items()
        if gate.get("status") == "passed"
    ]
    return {
        "passed": True,
        "scope": "synthetic local preflight; no live ETL, staging, dashboard, or production",
        "workspace": str(workspace),
        "passed_gates": passed_gates,
        "current_gate": next_result["current_gate"],
        "next_action": next_result["next_action"],
        "report_count": len(reports),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Retain demo files here; omit to use an automatically removed temp folder.",
    )
    args = parser.parse_args()
    try:
        if args.output:
            result = run_demo(args.output.resolve())
            result["retained"] = True
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        with tempfile.TemporaryDirectory(prefix="mega-demoland-") as temp:
            result = run_demo(Path(temp))
            result["retained"] = False
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
