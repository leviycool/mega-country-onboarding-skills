#!/usr/bin/env python3
"""Validate the raw-source inventory for a MEGA country onboarding."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


SOURCE_KINDS = {
    "boost_workbook",
    "raw_microdata",
    "classification_dictionary",
    "boundary",
    "population",
    "outcome_indicator",
    "supplemental",
}
AUTHORITIES = {"authoritative", "supporting", "derived"}
DATA_CLASSIFICATIONS = {"public", "internal", "restricted"}
STAGES = {"approved", "revised", "executed"}
SUBNATIONAL_REVIEW_STATES = {"pending", "candidate", "central_only"}


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


def validate(inventory: dict, base: Path) -> tuple[list[str], list[dict]]:
    issues: list[str] = []
    checked_sources: list[dict] = []

    country = inventory.get("country") or {}
    for field in ("name", "iso2", "iso3"):
        if not nonempty(country.get(field)):
            issues.append(f"country.{field} is required")
    if nonempty(country.get("iso2")) and not re.fullmatch(
        r"[A-Z]{2}", str(country["iso2"])
    ):
        issues.append("country.iso2 must contain two uppercase letters")
    if nonempty(country.get("iso3")) and not re.fullmatch(
        r"[A-Z]{3}", str(country["iso3"])
    ):
        issues.append("country.iso3 must contain three uppercase letters")
    if not valid_timestamp(inventory.get("captured_at")):
        issues.append("captured_at must be an ISO-8601 timestamp with timezone")

    scope = inventory.get("scope") or {}
    stages = scope.get("stages")
    if not isinstance(stages, list) or not stages:
        issues.append("scope.stages must be a non-empty list")
    else:
        normalized_stages = [str(stage).casefold() for stage in stages]
        unknown_stages = sorted(set(normalized_stages) - STAGES)
        if unknown_stages:
            issues.append(f"scope.stages contains unsupported values: {unknown_stages}")
        if len(normalized_stages) != len(set(normalized_stages)):
            issues.append("scope.stages contains duplicates")
    years = scope.get("expected_years")
    if not isinstance(years, list) or not years:
        issues.append("scope.expected_years must be a non-empty list")
    else:
        invalid_years = [year for year in years if not isinstance(year, int)]
        if invalid_years:
            issues.append("scope.expected_years must contain integers")
        if len(years) != len(set(years)):
            issues.append("scope.expected_years contains duplicates")
    for field in ("currency", "amount_unit", "fiscal_year_convention"):
        if not nonempty(scope.get(field)):
            issues.append(f"scope.{field} is required")
    if scope.get("subnational_review") not in SUBNATIONAL_REVIEW_STATES:
        issues.append(
            "scope.subnational_review must be pending, candidate, or central_only"
        )
    if not isinstance(scope.get("published_products"), list) or not scope.get(
        "published_products"
    ):
        issues.append("scope.published_products must be a non-empty list")

    sources = inventory.get("sources")
    if not isinstance(sources, list) or not sources:
        return [*issues, "sources must be a non-empty list"], checked_sources

    source_ids: list[str] = []
    authoritative_ids: set[str] = set()
    source_by_id: dict[str, dict] = {}
    for index, source in enumerate(sources):
        prefix = f"sources[{index}]"
        if not isinstance(source, dict):
            issues.append(f"{prefix} must be an object")
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not re.fullmatch(
            r"[a-z0-9][a-z0-9_-]*", source_id
        ):
            issues.append(f"{prefix}.id must be a lowercase stable identifier")
        else:
            source_ids.append(source_id)
            source_by_id[source_id] = source
        if source.get("kind") not in SOURCE_KINDS:
            issues.append(f"{prefix}.kind must be one of {sorted(SOURCE_KINDS)}")
        authority = source.get("authority")
        if authority not in AUTHORITIES:
            issues.append(f"{prefix}.authority must be one of {sorted(AUTHORITIES)}")
        elif authority == "authoritative" and isinstance(source_id, str):
            authoritative_ids.add(source_id)
        if source.get("required") not in {True, False}:
            issues.append(f"{prefix}.required must be boolean")
        for field in ("path_or_url", "local_snapshot", "owner", "format"):
            if not nonempty(source.get(field)):
                issues.append(f"{prefix}.{field} is required")
        if source.get("data_classification") not in DATA_CLASSIFICATIONS:
            issues.append(
                f"{prefix}.data_classification must be one of {sorted(DATA_CLASSIFICATIONS)}"
            )
        digest = source.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            issues.append(f"{prefix}.sha256 must contain 64 hexadecimal characters")
        snapshot = local_path(source.get("local_snapshot"), base)
        if snapshot is None or not snapshot.is_file():
            issues.append(f"{prefix}.local_snapshot is not a local file")
        elif isinstance(digest, str) and re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            observed = sha256(snapshot)
            if observed.casefold() != digest.casefold():
                issues.append(f"{prefix}.sha256 does not match {snapshot}")
            checked_sources.append(
                {
                    "id": source_id,
                    "kind": source.get("kind"),
                    "authority": authority,
                    "required": source.get("required"),
                    "local_snapshot": str(snapshot.resolve()),
                    "sha256": observed,
                    "bytes": snapshot.stat().st_size,
                }
            )
        derived_from = source.get("derived_from", [])
        if authority == "derived" and (
            not isinstance(derived_from, list) or not derived_from
        ):
            issues.append(f"{prefix}.derived_from is required for derived sources")
        elif not isinstance(derived_from, list):
            issues.append(f"{prefix}.derived_from must be a list")

    duplicate_ids = sorted(
        source_id for source_id in set(source_ids) if source_ids.count(source_id) > 1
    )
    if duplicate_ids:
        issues.append(f"source ids are duplicated: {duplicate_ids}")

    known_ids = set(source_ids)
    for source_id, source in source_by_id.items():
        for parent_id in source.get("derived_from", []):
            if parent_id == source_id:
                issues.append(f"source {source_id} cannot derive from itself")
            elif parent_id not in known_ids:
                issues.append(
                    f"source {source_id} derives from unknown source {parent_id}"
                )

    primary_source_ids = inventory.get("primary_source_ids")
    if not isinstance(primary_source_ids, list) or not primary_source_ids:
        issues.append("primary_source_ids must be a non-empty list")
    else:
        if len(primary_source_ids) != len(set(primary_source_ids)):
            issues.append("primary_source_ids contains duplicates")
        for source_id in primary_source_ids:
            if source_id not in known_ids:
                issues.append(f"primary source {source_id} is not listed in sources")
            elif source_id not in authoritative_ids:
                issues.append(f"primary source {source_id} must be authoritative")

    if not authoritative_ids:
        issues.append("at least one source must be authoritative")
    if not any(
        isinstance(source, dict) and source.get("kind") == "boost_workbook"
        for source in sources
    ):
        issues.append("sources must include the BOOST workbook used for onboarding")

    return issues, checked_sources


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        inventory = load_json(args.inventory)
        issues, checked_sources = validate(inventory, args.inventory.resolve().parent)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issues = [str(exc)]
        checked_sources = []

    report = {
        "check": "source_intake",
        "passed": not issues,
        "inventory": str(args.inventory),
        "inventory_sha256": sha256(args.inventory)
        if args.inventory.is_file()
        else None,
        "source_count": len(checked_sources),
        "checked_sources": checked_sources,
        "issues": issues,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
