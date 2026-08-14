#!/usr/bin/env python3
"""Audit subnational datasets against an explicit administrative contract."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd


def resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def load_table(path: Path, kind: str, sheet: str | None = None) -> pd.DataFrame:
    if kind == "csv":
        return pd.read_csv(path, low_memory=False)
    if kind in {"xlsx", "xlsm"}:
        return pd.read_excel(path, sheet_name=sheet or 0)
    if kind == "parquet":
        return pd.read_parquet(path)
    if kind == "json":
        return pd.read_json(path)
    raise ValueError(f"Unsupported table format {kind!r}")


def load_boundaries(target: dict, base: Path) -> tuple[list[str], dict]:
    path = resolve(base, target["boundary_path"])
    kind = target.get("boundary_format") or path.suffix.lower().lstrip(".")
    name_field = target["boundary_name_property"]
    geometry_report = {"checked": False, "missing": 0, "invalid": [], "reason": None}
    if kind in {"geojson", "json"}:
        payload = json.loads(path.read_text(encoding="utf-8"))
        features = payload.get("features", [])
        names = [
            str((feature.get("properties") or {}).get(name_field, "")).strip()
            for feature in features
        ]
        geometry_report["missing"] = sum(
            not feature.get("geometry") for feature in features
        )
        try:
            from shapely.geometry import shape
        except ImportError:
            geometry_report["reason"] = (
                "shapely is unavailable; geometry validity not checked"
            )
        else:
            geometry_report["checked"] = True
            for index, feature in enumerate(features):
                geometry = feature.get("geometry")
                if not geometry:
                    continue
                try:
                    value = shape(geometry)
                    if value.is_empty or not value.is_valid:
                        geometry_report["invalid"].append(
                            {
                                "feature_index": index,
                                "name": names[index],
                                "is_empty": value.is_empty,
                            }
                        )
                except Exception as exc:  # malformed source geometry must be reported
                    geometry_report["invalid"].append(
                        {
                            "feature_index": index,
                            "name": names[index],
                            "error": str(exc),
                        }
                    )
        return names, geometry_report
    table = load_table(path, kind, target.get("sheet"))
    if name_field not in table.columns:
        raise ValueError(f"Boundary name field {name_field!r} missing from {path}")
    names = table[name_field].fillna("").astype(str).str.strip().tolist()
    geometry_report["reason"] = "tabular boundary input has no geometry validation"
    return names, geometry_report


def normalize_name(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def audit_dataset(cfg: dict, targets: set[str], base: Path) -> dict:
    path = resolve(base, cfg["path"])
    kind = cfg.get("format") or path.suffix.lower().lstrip(".")
    df = load_table(path, kind, cfg.get("sheet"))
    required_columns = [cfg["name_column"]]
    for key in ("year_column", "value_column"):
        if cfg.get(key):
            required_columns.append(cfg[key])
    missing_columns = sorted(set(required_columns) - set(df.columns))
    if missing_columns:
        return {
            "name": cfg["name"],
            "path": str(path),
            "passed": False,
            "issues": [f"missing columns: {missing_columns}"],
        }

    name_col = cfg["name_column"]
    year_col = cfg.get("year_column")
    value_col = cfg.get("value_column")
    work = df.copy()
    work["_source_name"] = work[name_col].map(normalize_name)
    mapping = cfg.get("mapping", {})
    work["_target_name"] = work["_source_name"].replace(mapping)
    source_names = sorted(name for name in work["_source_name"].unique() if name)
    mapped_names = sorted(name for name in work["_target_name"].unique() if name)
    unmatched = sorted(set(mapped_names) - targets)
    target_without_any_data = sorted(targets - set(mapped_names))
    mapping_targets_outside = sorted(set(mapping.values()) - targets)
    unused_mapping_sources = sorted(set(mapping) - set(source_names))
    empty_source_names = int(work["_source_name"].eq("").sum())
    issues: list[str] = []
    warnings: list[str] = []
    if unmatched:
        issues.append(f"mapped source names outside target boundaries: {unmatched}")
    if mapping_targets_outside:
        issues.append(
            f"mapping targets outside target boundaries: {mapping_targets_outside}"
        )
    if empty_source_names:
        issues.append(f"{empty_source_names} rows have empty source names")
    if unused_mapping_sources:
        warnings.append(f"unused mapping source labels: {unused_mapping_sources}")

    if "accepted_no_data_targets" in cfg or "accepted_no_data_reasons" in cfg:
        issues.append(
            "legacy accepted_no_data_targets/reasons are not release-valid; use reviewed accepted_no_data objects"
        )
    accepted_entries = cfg.get("accepted_no_data", [])
    if not isinstance(accepted_entries, list):
        issues.append("accepted_no_data must be a list")
        accepted_entries = []
    accepted_no_data: set[str] = set()
    reviewed_entries: list[dict] = []
    for index, entry in enumerate(accepted_entries):
        prefix = f"accepted_no_data[{index}]"
        if not isinstance(entry, dict):
            issues.append(f"{prefix} must be an object")
            continue
        target = entry.get("target")
        if not isinstance(target, str) or not target.strip():
            issues.append(f"{prefix}.target is required")
            continue
        target = target.strip()
        if target in accepted_no_data:
            issues.append(f"accepted_no_data repeats target {target!r}")
            continue
        accepted_no_data.add(target)
        for field in ("reason", "owner", "evidence"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                issues.append(f"{prefix}.{field} is required")
        if not valid_timestamp(entry.get("checked_at")):
            issues.append(
                f"{prefix}.checked_at must be an ISO-8601 timestamp with timezone"
            )
        reviewed_entries.append(entry)
    accepted_outside = sorted(accepted_no_data - targets)
    if accepted_outside:
        issues.append(
            f"accepted no-data targets outside target boundaries: {accepted_outside}"
        )
    unexpected_no_data = sorted(set(target_without_any_data) - accepted_no_data)
    if cfg.get("required_complete") and unexpected_no_data:
        issues.append(f"target units without any data: {unexpected_no_data}")

    value_stats = None
    if value_col:
        numeric = pd.to_numeric(work[value_col], errors="coerce")
        nonnumeric = int(numeric.isna().sum() - work[value_col].isna().sum())
        nulls = int(work[value_col].isna().sum())
        negatives = int((numeric < 0).sum())
        value_stats = {
            "null": nulls,
            "nonnumeric": max(nonnumeric, 0),
            "negative": negatives,
        }
        if nulls:
            issues.append(f"{nulls} rows have null {value_col}")
        if nonnumeric > 0:
            issues.append(f"{nonnumeric} rows have nonnumeric {value_col}")
        if negatives and not cfg.get("allow_negative", False):
            issues.append(f"{negatives} rows have negative {value_col}")

    key_columns = ["_target_name"] + ([year_col] if year_col else [])
    duplicate_rows = int(work.duplicated(key_columns, keep=False).sum())
    collisions = {
        target: sorted(group["_source_name"].unique())
        for target, group in work.groupby("_target_name")
        if target and group["_source_name"].nunique() > 1
    }
    aggregation = cfg.get("aggregation")
    if duplicate_rows and aggregation != "sum":
        issues.append(f"{duplicate_rows} rows duplicate target keys {key_columns}")
    if collisions and aggregation != "sum":
        issues.append(
            "many-to-one mappings require aggregation='sum' or pre-aggregated input"
        )

    required_year_gaps = []
    if year_col and cfg.get("required_years"):
        normalized_year = pd.to_numeric(work[year_col], errors="coerce").astype("Int64")
        invalid_years = int(normalized_year.isna().sum())
        if invalid_years:
            issues.append(f"{invalid_years} rows have invalid or null {year_col}")
        work["_normalized_year"] = normalized_year
        for year in cfg["required_years"]:
            present = set(
                work.loc[work["_normalized_year"].eq(int(year)), "_target_name"]
            )
            missing = sorted(targets - present - accepted_no_data)
            if missing:
                required_year_gaps.append({"year": int(year), "targets": missing})
        if cfg.get("required_complete") and required_year_gaps:
            issues.append(f"required year coverage gaps: {required_year_gaps}")

    return {
        "name": cfg["name"],
        "path": str(path),
        "passed": not issues,
        "rows": int(len(work)),
        "source_unit_count": len(source_names),
        "mapped_target_count": len(set(mapped_names) & targets),
        "unmatched_mapped_names": unmatched,
        "target_without_any_data": target_without_any_data,
        "accepted_no_data": reviewed_entries,
        "mapping_collisions": collisions,
        "duplicate_target_key_rows": duplicate_rows,
        "required_year_gaps": required_year_gaps,
        "value_stats": value_stats,
        "issues": issues,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    if not isinstance(contract, dict):
        raise SystemExit("Contract must be a JSON object")
    base = args.contract.resolve().parent
    contract_issues = []
    if not isinstance(contract.get("country"), str) or not contract["country"].strip():
        contract_issues.append("country is required")
    if not isinstance(contract.get("iso3"), str) or not contract["iso3"].strip():
        contract_issues.append("iso3 is required")
    if contract.get("subnational_required") is not True:
        contract_issues.append(
            "subnational_required must be true; record a central-only decision in the onboarding manifest instead"
        )
    required_dataset_names = contract.get("required_dataset_names")
    if not isinstance(required_dataset_names, list) or not required_dataset_names:
        contract_issues.append("required_dataset_names must be a non-empty list")
        required_dataset_names = []
    elif not all(
        isinstance(name, str) and name.strip() for name in required_dataset_names
    ):
        contract_issues.append("required_dataset_names must contain non-empty strings")
    duplicate_required_names = sorted(
        name
        for name in set(required_dataset_names)
        if required_dataset_names.count(name) > 1
    )
    if duplicate_required_names:
        contract_issues.append(
            f"required_dataset_names contains duplicates: {duplicate_required_names}"
        )
    target = contract.get("target")
    if not isinstance(target, dict):
        contract_issues.append("target must be an object")
        target = {}
    for field in ("admin_level", "vintage", "boundary_path", "boundary_name_property"):
        if not isinstance(target.get(field), str) or not target[field].strip():
            contract_issues.append(f"target.{field} is required")
    if target.get("require_geometry_validation") is not True:
        contract_issues.append(
            "target.require_geometry_validation must be true for a release audit"
        )
    geometry = {"checked": False, "missing": 0, "invalid": [], "reason": None}
    boundary_names = []
    try:
        boundary_names, geometry = load_boundaries(target, base)
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        contract_issues.append(f"boundary input could not be loaded: {exc}")
        geometry["reason"] = "boundary input could not be loaded"
    counts = Counter(boundary_names)
    blank_names = counts.get("", 0)
    duplicate_names = sorted(
        name for name, count in counts.items() if name and count > 1
    )
    targets = {name for name in boundary_names if name}
    boundary_issues = list(contract_issues)
    if blank_names:
        boundary_issues.append(f"{blank_names} boundaries have empty names")
    if duplicate_names:
        boundary_issues.append(f"duplicate boundary names: {duplicate_names}")
    expected_count = target.get("expected_unit_count")
    if expected_count is None:
        boundary_issues.append("target.expected_unit_count is required")
    else:
        try:
            expected_count = int(expected_count)
        except (TypeError, ValueError):
            boundary_issues.append("target.expected_unit_count must be an integer")
        else:
            if expected_count < 1:
                boundary_issues.append(
                    "target.expected_unit_count must be greater than zero"
                )
            elif len(targets) != expected_count:
                boundary_issues.append(
                    f"expected {expected_count} target units, found {len(targets)}"
                )
    if geometry["missing"]:
        boundary_issues.append(
            f"{geometry['missing']} boundaries have missing geometry"
        )
    if geometry["invalid"]:
        boundary_issues.append(
            f"{len(geometry['invalid'])} boundaries have invalid geometry"
        )
    if not geometry["checked"]:
        boundary_issues.append(
            geometry["reason"] or "geometry validity was not checked"
        )

    dataset_configs = contract.get("datasets", [])
    if not isinstance(dataset_configs, list) or not dataset_configs:
        boundary_issues.append("datasets must be a non-empty list")
        dataset_configs = []
    dataset_names = [
        cfg.get("name") for cfg in dataset_configs if isinstance(cfg, dict)
    ]
    duplicate_dataset_names = sorted(
        name for name in set(dataset_names) if name and dataset_names.count(name) > 1
    )
    if duplicate_dataset_names:
        boundary_issues.append(
            f"dataset names must be unique: {duplicate_dataset_names}"
        )
    missing_required_datasets = sorted(set(required_dataset_names) - set(dataset_names))
    if missing_required_datasets:
        boundary_issues.append(
            f"required datasets are missing: {missing_required_datasets}"
        )
    datasets = []
    for cfg in dataset_configs:
        if not isinstance(cfg, dict):
            boundary_issues.append("every dataset must be an object")
            continue
        config_valid = True
        for field in ("name", "role", "path", "name_column"):
            if not isinstance(cfg.get(field), str) or not cfg[field].strip():
                config_valid = False
                boundary_issues.append(
                    f"dataset {cfg.get('name', '<unnamed>')}: {field} is required"
                )
        if (
            cfg.get("name") in required_dataset_names
            and cfg.get("required_complete") is not True
        ):
            boundary_issues.append(
                f"dataset {cfg.get('name')}: required_complete must be true"
            )
        if not config_valid:
            continue
        try:
            datasets.append(audit_dataset(cfg, targets, base))
        except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
            datasets.append(
                {
                    "name": cfg["name"],
                    "path": str(resolve(base, cfg["path"])),
                    "passed": False,
                    "issues": [f"dataset could not be audited: {exc}"],
                }
            )
    issues = list(boundary_issues)
    for dataset in datasets:
        issues.extend(
            f"{dataset['name']}: {issue}" for issue in dataset.get("issues", [])
        )
    report = {
        "check": "subnational",
        "country": contract.get("country"),
        "iso3": contract.get("iso3"),
        "passed": not issues,
        "target": {
            "admin_level": target.get("admin_level"),
            "vintage": target.get("vintage"),
            "unit_count": len(targets),
            "units": sorted(targets),
            "duplicate_names": duplicate_names,
            "geometry": geometry,
        },
        "datasets": datasets,
        "required_dataset_names": required_dataset_names,
        "issues": issues,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "country": report["country"],
                "passed": report["passed"],
                "target_units": len(targets),
                "datasets": len(datasets),
                "issues": len(issues),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
