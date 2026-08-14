#!/usr/bin/env python3
"""Validate a foreign-funding flag against source logic and amount partitions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd


TRUE_VALUES = {"1", "true"}
FALSE_VALUES = {"0", "false"}
DERIVED_FLAG_COLUMN = "_source_derived_is_foreign"


def load_table(path: Path, sheet: str | None) -> pd.DataFrame:
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


def normalize_flag(value: object) -> tuple[str, bool | None]:
    if pd.isna(value) or (isinstance(value, str) and not value.strip()):
        return "null", None
    if isinstance(value, bool):
        return "valid", value
    text = str(value).strip().casefold()
    if text in TRUE_VALUES:
        return "valid", True
    if text in FALSE_VALUES:
        return "valid", False
    return "invalid", None


def normalize_series(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    parsed = series.map(normalize_flag)
    return parsed.map(lambda item: item[0]), parsed.map(lambda item: item[1])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def criterion_mask(series: pd.Series, criterion: dict) -> pd.Series:
    operator = criterion.get("operator")
    value = criterion.get("value")
    if operator == "is_null":
        return series.isna() | series.astype("string").str.strip().eq("")
    if operator == "not_null":
        return ~(series.isna() | series.astype("string").str.strip().eq(""))
    if operator in {"lt", "le", "gt", "ge"}:
        numeric = pd.to_numeric(series, errors="coerce")
        target = float(value)
        return {
            "lt": numeric.lt(target),
            "le": numeric.le(target),
            "gt": numeric.gt(target),
            "ge": numeric.ge(target),
        }[operator].fillna(False)
    text = series.fillna("").astype(str)
    case_sensitive = criterion.get("case_sensitive", False) is True
    comparable = text if case_sensitive else text.str.casefold()
    if isinstance(value, str):
        target = value if case_sensitive else value.casefold()
    else:
        target = value
    if operator == "equals":
        return comparable.eq(str(target))
    if operator == "not_equals":
        return comparable.ne(str(target))
    if operator == "starts_with":
        return comparable.str.startswith(str(target), na=False)
    if operator == "contains":
        return comparable.str.contains(re.escape(str(target)), regex=True, na=False)
    if operator == "regex":
        flags = 0 if case_sensitive else re.IGNORECASE
        return text.str.contains(str(value), regex=True, flags=flags, na=False)
    if operator in {"in", "not_in"}:
        if not isinstance(value, list):
            raise ValueError(f"{operator} requires a list value")
        allowed = {
            str(item) if case_sensitive else str(item).casefold() for item in value
        }
        result = comparable.isin(allowed)
        return ~result if operator == "not_in" else result
    raise ValueError(f"Unsupported predicate operator: {operator!r}")


def derive_expected_flag(
    frame: pd.DataFrame,
    config: dict,
    forbidden_columns: set[str],
) -> tuple[pd.Series, list[str]]:
    if not isinstance(config, dict):
        raise ValueError("Predicate config must be a JSON object")
    description = config.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Predicate config requires a non-empty description")
    branches = config.get("branches")
    if not isinstance(branches, list) or not branches:
        raise ValueError("Predicate config requires a non-empty branches list")
    result = pd.Series(False, index=frame.index)
    used_columns = []
    for branch_index, branch in enumerate(branches):
        criteria = branch.get("all") if isinstance(branch, dict) else None
        if not isinstance(criteria, list) or not criteria:
            raise ValueError(f"Predicate branch {branch_index} requires non-empty all")
        branch_mask = pd.Series(True, index=frame.index)
        for criterion_index, criterion in enumerate(criteria):
            if not isinstance(criterion, dict):
                raise ValueError(
                    f"Predicate branch {branch_index} criterion {criterion_index} must be an object"
                )
            column = criterion.get("column")
            if not isinstance(column, str) or not column:
                raise ValueError("Every predicate criterion requires a column")
            if column in forbidden_columns:
                raise ValueError(
                    f"Predicate cannot use output or expected flag column {column!r}"
                )
            if column not in frame.columns:
                raise ValueError(f"Predicate source column is missing: {column}")
            used_columns.append(column)
            branch_mask &= criterion_mask(frame[column], criterion)
        result |= branch_mask
    return result.astype(bool), sorted(set(used_columns))


def json_value(value: object) -> object:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def sample_rows(
    frame: pd.DataFrame,
    mask: pd.Series,
    id_columns: list[str],
    output_column: str,
    expected_column: str | None,
    limit: int,
) -> list[dict]:
    columns = id_columns + [output_column]
    if expected_column:
        columns.append(expected_column)
    result = []
    for index, row in frame.loc[mask, columns].head(limit).iterrows():
        item = {"row_index": json_value(index)}
        item.update({column: json_value(row[column]) for column in columns})
        result.append(item)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--sheet")
    parser.add_argument("--flag-column", default="is_foreign")
    parser.add_argument("--expected-flag-column")
    parser.add_argument("--require-expected-flag", action="store_true")
    parser.add_argument("--predicate-config", type=Path)
    parser.add_argument("--require-independent-predicate", action="store_true")
    parser.add_argument(
        "--source-rule",
        help="Reviewed raw-source predicate used to derive the expected flag",
    )
    parser.add_argument("--year-column", default="year")
    parser.add_argument("--measure", action="append", required=True)
    parser.add_argument("--id-column", action="append", default=[])
    parser.add_argument("--allow-null-flag", action="store_true")
    parser.add_argument("--allow-null-measures", action="store_true")
    parser.add_argument("--require-both-values", action="store_true")
    parser.add_argument("--absolute-tolerance", type=float, default=0.01)
    parser.add_argument("--sample-limit", type=int, default=25)
    parser.add_argument("--detail-csv", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    if args.require_expected_flag and not args.expected_flag_column:
        parser.error("--require-expected-flag requires --expected-flag-column")
    if args.require_expected_flag and not args.source_rule:
        parser.error("--require-expected-flag requires --source-rule")
    if args.expected_flag_column == args.flag_column:
        parser.error("--expected-flag-column must differ from --flag-column")
    if args.require_independent_predicate and not args.predicate_config:
        parser.error("--require-independent-predicate requires --predicate-config")
    if args.require_independent_predicate and not args.id_column:
        parser.error("--require-independent-predicate requires --id-column")
    if args.absolute_tolerance < 0:
        parser.error("--absolute-tolerance must be non-negative")

    frame = load_table(args.data, args.sheet)
    required = {
        args.flag_column,
        args.year_column,
        *args.measure,
        *args.id_column,
    }
    if args.expected_flag_column:
        required.add(args.expected_flag_column)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SystemExit(f"Input is missing required columns: {missing}")

    output_status, output_flag = normalize_series(frame[args.flag_column])
    year_null = frame[args.year_column].isna()
    blockers: list[str] = []
    if not args.predicate_config:
        blockers.append("independent predicate config is required for a passing audit")
    if year_null.any():
        blockers.append(f"{int(year_null.sum())} row(s) have a null year")

    output_invalid = output_status.eq("invalid")
    output_null = output_status.eq("null")
    if output_invalid.any():
        blockers.append(
            f"{int(output_invalid.sum())} row(s) have an invalid output flag"
        )
    if output_null.any() and not args.allow_null_flag:
        blockers.append(f"{int(output_null.sum())} row(s) have a null output flag")

    if not args.id_column:
        id_null = pd.Series(False, index=frame.index)
    else:
        id_values = frame[args.id_column]
        id_null = id_values.isna().any(axis=1) | id_values.astype("string").apply(
            lambda column: column.str.strip().eq("")
        ).any(axis=1)
    id_duplicate = (
        pd.Series(False, index=frame.index)
        if not args.id_column
        else frame.duplicated(args.id_column, keep=False)
    )
    if id_null.any():
        blockers.append(f"{int(id_null.sum())} row(s) have an incomplete stable ID")
    if id_duplicate.any():
        blockers.append(f"{int(id_duplicate.sum())} row(s) have a duplicate stable ID")

    predicate = None
    predicate_columns: list[str] = []
    expected_source_column = args.expected_flag_column
    provided_expected_mismatch = pd.Series(False, index=frame.index)
    if args.predicate_config:
        try:
            predicate = json.loads(args.predicate_config.read_text(encoding="utf-8"))
            derived, predicate_columns = derive_expected_flag(
                frame,
                predicate,
                {args.flag_column, args.expected_flag_column, DERIVED_FLAG_COLUMN}
                - {None},
            )
        except (json.JSONDecodeError, ValueError) as exc:
            report = {
                "check": "foreign_funding",
                "passed": False,
                "data": str(args.data.resolve()),
                "predicate_config": str(args.predicate_config.resolve()),
                "blockers": [f"invalid independent predicate: {exc}"],
            }
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(json.dumps({"passed": False, "blockers": 1}))
            return 1
        frame[DERIVED_FLAG_COLUMN] = derived
        expected_source_column = DERIVED_FLAG_COLUMN
        if args.expected_flag_column:
            supplied_status, supplied_flag = normalize_series(
                frame[args.expected_flag_column]
            )
            supplied_invalid = supplied_status.eq("invalid")
            supplied_null = supplied_status.eq("null")
            if supplied_invalid.any():
                blockers.append(
                    f"{int(supplied_invalid.sum())} supplied expected flag row(s) are invalid"
                )
            if supplied_null.any() and not args.allow_null_flag:
                blockers.append(
                    f"{int(supplied_null.sum())} supplied expected flag row(s) are null"
                )
            comparable_supplied = supplied_status.eq("valid")
            provided_expected_mismatch = comparable_supplied & supplied_flag.ne(derived)
            if provided_expected_mismatch.any():
                blockers.append(
                    f"{int(provided_expected_mismatch.sum())} supplied expected flag row(s) disagree with the predicate"
                )

    expected_status = expected_flag = mismatch = None
    if expected_source_column:
        expected_status, expected_flag = normalize_series(frame[expected_source_column])
        expected_invalid = expected_status.eq("invalid")
        expected_null = expected_status.eq("null")
        if expected_invalid.any():
            blockers.append(
                f"{int(expected_invalid.sum())} row(s) have an invalid expected flag"
            )
        if expected_null.any() and not args.allow_null_flag:
            blockers.append(
                f"{int(expected_null.sum())} row(s) have a null expected flag"
            )
        comparable = output_status.eq("valid") & expected_status.eq("valid")
        mismatch = comparable & output_flag.ne(expected_flag)
        if mismatch.any():
            blockers.append(
                f"{int(mismatch.sum())} row(s) disagree with the source-derived flag"
            )

    numeric_measures: dict[str, pd.Series] = {}
    measure_quality = {}
    for measure in args.measure:
        raw = frame[measure]
        numeric = pd.to_numeric(raw, errors="coerce")
        invalid = raw.notna() & numeric.isna()
        null = raw.isna()
        numeric_measures[measure] = numeric
        measure_quality[measure] = {
            "null_rows": int(null.sum()),
            "invalid_rows": int(invalid.sum()),
        }
        if invalid.any():
            blockers.append(
                f"{int(invalid.sum())} row(s) have a non-numeric {measure} value"
            )
        if null.any() and not args.allow_null_measures:
            blockers.append(f"{int(null.sum())} row(s) have a null {measure} value")

    valid_partition = output_status.eq("valid") & ~year_null
    observed_values = sorted(set(output_flag.loc[valid_partition]))
    if args.require_both_values and observed_values != [False, True]:
        blockers.append(
            "output flag does not contain both false and true values as required"
        )

    work = pd.DataFrame(
        {
            "year": frame[args.year_column],
            "is_foreign": output_flag,
            **numeric_measures,
        },
        index=frame.index,
    )
    partition_summary = []
    for (year, flag), group in work.loc[valid_partition].groupby(
        ["year", "is_foreign"], dropna=False, sort=True
    ):
        partition_summary.append(
            {
                "year": json_value(year),
                "is_foreign": bool(flag),
                "rows": int(len(group)),
                **{
                    measure: json_value(group[measure].sum(min_count=1))
                    for measure in args.measure
                },
            }
        )

    conservation = []
    for year, all_rows in work.loc[~year_null].groupby("year", dropna=False, sort=True):
        partition_rows = all_rows[all_rows["is_foreign"].notna()]
        item = {
            "year": json_value(year),
            "all_rows": int(len(all_rows)),
            "partitioned_rows": int(len(partition_rows)),
            "row_difference": int(len(all_rows) - len(partition_rows)),
            "measures": {},
        }
        if item["row_difference"]:
            blockers.append(
                f"year {json_value(year)} has {item['row_difference']} unpartitioned row(s)"
            )
        for measure in args.measure:
            total = all_rows[measure].sum(min_count=1)
            partitioned = (
                0.0
                if partition_rows.empty
                else partition_rows[measure].sum(min_count=1)
            )
            difference = total - partitioned
            numeric_difference = None if pd.isna(difference) else float(difference)
            item["measures"][measure] = {
                "all_rows": json_value(total),
                "partitioned": json_value(partitioned),
                "difference": numeric_difference,
            }
            if (
                numeric_difference is not None
                and abs(numeric_difference) > args.absolute_tolerance
            ):
                blockers.append(
                    f"year {json_value(year)} {measure} does not conserve by "
                    f"{numeric_difference}"
                )
        conservation.append(item)

    invalid_sample = sample_rows(
        frame,
        output_invalid | output_null,
        args.id_column,
        args.flag_column,
        expected_source_column,
        args.sample_limit,
    )
    mismatch_sample = (
        []
        if mismatch is None
        else sample_rows(
            frame,
            mismatch,
            args.id_column,
            args.flag_column,
            expected_source_column,
            args.sample_limit,
        )
    )

    if args.detail_csv:
        detail = frame[args.id_column].copy()
        detail["output_flag_raw"] = frame[args.flag_column]
        detail["output_flag_status"] = output_status
        detail["output_flag_normalized"] = output_flag
        if expected_source_column:
            detail["expected_flag_raw"] = frame[expected_source_column]
            detail["expected_flag_status"] = expected_status
            detail["expected_flag_normalized"] = expected_flag
            detail["flag_mismatch"] = mismatch
        if args.predicate_config and args.expected_flag_column:
            detail["provided_expected_predicate_mismatch"] = provided_expected_mismatch
        args.detail_csv.parent.mkdir(parents=True, exist_ok=True)
        detail.to_csv(args.detail_csv, index=True, index_label="row_index")

    report = {
        "check": "foreign_funding",
        "passed": not blockers,
        "data": str(args.data.resolve()),
        "sheet": args.sheet,
        "rows": int(len(frame)),
        "flag_column": args.flag_column,
        "expected_flag_column": expected_source_column,
        "provided_expected_flag_column": args.expected_flag_column,
        "source_rule": args.source_rule or (predicate or {}).get("description"),
        "predicate_config": None
        if not args.predicate_config
        else {
            "path": str(args.predicate_config.resolve()),
            "sha256": sha256(args.predicate_config),
            "source_columns": predicate_columns,
        },
        "independent_predicate_used": predicate is not None,
        "accepted_flag_encodings": {
            "true": sorted(TRUE_VALUES),
            "false": sorted(FALSE_VALUES),
        },
        "flag_quality": {
            "valid_rows": int(output_status.eq("valid").sum()),
            "null_rows": int(output_null.sum()),
            "invalid_rows": int(output_invalid.sum()),
            "observed_boolean_values": [bool(value) for value in observed_values],
        },
        "expected_flag_quality": None
        if expected_status is None
        else {
            "valid_rows": int(expected_status.eq("valid").sum()),
            "null_rows": int(expected_status.eq("null").sum()),
            "invalid_rows": int(expected_status.eq("invalid").sum()),
            "mismatch_rows": int(mismatch.sum()),
        },
        "measure_quality": measure_quality,
        "partition_summary": partition_summary,
        "conservation": conservation,
        "invalid_or_null_flag_sample": invalid_sample,
        "mismatch_sample": mismatch_sample,
        "provided_expected_predicate_mismatch_rows": int(
            provided_expected_mismatch.sum()
        ),
        "blockers": blockers,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "rows": report["rows"],
                "mismatch_rows": 0 if mismatch is None else int(mismatch.sum()),
                "blockers": len(blockers),
            }
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
