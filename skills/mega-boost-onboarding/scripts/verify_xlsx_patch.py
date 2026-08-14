#!/usr/bin/env python3
"""Verify that an XLSX formula patch changed only intended workbook parts."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from patch_xlsx_formulas import NS, sheet_paths


ALWAYS_ALLOWED = {
    "xl/workbook.xml",
    "xl/_rels/workbook.xml.rels",
    "[Content_Types].xml",
    "xl/calcChain.xml",
}


def formulas_and_styles(xml: bytes) -> dict[str, dict]:
    root = ET.fromstring(xml)
    result = {}
    for cell in root.findall(".//x:c", NS):
        formula = cell.find("x:f", NS)
        value = cell.find("x:v", NS)
        result[cell.attrib["r"]] = {
            "formula": None if formula is None else "=" + (formula.text or ""),
            "cached": None if value is None else value.text,
            "style": cell.attrib.get("s"),
            "type": cell.attrib.get("t"),
        }
    return result


def load_payloads(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Corrupt workbook member in {path}: {bad}")
        return {name: archive.read(name) for name in archive.namelist()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--patches", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    records = json.loads(args.patches.read_text(encoding="utf-8"))
    base = load_payloads(args.base)
    output = load_payloads(args.output)
    workbook_name = "xl/workbook.xml"
    rels_name = "xl/_rels/workbook.xml.rels"
    base_paths = sheet_paths(base[workbook_name], base[rels_name])
    out_paths = sheet_paths(output[workbook_name], output[rels_name])
    target_sheet_paths = {out_paths[record["sheet"]] for record in records}

    issues: list[str] = []
    all_members = set(base) | set(output)
    changed = sorted(name for name in all_members if base.get(name) != output.get(name))
    allowed = ALWAYS_ALLOWED | target_sheet_paths
    unexpected = sorted(set(changed) - allowed)
    if unexpected:
        issues.append(f"unexpected changed archive members: {unexpected}")

    base_cells = {
        name: formulas_and_styles(base[path])
        for name, path in base_paths.items()
        if path in base
    }
    out_cells = {
        name: formulas_and_styles(output[path])
        for name, path in out_paths.items()
        if path in output
    }
    target_keys = {(record["sheet"], record["cell"]) for record in records}
    for record in records:
        key = (record["sheet"], record["cell"])
        before = base_cells.get(key[0], {}).get(key[1])
        after = out_cells.get(key[0], {}).get(key[1])
        if before is None or after is None:
            issues.append(f"missing target cell {key[0]}!{key[1]}")
            continue
        if before["formula"] != record["old_formula"]:
            issues.append(f"base old_formula mismatch at {key[0]}!{key[1]}")
        if after["formula"] != record["new_formula"]:
            issues.append(f"output new_formula mismatch at {key[0]}!{key[1]}")
        if before["style"] != after["style"]:
            issues.append(f"style changed at {key[0]}!{key[1]}")

    unexpected_cells = []
    for sheet in sorted(set(base_cells) & set(out_cells)):
        for ref in sorted(set(base_cells[sheet]) | set(out_cells[sheet])):
            if (sheet, ref) in target_keys:
                continue
            if base_cells[sheet].get(ref) != out_cells[sheet].get(ref):
                unexpected_cells.append(f"{sheet}!{ref}")
                if len(unexpected_cells) >= 50:
                    break
    if unexpected_cells:
        issues.append(f"unexpected changed cells: {unexpected_cells}")

    workbook = ET.fromstring(output[workbook_name])
    calc = workbook.find("x:calcPr", NS)
    calc_ok = calc is not None and all(
        calc.attrib.get(key) == value
        for key, value in {
            "calcMode": "auto",
            "fullCalcOnLoad": "1",
            "forceFullCalc": "1",
        }.items()
    )
    if not calc_ok:
        issues.append("output does not request automatic full recalculation")
    if "xl/calcChain.xml" in output:
        issues.append("stale xl/calcChain.xml remains")

    report = {
        "passed": not issues,
        "base": str(args.base),
        "output": str(args.output),
        "patch_count": len(records),
        "changed_archive_members": changed,
        "unexpected_changed_members": unexpected,
        "unexpected_changed_cells": unexpected_cells,
        "calc_mode_auto_full_recalc": calc_ok,
        "issues": issues,
        "note": "Cached formula values are not proof of spreadsheet-engine recalculation.",
    }
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
