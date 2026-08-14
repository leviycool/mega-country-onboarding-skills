#!/usr/bin/env python3
"""Detect same-depth BOOST tag overlaps from structured formula rules."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import pandas as pd


LEVELS = ("econ", "econ_sub", "func", "func_sub")


def is_null(value: object) -> bool:
    return (
        value is None or value == "" or (isinstance(value, float) and math.isnan(value))
    )


def read_records(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def load_input(cfg: dict) -> pd.DataFrame:
    path = Path(cfg["input"])
    kind = cfg.get("format") or path.suffix.lower().lstrip(".")
    if kind == "csv":
        return pd.read_csv(path, low_memory=False)
    if kind in {"xlsx", "xlsm"}:
        if not cfg.get("sheet"):
            raise ValueError(f"Range {cfg['name']} requires sheet for Excel input")
        return pd.read_excel(path, sheet_name=cfg["sheet"])
    if kind == "parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported input format {kind!r} for {path}")


def dispatches(measure: str, cfg: dict) -> bool:
    if measure in cfg.get("measure_dispatch", []):
        return True
    return any(
        re.search(pattern, measure or "") for pattern in cfg.get("measure_patterns", [])
    )


def parse_years(value: str | None) -> set[str]:
    if not value:
        return set()
    text = str(value)
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", text))
    for start, end in re.findall(r"((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2})", text):
        years.update(str(year) for year in range(int(start), int(end) + 1))
    return years


def normalize_groups(raw: object) -> list[list[dict]]:
    if not isinstance(raw, list):
        raise ValueError("criteria_json must decode to a list")
    if not raw:
        return []
    if all(isinstance(item, dict) for item in raw):
        return [raw]
    if all(isinstance(item, list) for item in raw):
        return raw
    raise ValueError("criteria_json must be a list of criteria or a list of branches")


def compare(series: pd.Series, op: str, value: object) -> pd.Series:
    if isinstance(value, list):
        masks = [compare(series, "=", item) for item in value]
        result = pd.Series(False, index=series.index)
        for mask in masks:
            result |= mask
        return ~result if op == "<>" else result
    text = "" if value is None else str(value)
    if op in {"=", "<>"}:
        if "*" in text or "?" in text:
            pattern = (
                "^" + re.escape(text).replace(r"\*", ".*").replace(r"\?", ".") + "$"
            )
            equal = (
                series.fillna("").astype(str).str.match(pattern, case=False, na=False)
            )
        else:
            equal = series.fillna("").astype(str).str.casefold() == text.casefold()
        return ~equal if op == "<>" else equal
    numeric = pd.to_numeric(series, errors="coerce")
    target = float(text)
    return {
        "<": numeric < target,
        "<=": numeric <= target,
        ">": numeric > target,
        ">=": numeric >= target,
    }[op]


def rule_mask(
    df: pd.DataFrame,
    rule: dict,
    field_map: dict[str, str],
) -> tuple[pd.Series, list[dict], list[pd.Series]]:
    groups = normalize_groups(json.loads(rule["criteria_json"]))
    combined = pd.Series(False, index=df.index)
    unsupported: list[dict] = []
    supported_masks: list[pd.Series] = []
    if not groups:
        return (
            combined,
            [{"branch": None, "issues": [{"reason": "empty_criteria"}]}],
            [],
        )
    for branch_index, branch in enumerate(groups):
        branch_mask = pd.Series(True, index=df.index)
        branch_issues = []
        for criterion in branch:
            op = criterion.get("op", "=")
            if op == "=year":
                continue
            field = criterion.get("field")
            column = field_map.get(field)
            if not column or column not in df.columns:
                branch_issues.append(
                    {"field": field, "reason": "unmapped_or_missing_column"}
                )
                continue
            if op not in {"=", "<>", "<", "<=", ">", ">="}:
                branch_issues.append(
                    {"field": field, "op": op, "reason": "unsupported_operator"}
                )
                continue
            try:
                branch_mask &= compare(df[column], op, criterion.get("value"))
            except (TypeError, ValueError) as exc:
                branch_issues.append({"field": field, "op": op, "reason": str(exc)})
        if branch_issues:
            unsupported.append({"branch": branch_index, "issues": branch_issues})
            continue
        supported_masks.append(branch_mask)
        combined |= branch_mask

    years = parse_years(rule.get("years_covered"))
    year_column = field_map.get("year")
    if years and (not year_column or year_column not in df.columns):
        unsupported.append(
            {
                "branch": None,
                "issues": [{"reason": "year_column_unmapped_or_missing"}],
            }
        )
    elif years:
        normalized_year = (
            pd.to_numeric(df[year_column], errors="coerce")
            .astype("Int64")
            .astype("string")
        )
        year_mask = normalized_year.isin(years)
        combined &= year_mask
        supported_masks = [mask & year_mask for mask in supported_masks]
    return combined, unsupported, supported_masks


def subnational(code: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, code) for pattern in patterns)


def level_membership(row: dict) -> list[tuple[str, str]]:
    result = []
    if not is_null(row.get("econ")):
        if is_null(row.get("econ_sub")):
            result.append(("econ", str(row["econ"])))
        else:
            result.append(("econ_sub", str(row["econ_sub"])))
    if not is_null(row.get("func")):
        if is_null(row.get("func_sub")):
            result.append(("func", str(row["func"])))
        else:
            result.append(("func_sub", str(row["func_sub"])))
    return result


def candidate_groups(
    code_rows: dict[str, dict], patterns: list[str]
) -> dict[tuple, list[tuple[str, str]]]:
    groups: dict[tuple, list[tuple[str, str]]] = defaultdict(list)
    for code, row in code_rows.items():
        scope = "subnational" if subnational(code, patterns) else "primary"
        kind = row.get("tag_kind") or ""
        for level, value in level_membership(row):
            groups[(scope, kind, level)].append((code, value))
    return groups


def combine_rules(
    df: pd.DataFrame,
    rules: list[dict],
    field_map: dict[str, str],
    measures: list[str],
    range_name: str,
    stage: str,
) -> tuple[dict[str, pd.Series], list[dict], dict[str, dict], list[dict]]:
    masks: dict[str, pd.Series] = {}
    coverage: list[dict] = []
    samples: dict[str, dict] = {}
    self_doubles: list[dict] = []
    for rule in rules:
        code = rule["code"]
        try:
            mask, unsupported, supported_masks = rule_mask(df, rule, field_map)
        except (json.JSONDecodeError, ValueError) as exc:
            coverage.append({"code": code, "status": "UNSUPPORTED", "reason": str(exc)})
            continue
        if code not in masks:
            masks[code] = pd.Series(False, index=df.index)
        masks[code] |= mask
        samples.setdefault(code, rule)
        coverage.append(
            {
                "code": code,
                "status": "SUPPORTED" if not unsupported else "PARTIAL",
                "stage": stage,
                "supported_branches": len(supported_masks),
                "unsupported_branches": unsupported,
                "matched_rows": int(mask.sum()),
            }
        )
        if len(supported_masks) > 1:
            membership = sum(
                (branch_mask.astype(int) for branch_mask in supported_masks),
                start=pd.Series(0, index=df.index),
            )
            affected = membership.gt(1)
            if affected.any():
                values = {
                    measure: pd.to_numeric(df[measure], errors="coerce").fillna(0)
                    for measure in measures
                }
                self_doubles.append(
                    {
                        "range": range_name,
                        "stage": stage,
                        "code": code,
                        "formula_cell": rule.get("formula_cell"),
                        "sample_formula": rule.get("sample_formula"),
                        "rows": int(affected.sum()),
                        "max_branch_memberships": int(membership[affected].max()),
                        "measures": {
                            measure: {
                                "affected_exposure": float(
                                    values[measure][affected].sum()
                                ),
                                "net_excess": float(
                                    (
                                        values[measure] * (membership - 1).clip(lower=0)
                                    ).sum()
                                ),
                            }
                            for measure in measures
                        },
                    }
                )
    return masks, coverage, samples, self_doubles


def as_number(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def pair_records(
    df: pd.DataFrame,
    masks: dict[str, pd.Series],
    samples: dict[str, dict],
    code_rows: dict[str, dict],
    groups: dict[tuple, list[tuple[str, str]]],
    measures: list[str],
    range_name: str,
    year_column: str | None,
    stage: str,
) -> list[dict]:
    numeric = {
        measure: pd.to_numeric(df[measure], errors="coerce").fillna(0)
        for measure in measures
    }
    records = []
    for (scope, kind, level), entries in sorted(groups.items()):
        available = [(code, value) for code, value in entries if code in masks]
        for (code_a, value_a), (code_b, value_b) in combinations(sorted(available), 2):
            intersection = masks[code_a] & masks[code_b]
            if not intersection.any():
                continue
            totals = {}
            for measure in measures:
                totals[measure] = {
                    "code_a": float(numeric[measure][masks[code_a]].sum()),
                    "code_b": float(numeric[measure][masks[code_b]].sum()),
                    "overlap": float(numeric[measure][intersection].sum()),
                }
                denominator = min(
                    abs(totals[measure]["code_a"]), abs(totals[measure]["code_b"])
                )
                totals[measure]["overlap_ratio_to_smaller"] = (
                    None
                    if denominator == 0
                    else totals[measure]["overlap"] / denominator
                )
            by_year = []
            if year_column and year_column in df.columns:
                temp = pd.DataFrame({"year": df[year_column], "_overlap": intersection})
                for measure in measures:
                    temp[measure] = numeric[measure]
                for year, part in temp[temp["_overlap"]].groupby("year", dropna=False):
                    by_year.append(
                        {
                            "year": None if pd.isna(year) else str(year),
                            "rows": int(len(part)),
                            "measures": {
                                measure: float(part[measure].sum())
                                for measure in measures
                            },
                        }
                    )
            sample_a, sample_b = samples.get(code_a, {}), samples.get(code_b, {})
            records.append(
                {
                    "range": range_name,
                    "stage": stage,
                    "scope": scope,
                    "tag_kind": kind,
                    "level": level,
                    "code_a": code_a,
                    "code_b": code_b,
                    "value_a": value_a,
                    "value_b": value_b,
                    "relationship": "same_value_duplicate"
                    if value_a == value_b
                    else "cross_category",
                    "rows": int(intersection.sum()),
                    "totals": totals,
                    "by_year": by_year,
                    "formula_a": sample_a.get("sample_formula"),
                    "formula_b": sample_b.get("sample_formula"),
                    "category_a": sample_a.get("category"),
                    "category_b": sample_b.get("category"),
                }
            )
    return records


def net_excess_records(
    df: pd.DataFrame,
    masks: dict[str, pd.Series],
    groups: dict[tuple, list[tuple[str, str]]],
    measures: list[str],
    range_name: str,
    year_column: str | None,
    stage: str,
) -> list[dict]:
    results = []
    years = [(None, pd.Series(True, index=df.index))]
    if year_column and year_column in df.columns:
        years = [
            (None if pd.isna(year) else str(year), df[year_column].eq(year))
            for year in df[year_column].drop_duplicates().tolist()
        ]
    for (scope, kind, level), entries in sorted(groups.items()):
        codes = sorted({code for code, _ in entries if code in masks})
        if len(codes) < 2:
            continue
        membership = sum(
            (masks[code].astype(int) for code in codes),
            start=pd.Series(0, index=df.index),
        )
        for year, year_mask in years:
            affected = year_mask & membership.gt(1)
            if not affected.any():
                continue
            result = {
                "range": range_name,
                "stage": stage,
                "scope": scope,
                "tag_kind": kind,
                "level": level,
                "year": year,
                "unique_affected_rows": int(affected.sum()),
                "max_memberships": int(membership[affected].max()),
                "measures": {},
            }
            for measure in measures:
                values = pd.to_numeric(df[measure], errors="coerce").fillna(0)
                result["measures"][measure] = {
                    "unique_affected_exposure": float(values[affected].sum()),
                    "net_excess": float(
                        (
                            values
                            * (membership - 1).clip(lower=0)
                            * year_mask.astype(int)
                        ).sum()
                    ),
                }
            results.append(result)
    return results


def write_detail_csv(records: list[dict], path: Path) -> None:
    rows = []
    for record in records:
        if record["by_year"]:
            year_rows = record["by_year"]
        else:
            year_rows = [{"year": None, "rows": record["rows"], "measures": {}}]
        for year in year_rows:
            base = {
                key: record[key]
                for key in (
                    "range",
                    "stage",
                    "scope",
                    "tag_kind",
                    "level",
                    "code_a",
                    "code_b",
                    "value_a",
                    "value_b",
                    "relationship",
                )
            }
            base.update({"year": year["year"], "rows": year["rows"]})
            for measure, value in year.get("measures", {}).items():
                base[f"{measure}_overlap"] = value
            rows.append(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--tag-rules", type=Path, required=True)
    parser.add_argument("--code-dictionary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--detail-csv", type=Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    rules = read_records(args.tag_rules)
    code_records = read_records(args.code_dictionary)
    code_values = [row.get("code") for row in code_records]
    duplicate_dictionary_codes = sorted(
        code for code in set(code_values) if code and code_values.count(code) > 1
    )
    code_rows = {row["code"]: row for row in code_records if row.get("code")}
    patterns = config.get("subnational_code_patterns", ["_SBN_", "^SBN_"])
    groups = candidate_groups(code_rows, patterns)
    stages = config.get("expected_stages")
    if (
        not isinstance(stages, list)
        or not stages
        or not all(isinstance(stage, str) and stage.strip() for stage in stages)
    ):
        raise SystemExit("Config requires a non-empty expected_stages list")
    if len({stage.casefold() for stage in stages}) != len(stages):
        raise SystemExit("expected_stages contains duplicate stage names")
    expected_codes_by_stage = config.get("expected_codes_by_stage")
    if not isinstance(expected_codes_by_stage, dict):
        raise SystemExit("Config requires expected_codes_by_stage")
    minimum_rules = int(config.get("minimum_rules_per_stage", 1))
    if minimum_rules < 1:
        raise SystemExit("minimum_rules_per_stage must be at least 1")

    all_pairs, all_excess, all_coverage, range_summaries = [], [], [], []
    all_self_doubles, coverage_issues = [], []
    if duplicate_dictionary_codes:
        coverage_issues.append(
            f"code dictionary contains duplicate codes: {duplicate_dictionary_codes}"
        )
    for stage in stages:
        expected_codes = expected_codes_by_stage.get(stage)
        if not isinstance(expected_codes, list) or not expected_codes:
            coverage_issues.append(
                f"stage {stage} requires a non-empty expected code list"
            )
            expected_codes = []
        duplicate_expected = sorted(
            code for code in set(expected_codes) if expected_codes.count(code) > 1
        )
        if duplicate_expected:
            coverage_issues.append(
                f"stage {stage} repeats expected codes: {duplicate_expected}"
            )
        for range_cfg in config["ranges"]:
            df = load_input(range_cfg)
            missing_measures = sorted(set(range_cfg["measures"]) - set(df.columns))
            if missing_measures:
                raise ValueError(
                    f"Range {range_cfg['name']} missing measure columns {missing_measures}"
                )
            selected = [
                rule
                for rule in rules
                if rule.get("row_type", "TAG") == "TAG"
                and rule.get("sheet", stage).casefold() == stage.casefold()
                and dispatches(rule.get("measure", ""), range_cfg)
                and rule.get("code") in code_rows
            ]
            selected_codes = sorted({rule.get("code") for rule in selected})
            missing_codes = sorted(set(expected_codes) - set(selected_codes))
            unexpected_codes = sorted(set(selected_codes) - set(expected_codes))
            if len(selected) < minimum_rules:
                coverage_issues.append(
                    f"stage {stage} range {range_cfg['name']} selected {len(selected)} rules; expected at least {minimum_rules}"
                )
            if missing_codes:
                coverage_issues.append(
                    f"stage {stage} range {range_cfg['name']} missing expected codes: {missing_codes}"
                )
            if unexpected_codes:
                coverage_issues.append(
                    f"stage {stage} range {range_cfg['name']} has uncontracted codes: {unexpected_codes}"
                )
            masks, coverage, samples, self_doubles = combine_rules(
                df,
                selected,
                range_cfg["field_map"],
                range_cfg["measures"],
                range_cfg["name"],
                stage,
            )
            for item in coverage:
                item["range"] = range_cfg["name"]
            all_coverage.extend(coverage)
            all_self_doubles.extend(self_doubles)
            year_column = range_cfg["field_map"].get("year")
            pairs = pair_records(
                df,
                masks,
                samples,
                code_rows,
                groups,
                range_cfg["measures"],
                range_cfg["name"],
                year_column,
                stage,
            )
            excess = net_excess_records(
                df,
                masks,
                groups,
                range_cfg["measures"],
                range_cfg["name"],
                year_column,
                stage,
            )
            all_pairs.extend(pairs)
            all_excess.extend(excess)
            range_summaries.append(
                {
                    "range": range_cfg["name"],
                    "stage": stage,
                    "rows": int(len(df)),
                    "selected_rules": len(selected),
                    "expected_codes": expected_codes,
                    "selected_codes": selected_codes,
                    "missing_expected_codes": missing_codes,
                    "unexpected_codes": unexpected_codes,
                    "codes_with_masks": len(masks),
                    "overlap_pairs": len(pairs),
                    "within_formula_self_doubles": len(self_doubles),
                    "net_excess_groups": len(excess),
                }
            )

    partial_or_unsupported = [
        item for item in all_coverage if item.get("status") != "SUPPORTED"
    ]
    report = {
        "check": "overcounting",
        "country": config.get("country"),
        "expected_stages": stages,
        "passed": not all_pairs
        and not all_self_doubles
        and not partial_or_unsupported
        and not coverage_issues,
        "range_summaries": range_summaries,
        "pairwise_overlaps": all_pairs,
        "dimension_year_net_excess": all_excess,
        "within_formula_self_doubles": all_self_doubles,
        "parser_coverage": all_coverage,
        "unresolved_parser_coverage": partial_or_unsupported,
        "coverage_issues": coverage_issues,
        "method_note": "Do not sum pairwise overlap amounts; use dimension_year_net_excess for total excess.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if args.detail_csv:
        write_detail_csv(all_pairs, args.detail_csv)
    print(
        json.dumps(
            {
                "country": report["country"],
                "passed": report["passed"],
                "overlap_pairs": len(all_pairs),
                "net_excess_groups": len(all_excess),
                "within_formula_self_doubles": len(all_self_doubles),
                "unresolved_parser_records": len(partial_or_unsupported),
                "coverage_issues": len(coverage_issues),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
