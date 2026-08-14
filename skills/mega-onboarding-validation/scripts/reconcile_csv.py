#!/usr/bin/env python3
"""Reconcile two tabular measures with explicit missing-row statuses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def load(path: Path, sheet: str | None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, low_memory=False)
    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(path, sheet_name=sheet or 0)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".json":
        return pd.read_json(path)
    raise ValueError(f"Unsupported table format: {path}")


def aggregate(
    df: pd.DataFrame, keys: list[str], value: str, label: str
) -> tuple[pd.DataFrame, dict]:
    missing = sorted(set(keys + [value]) - set(df.columns))
    if missing:
        raise ValueError(f"{label} is missing columns {missing}")
    work = df[keys + [value]].copy()
    duplicate_rows = int(work.duplicated(keys, keep=False).sum())
    null_key_rows = int(work[keys].isna().any(axis=1).sum())
    raw_value = work[value]
    numeric_value = pd.to_numeric(raw_value, errors="coerce")
    invalid_value_rows = int((raw_value.notna() & numeric_value.isna()).sum())
    null_value_rows = int(raw_value.isna().sum())
    work[value] = numeric_value
    return work.groupby(keys, dropna=False, as_index=False)[value].sum(min_count=1), {
        "label": label,
        "duplicate_key_rows": duplicate_rows,
        "null_key_rows": null_key_rows,
        "invalid_value_rows": invalid_value_rows,
        "null_value_rows": null_value_rows,
    }


def json_value(value: object) -> object:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--left", type=Path, required=True, help="Pipeline or candidate table"
    )
    parser.add_argument(
        "--right", type=Path, required=True, help="Reference workbook/CCI table"
    )
    parser.add_argument("--left-sheet")
    parser.add_argument("--right-sheet")
    parser.add_argument("--keys", required=True, help="Comma-separated join keys")
    parser.add_argument("--left-value", required=True)
    parser.add_argument("--right-value", required=True)
    parser.add_argument("--absolute-tolerance", type=float, default=0.5)
    parser.add_argument("--relative-tolerance", type=float, default=0.05)
    parser.add_argument(
        "--denominator", choices=["left", "right", "max"], default="right"
    )
    parser.add_argument(
        "--allow-status",
        action="append",
        default=[],
        choices=["MISSING_LEFT", "MISSING_RIGHT"],
        help="Permit a missing-row status without failing the reconciliation",
    )
    parser.add_argument("--allow-duplicate-keys", action="store_true")
    parser.add_argument("--duplicate-key-reason")
    parser.add_argument("--allow-null-values", action="store_true")
    parser.add_argument("--null-value-reason")
    parser.add_argument("--detail-csv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    keys = [key.strip() for key in args.keys.split(",") if key.strip()]
    if not keys:
        raise SystemExit("At least one key is required")
    if args.allow_duplicate_keys and not args.duplicate_key_reason:
        parser.error("--allow-duplicate-keys requires --duplicate-key-reason")
    if args.allow_null_values and not args.null_value_reason:
        parser.error("--allow-null-values requires --null-value-reason")
    left_raw, right_raw = (
        load(args.left, args.left_sheet),
        load(args.right, args.right_sheet),
    )
    left, left_quality = aggregate(left_raw, keys, args.left_value, "left")
    right, right_quality = aggregate(right_raw, keys, args.right_value, "right")
    left = left.rename(columns={args.left_value: "left_value"})
    right = right.rename(columns={args.right_value: "right_value"})
    joined = left.merge(right, on=keys, how="outer", indicator=True)
    joined["absolute_difference"] = joined["left_value"] - joined["right_value"]
    if args.denominator == "left":
        denominator = joined["left_value"].abs()
    elif args.denominator == "right":
        denominator = joined["right_value"].abs()
    else:
        denominator = pd.concat(
            [joined["left_value"].abs(), joined["right_value"].abs()], axis=1
        ).max(axis=1)
    joined["relative_difference"] = joined[
        "absolute_difference"
    ].abs() / denominator.where(denominator.ne(0))

    statuses = []
    for _, row in joined.iterrows():
        if row["_merge"] == "left_only":
            statuses.append("MISSING_RIGHT")
            continue
        if row["_merge"] == "right_only":
            statuses.append("MISSING_LEFT")
            continue
        absolute = abs(float(row["absolute_difference"]))
        relative = row["relative_difference"]
        if absolute <= args.absolute_tolerance:
            statuses.append("MATCH")
        elif pd.notna(relative) and float(relative) <= args.relative_tolerance:
            statuses.append("MATCH")
        else:
            statuses.append("DISCREPANCY")
    joined["status"] = statuses
    joined = joined.drop(columns=["_merge"])
    args.detail_csv.parent.mkdir(parents=True, exist_ok=True)
    joined.to_csv(args.detail_csv, index=False)

    counts = joined["status"].value_counts().to_dict()
    blocking_statuses = {"DISCREPANCY", "MISSING_LEFT", "MISSING_RIGHT"} - set(
        args.allow_status
    )
    blockers = joined[joined["status"].isin(blocking_statuses)]
    quality_blockers = []
    for quality in (left_quality, right_quality):
        label = quality["label"]
        if quality["duplicate_key_rows"] and not args.allow_duplicate_keys:
            quality_blockers.append(
                f"{label} has {quality['duplicate_key_rows']} duplicate key row(s)"
            )
        if quality["null_key_rows"]:
            quality_blockers.append(
                f"{label} has {quality['null_key_rows']} null key row(s)"
            )
        if quality["invalid_value_rows"]:
            quality_blockers.append(
                f"{label} has {quality['invalid_value_rows']} invalid value row(s)"
            )
        if quality["null_value_rows"] and not args.allow_null_values:
            quality_blockers.append(
                f"{label} has {quality['null_value_rows']} null value row(s)"
            )
    sample = []
    for _, row in blockers.head(25).iterrows():
        sample.append(
            {
                **{key: json_value(row[key]) for key in keys},
                "left_value": json_value(row["left_value"]),
                "right_value": json_value(row["right_value"]),
                "absolute_difference": json_value(row["absolute_difference"]),
                "relative_difference": json_value(row["relative_difference"]),
                "status": row["status"],
            }
        )
    report = {
        "check": "reconciliation",
        "passed": blockers.empty and not quality_blockers,
        "left": str(args.left),
        "right": str(args.right),
        "keys": keys,
        "left_rows": int(len(left_raw)),
        "right_rows": int(len(right_raw)),
        "input_quality": {"left": left_quality, "right": right_quality},
        "quality_exceptions": {
            "duplicate_keys": args.duplicate_key_reason
            if args.allow_duplicate_keys
            else None,
            "null_values": args.null_value_reason if args.allow_null_values else None,
        },
        "quality_blockers": quality_blockers,
        "comparison_rows": int(len(joined)),
        "status_counts": {str(key): int(value) for key, value in counts.items()},
        "tolerances": {
            "absolute": args.absolute_tolerance,
            "relative": args.relative_tolerance,
            "denominator": args.denominator,
        },
        "allowed_statuses": args.allow_status,
        "blocking_sample": sample,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"passed": report["passed"], "status_counts": report["status_counts"]}
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
