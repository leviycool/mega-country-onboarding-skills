#!/usr/bin/env python3
"""Initialize and validate a MEGA country-onboarding manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


STATUSES = {"not_started", "in_progress", "passed", "blocked", "not_applicable"}
CURRENT_SCHEMA_VERSION = 4
EVIDENCE_KINDS = {"command", "decision", "file", "run", "url"}
MACHINE_EVIDENCE_KINDS = {"command", "file", "run"}
SUCCESSFUL_RUN_STATES = {"passed", "success", "succeeded"}
REQUIRED_REPORT_CHECKS = {
    "intake": {"source_intake"},
    "workbook_duplicates": {"workbook_duplicates"},
    "overcounting": {"overcounting"},
    "foreign_funding": {"foreign_funding"},
    "subnational": {"subnational", "subnational_decision"},
    "cross_country": {"cross_country", "reconciliation"},
}
REQUIRED_GATES = {
    "intake",
    "workbook_audit",
    "workbook_duplicates",
    "overcounting",
    "foreign_funding",
    "boost_etl",
    "subnational",
    "cross_country",
    "dashboard",
    "staging",
    "production",
}
GATE_ORDER = (
    "intake",
    "workbook_audit",
    "subnational",
    "workbook_duplicates",
    "overcounting",
    "foreign_funding",
    "boost_etl",
    "cross_country",
    "dashboard",
    "staging",
    "production",
)


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def initialize(args: argparse.Namespace) -> int:
    if args.output.exists() and not args.force:
        raise FileExistsError(
            f"Refusing to overwrite {args.output}; pass --force to replace it"
        )
    manifest = deepcopy(load_json(args.template))
    manifest["country"].update(
        {"name": args.country, "iso2": args.iso2.upper(), "iso3": args.iso3.upper()}
    )
    manifest["workspace"].update(
        {
            "root": str(args.workspace.resolve()),
            "manifest_path": str(args.output.resolve()),
        }
    )
    if args.workbook:
        workbook = args.workbook.resolve()
        manifest["source_workbook"]["path_or_url"] = str(workbook)
        manifest["source_workbook"]["local_snapshot"] = str(workbook)
        if workbook.is_file():
            manifest["source_workbook"]["sha256"] = sha256(workbook)
    if args.source_inventory:
        source_inventory = args.source_inventory.resolve()
        manifest["source_package"]["inventory_path"] = str(source_inventory)
        if source_inventory.is_file():
            manifest["source_package"]["inventory_sha256"] = sha256(source_inventory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"created": str(args.output), "country": manifest["country"]}))
    return 0


def nonempty(value: object) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def local_path(value: object, base: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        return None
    path = Path(value)
    return path if path.is_absolute() else base / path


def validate_evidence(
    gate_name: str,
    evidence: object,
    ready: bool,
    base: Path,
    expected_inventory_sha256: str | None = None,
) -> list[str]:
    issues: list[str] = []
    if not isinstance(evidence, list) or not evidence:
        return [f"gates.{gate_name}.evidence must be a non-empty list"]
    machine_evidence = False
    passing_report = False
    for index, item in enumerate(evidence):
        prefix = f"gates.{gate_name}.evidence[{index}]"
        if not isinstance(item, dict):
            issues.append(f"{prefix} must be an object, not free text")
            continue
        kind = item.get("kind")
        if kind not in EVIDENCE_KINDS:
            issues.append(f"{prefix}.kind must be one of {sorted(EVIDENCE_KINDS)}")
            continue
        if not valid_timestamp(item.get("checked_at")):
            issues.append(f"{prefix}.checked_at must be an ISO-8601 timestamp")
        machine_evidence |= kind in MACHINE_EVIDENCE_KINDS
        if kind == "file":
            path = local_path(item.get("path"), base)
            if path is None:
                issues.append(f"{prefix}.path must be a local file path")
                continue
            digest = item.get("sha256")
            if not isinstance(digest, str) or not re.fullmatch(
                r"[0-9a-fA-F]{64}", digest
            ):
                issues.append(f"{prefix}.sha256 must contain 64 hexadecimal characters")
            if ready:
                if not path.is_file():
                    issues.append(f"{prefix}.path does not exist: {path}")
                elif (
                    isinstance(digest, str)
                    and sha256(path).casefold() != digest.casefold()
                ):
                    issues.append(f"{prefix}.sha256 does not match {path}")
                elif path.suffix.casefold() == ".json":
                    try:
                        report = load_json(path)
                    except (json.JSONDecodeError, ValueError) as exc:
                        issues.append(
                            f"{prefix}.path is not a valid JSON report: {exc}"
                        )
                    else:
                        valid_report = report.get("passed") is True and report.get(
                            "check"
                        ) in REQUIRED_REPORT_CHECKS.get(gate_name, set())
                        if (
                            valid_report
                            and gate_name == "intake"
                            and report.get("inventory_sha256")
                            != expected_inventory_sha256
                        ):
                            issues.append(
                                f"{prefix}.path was produced from a different source inventory"
                            )
                            valid_report = False
                        passing_report |= valid_report
        elif kind == "command":
            if not nonempty(item.get("command")):
                issues.append(f"{prefix}.command is required")
            if item.get("exit_code") != 0:
                issues.append(f"{prefix}.exit_code must be 0")
        elif kind == "run":
            for field in ("system", "run_id", "ref"):
                if not nonempty(item.get(field)):
                    issues.append(f"{prefix}.{field} is required")
            if str(item.get("status", "")).casefold() not in SUCCESSFUL_RUN_STATES:
                issues.append(
                    f"{prefix}.status must be one of {sorted(SUCCESSFUL_RUN_STATES)}"
                )
        elif kind == "decision":
            for field in ("owner", "reason"):
                if not nonempty(item.get(field)):
                    issues.append(f"{prefix}.{field} is required")
        elif kind == "url":
            parsed = urlparse(str(item.get("url", "")))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                issues.append(f"{prefix}.url must be an HTTP(S) URL")
            if item.get("result") not in {"accepted", "passed"}:
                issues.append(f"{prefix}.result must be accepted or passed")
    if ready and not machine_evidence:
        issues.append(
            f"gates.{gate_name}.evidence requires file, command, or run evidence"
        )
    if ready and gate_name in REQUIRED_REPORT_CHECKS and not passing_report:
        issues.append(
            f"gates.{gate_name}.evidence requires a matching JSON report with passed=true"
        )
    return issues


def validate(manifest: dict, ready: bool, base: Path | None = None) -> list[str]:
    issues: list[str] = []
    base = (base or Path.cwd()).resolve()
    if manifest.get("schema_version") != CURRENT_SCHEMA_VERSION:
        issues.append(
            f"schema_version must be {CURRENT_SCHEMA_VERSION}; add the current required gates when upgrading"
        )
    country = manifest.get("country") or {}
    for key in ("name", "iso2", "iso3"):
        if not nonempty(country.get(key)):
            issues.append(f"country.{key} is required")
    if nonempty(country.get("iso2")) and not re.fullmatch(
        r"[A-Z]{2}", str(country["iso2"])
    ):
        issues.append("country.iso2 must contain two uppercase letters")
    if nonempty(country.get("iso3")) and not re.fullmatch(
        r"[A-Z]{3}", str(country["iso3"])
    ):
        issues.append("country.iso3 must contain three uppercase letters")

    workbook = manifest.get("source_workbook") or {}
    if not nonempty(workbook.get("path_or_url")):
        issues.append("source_workbook.path_or_url is required")
    if not nonempty(workbook.get("local_snapshot")):
        issues.append("source_workbook.local_snapshot is required")
    workbook_digest = workbook.get("sha256")
    if not isinstance(workbook_digest, str) or not re.fullmatch(
        r"[0-9a-fA-F]{64}", workbook_digest
    ):
        issues.append("source_workbook.sha256 must contain 64 hexadecimal characters")
    workbook_path = local_path(workbook.get("local_snapshot"), base)
    if ready:
        if workbook_path is None or not workbook_path.is_file():
            issues.append("source_workbook.local_snapshot is not a local file")
        elif isinstance(workbook_digest, str) and re.fullmatch(
            r"[0-9a-fA-F]{64}", workbook_digest
        ):
            if sha256(workbook_path).casefold() != workbook_digest.casefold():
                issues.append(
                    "source_workbook.sha256 does not match the local workbook"
                )

    source_package = manifest.get("source_package") or {}
    for field in ("inventory_path", "inventory_sha256"):
        if not nonempty(source_package.get(field)):
            issues.append(f"source_package.{field} is required")
    if not isinstance(
        source_package.get("primary_source_ids"), list
    ) or not source_package.get("primary_source_ids"):
        issues.append("source_package.primary_source_ids must be a non-empty list")
    inventory_digest = source_package.get("inventory_sha256")
    if nonempty(inventory_digest) and (
        not isinstance(inventory_digest, str)
        or not re.fullmatch(r"[0-9a-fA-F]{64}", inventory_digest)
    ):
        issues.append(
            "source_package.inventory_sha256 must contain 64 hexadecimal characters"
        )
    inventory_path = local_path(source_package.get("inventory_path"), base)
    if ready:
        if inventory_path is None or not inventory_path.is_file():
            issues.append("source_package.inventory_path is not a local file")
        elif isinstance(inventory_digest, str) and re.fullmatch(
            r"[0-9a-fA-F]{64}", inventory_digest
        ):
            if sha256(inventory_path).casefold() != inventory_digest.casefold():
                issues.append(
                    "source_package.inventory_sha256 does not match the source inventory"
                )
            else:
                try:
                    inventory = load_json(inventory_path)
                except (json.JSONDecodeError, ValueError) as exc:
                    issues.append(f"source_package.inventory_path is invalid: {exc}")
                else:
                    if inventory.get("primary_source_ids") != source_package.get(
                        "primary_source_ids"
                    ):
                        issues.append(
                            "source_package.primary_source_ids does not match the source inventory"
                        )
                    inventory_country = inventory.get("country") or {}
                    for field in ("iso2", "iso3"):
                        if inventory_country.get(field) != country.get(field):
                            issues.append(
                                f"source inventory country.{field} does not match the manifest"
                            )
                    workbook_sources = [
                        source
                        for source in inventory.get("sources", [])
                        if isinstance(source, dict)
                        and source.get("kind") == "boost_workbook"
                    ]
                    if not any(
                        str(source.get("sha256", "")).casefold()
                        == str(workbook_digest).casefold()
                        for source in workbook_sources
                    ):
                        issues.append(
                            "source_workbook.sha256 is not listed as a BOOST workbook in the source inventory"
                        )

    workspace = manifest.get("workspace") or {}
    for field in ("root", "manifest_path"):
        if not nonempty(workspace.get(field)):
            issues.append(f"workspace.{field} is required")
    workspace_root = local_path(workspace.get("root"), base)
    if ready and (workspace_root is None or not workspace_root.is_dir()):
        issues.append("workspace.root is not a local directory")

    repositories = manifest.get("repositories") or {}
    for repo in ("mega-boost", "mega-indicators", "rpf-country-dash"):
        cfg = repositories.get(repo) or {}
        if not nonempty(cfg.get("path")):
            issues.append(f"repositories.{repo}.path is required")
        if not nonempty(cfg.get("baseline_ref")):
            issues.append(f"repositories.{repo}.baseline_ref is required")
        if ready and not nonempty(cfg.get("final_ref")):
            issues.append(f"repositories.{repo}.final_ref is required for readiness")
        repo_path = local_path(cfg.get("path"), base)
        if ready and (repo_path is None or not repo_path.is_dir()):
            issues.append(f"repositories.{repo}.path is not a local directory")

    gates = manifest.get("gates") or {}
    missing_gates = sorted(REQUIRED_GATES - set(gates))
    if missing_gates:
        issues.append(f"missing gates: {', '.join(missing_gates)}")
    for name, gate in gates.items():
        if not isinstance(gate, dict):
            issues.append(f"gates.{name} must be an object")
            continue
        status = gate.get("status")
        if status not in STATUSES:
            issues.append(f"gates.{name}.status must be one of {sorted(STATUSES)}")
        if status in {"passed", "not_applicable"}:
            issues.extend(
                validate_evidence(
                    name,
                    gate.get("evidence"),
                    ready,
                    base,
                    inventory_digest if isinstance(inventory_digest, str) else None,
                )
            )
        if ready and name in REQUIRED_GATES and status != "passed":
            issues.append(f"gates.{name} is not release-ready: {status}")

    subnational = manifest.get("subnational") or {}
    required = subnational.get("required")
    subnational_status = (gates.get("subnational") or {}).get("status")
    if required not in {True, False, None} or (
        required is None and (ready or subnational_status == "passed")
    ):
        issues.append("subnational.required must be true or false")
    if required is True:
        if not nonempty(subnational.get("target_admin_level")):
            issues.append(
                "subnational.target_admin_level is required when subnational data are required"
            )
        if not nonempty(subnational.get("target_units")):
            issues.append(
                "subnational.target_units is required when subnational data are required"
            )
        if not nonempty(subnational.get("sources")):
            issues.append(
                "subnational.sources is required when subnational data are required"
            )
    if required is False and not nonempty(subnational.get("decision_evidence")):
        issues.append(
            "subnational.decision_evidence is required for a central-only decision"
        )

    if ready:
        risks = manifest.get("risks", [])
        if not isinstance(risks, list):
            issues.append("risks must be a list")
            risks = []
        open_blockers = [
            risk
            for risk in risks
            if isinstance(risk, dict)
            and risk.get("release_blocking") is True
            and risk.get("status") not in {"resolved", "accepted"}
        ]
        if open_blockers:
            issues.append(f"{len(open_blockers)} release-blocking risk(s) remain open")
        for index, risk in enumerate(risks):
            if not isinstance(risk, dict):
                issues.append(f"risks[{index}] must be an object")
                continue
            for field in ("id", "owner", "status", "description"):
                if not nonempty(risk.get(field)):
                    issues.append(f"risks[{index}].{field} is required")
            if risk.get("release_blocking") not in {True, False}:
                issues.append(f"risks[{index}].release_blocking must be boolean")
            if risk.get("status") == "accepted":
                for field in ("accepted_by", "accepted_at", "acceptance_rationale"):
                    if not nonempty(risk.get(field)):
                        issues.append(
                            f"risks[{index}].{field} is required when accepted"
                        )
        if not nonempty((manifest.get("handoff") or {}).get("summary")):
            issues.append("handoff.summary is required for release readiness")
    return issues


def check(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    issues = validate(manifest, args.ready, args.manifest.resolve().parent)
    declared_path = local_path(
        (manifest.get("workspace") or {}).get("manifest_path"),
        args.manifest.resolve().parent,
    )
    if args.ready and (
        declared_path is None or declared_path.resolve() != args.manifest.resolve()
    ):
        issues.append("workspace.manifest_path does not match the checked manifest")
    result = {
        "manifest": str(args.manifest),
        "mode": "ready" if args.ready else "structural",
        "passed": not issues,
        "issues": issues,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if issues else 0


def next_step(args: argparse.Namespace) -> int:
    manifest = load_json(args.manifest)
    issues = validate(manifest, False, args.manifest.resolve().parent)
    gates = manifest.get("gates")
    if not isinstance(gates, dict):
        gates = {}
    current_gate = next(
        (
            name
            for name in GATE_ORDER
            if (gates.get(name) or {}).get("status") != "passed"
        ),
        None,
    )
    gate = gates.get(current_gate) or {} if current_gate else {}
    risks = manifest.get("risks")
    if not isinstance(risks, list):
        risks = []
    blocking_risks = [
        risk
        for risk in risks
        if isinstance(risk, dict)
        and risk.get("release_blocking") is True
        and risk.get("status") not in {"resolved", "accepted"}
    ]
    result = {
        "manifest": str(args.manifest),
        "structurally_valid": not issues,
        "current_gate": current_gate,
        "status": gate.get("status") if current_gate else "all_standard_gates_passed",
        "next_action": gate.get("next_action")
        if current_gate
        else (manifest.get("handoff") or {}).get("next_action"),
        "blocking_risks": blocking_risks,
        "issues": issues,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if issues else 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    init = sub.add_parser(
        "init", help="Create a populated manifest from the bundled template"
    )
    init.add_argument("--template", type=Path, required=True)
    init.add_argument("--output", type=Path, required=True)
    init.add_argument("--country", required=True)
    init.add_argument("--iso2", required=True)
    init.add_argument("--iso3", required=True)
    init.add_argument("--workspace", type=Path, required=True)
    init.add_argument("--workbook", type=Path)
    init.add_argument("--source-inventory", type=Path)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=initialize)

    verify = sub.add_parser(
        "check", help="Validate manifest structure or release readiness"
    )
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--ready", action="store_true")
    verify.set_defaults(func=check)

    next_command = sub.add_parser(
        "next", help="Show the first incomplete standard gate and its next action"
    )
    next_command.add_argument("--manifest", type=Path, required=True)
    next_command.set_defaults(func=next_step)
    return root


def main() -> int:
    args = parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
