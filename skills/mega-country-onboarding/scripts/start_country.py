#!/usr/bin/env python3
"""Create a validated first-hour workspace for a MEGA country onboarding."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import check_manifest
import check_source_inventory


REPOSITORIES = ("mega-boost", "mega-indicators", "rpf-country-dash")
DEFAULT_PRODUCTS = (
    "boost_country_gold",
    "cross_country_aggregate",
    "country_dashboard",
)


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"Cannot inspect Git repository {repo}: {detail}")
    return completed.stdout.strip()


def repository_contract(repo_root: Path) -> dict[str, dict]:
    contract = {}
    for name in REPOSITORIES:
        path = (repo_root / name).resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"Required repository is missing: {path}")
        baseline = git(path, "rev-parse", "HEAD")
        dirty = git(path, "status", "--porcelain")
        if dirty:
            raise ValueError(
                f"Repository {path} is not clean. Preserve the existing work and start "
                "the onboarding from a clean branch or worktree."
            )
        contract[name] = {
            "path": str(path),
            "baseline_ref": baseline,
            "final_ref": None,
        }
    return contract


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", required=True)
    parser.add_argument("--iso2", required=True)
    parser.add_argument("--iso3", required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--source-owner", required=True)
    parser.add_argument("--year", type=int, action="append", required=True)
    parser.add_argument(
        "--stage",
        choices=("approved", "revised", "executed"),
        action="append",
        required=True,
    )
    parser.add_argument("--currency", required=True)
    parser.add_argument("--amount-unit", required=True)
    parser.add_argument("--fiscal-year-convention", required=True)
    parser.add_argument(
        "--subnational-review",
        choices=("pending", "candidate", "central_only"),
        default="pending",
    )
    parser.add_argument(
        "--data-classification",
        choices=("public", "internal", "restricted"),
        default="internal",
    )
    parser.add_argument("--published-product", action="append")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument(
        "--template",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "assets"
        / "onboarding-manifest.json",
    )
    return parser.parse_args()


def validate_identifiers(args: argparse.Namespace) -> tuple[str, str]:
    iso2 = args.iso2.upper()
    iso3 = args.iso3.upper()
    if not re.fullmatch(r"[A-Z]{2}", iso2):
        raise ValueError("--iso2 must contain two letters")
    if not re.fullmatch(r"[A-Z]{3}", iso3):
        raise ValueError("--iso3 must contain three letters")
    if len(args.year) != len(set(args.year)):
        raise ValueError("--year contains duplicates")
    if len(args.stage) != len(set(args.stage)):
        raise ValueError("--stage contains duplicates")
    return iso2, iso3


def main() -> int:
    args = parse_args()
    try:
        iso2, iso3 = validate_identifiers(args)
        workbook = args.workbook.resolve()
        workspace = args.workspace.resolve()
        if not workbook.is_file():
            raise FileNotFoundError(f"Workbook does not exist: {workbook}")
        if not args.template.is_file():
            raise FileNotFoundError(
                f"Manifest template does not exist: {args.template}"
            )

        inventory_path = workspace / "source-inventory.json"
        intake_report_path = workspace / "reports" / "source-intake.json"
        manifest_path = workspace / "onboarding-manifest.json"
        existing = [
            path
            for path in (inventory_path, intake_report_path, manifest_path)
            if path.exists()
        ]
        if existing:
            joined = ", ".join(str(path) for path in existing)
            raise FileExistsError(
                f"Refusing to overwrite an existing onboarding record: {joined}. "
                "Resume from the existing manifest instead."
            )

        captured_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        workbook_digest = sha256_file(workbook)
        inventory = {
            "country": {"name": args.country, "iso2": iso2, "iso3": iso3},
            "captured_at": captured_at,
            "scope": {
                "stages": list(dict.fromkeys(args.stage)),
                "expected_years": sorted(args.year),
                "currency": args.currency,
                "amount_unit": args.amount_unit,
                "fiscal_year_convention": args.fiscal_year_convention,
                "subnational_review": args.subnational_review,
                "published_products": args.published_product or list(DEFAULT_PRODUCTS),
            },
            "primary_source_ids": ["boost_workbook"],
            "sources": [
                {
                    "id": "boost_workbook",
                    "kind": "boost_workbook",
                    "authority": "authoritative",
                    "required": True,
                    "path_or_url": str(workbook),
                    "local_snapshot": str(workbook),
                    "sha256": workbook_digest,
                    "owner": args.source_owner,
                    "format": workbook.suffix.lstrip(".").casefold() or "unknown",
                    "data_classification": args.data_classification,
                    "derived_from": [],
                    "notes": [],
                }
            ],
            "known_constraints": [],
        }
        inventory_issues, checked_sources = check_source_inventory.validate(
            inventory, workspace
        )
        if inventory_issues:
            raise ValueError("Invalid source inventory: " + "; ".join(inventory_issues))
        inventory_content = json_bytes(inventory)
        inventory_digest = sha256_bytes(inventory_content)
        intake_report = {
            "check": "source_intake",
            "passed": True,
            "inventory": str(inventory_path),
            "inventory_sha256": inventory_digest,
            "source_count": len(checked_sources),
            "checked_sources": checked_sources,
            "issues": [],
        }
        intake_content = json_bytes(intake_report)

        repositories = repository_contract(args.repo_root.resolve())
        manifest = deepcopy(check_manifest.load_json(args.template))
        manifest["country"] = inventory["country"]
        manifest["workspace"] = {
            "root": str(workspace),
            "manifest_path": str(manifest_path),
        }
        manifest["source_workbook"].update(
            {
                "path_or_url": str(workbook),
                "local_snapshot": str(workbook),
                "sha256": workbook_digest,
                "authoritative_owner": args.source_owner,
            }
        )
        manifest["source_package"] = {
            "inventory_path": str(inventory_path),
            "inventory_sha256": inventory_digest,
            "primary_source_ids": ["boost_workbook"],
        }
        manifest["repositories"] = repositories
        manifest["gates"]["intake"] = {
            "status": "passed",
            "evidence": [
                {
                    "kind": "file",
                    "path": str(intake_report_path),
                    "sha256": sha256_bytes(intake_content),
                    "checked_at": captured_at,
                }
            ],
            "next_action": None,
        }
        manifest["handoff"]["next_action"] = manifest["gates"]["workbook_audit"][
            "next_action"
        ]
        manifest_issues = check_manifest.validate(manifest, False, workspace)
        if manifest_issues:
            raise ValueError("Invalid initial manifest: " + "; ".join(manifest_issues))

        (workspace / "reports").mkdir(parents=True, exist_ok=True)
        (workspace / "decisions").mkdir(parents=True, exist_ok=True)
        inventory_path.write_bytes(inventory_content)
        intake_report_path.write_bytes(intake_content)
        manifest_path.write_bytes(json_bytes(manifest))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"created": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    result = {
        "created": True,
        "country": manifest["country"],
        "workspace": str(workspace),
        "manifest": str(manifest_path),
        "source_inventory": str(inventory_path),
        "intake_report": str(intake_report_path),
        "intake_passed": True,
        "next_gate": "workbook_audit",
        "next_action": manifest["gates"]["workbook_audit"]["next_action"],
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
