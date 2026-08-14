#!/usr/bin/env python3
"""Inventory an OOXML workbook without recalculating or mutating it."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CELL_RE = re.compile(r"([A-Z]+)(\d+)$")
FUNCTION_RE = re.compile(r"\b([A-Z][A-Z0-9_.]*)\s*\(", re.IGNORECASE)
VOLATILE = {"INDIRECT", "OFFSET", "NOW", "TODAY", "RAND", "RANDBETWEEN", "CELL", "INFO"}


def q(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_target(base: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return str(PurePosixPath(base).parent.joinpath(target))


def relationship_map(archive: zipfile.ZipFile, path: str, base: str) -> dict[str, str]:
    if path not in archive.namelist():
        return {}
    root = ET.fromstring(archive.read(path))
    return {
        rel.attrib["Id"]: normalize_target(base, rel.attrib["Target"])
        for rel in root.findall(q(PKG_REL, "Relationship"))
    }


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []
    root = ET.fromstring(archive.read(path))
    return [
        "".join(node.text or "" for node in item.iter(q(MAIN, "t"))) for item in root
    ]


def cell_value(cell: ET.Element, strings: list[str]) -> object:
    kind = cell.attrib.get("t")
    value = cell.find(q(MAIN, "v"))
    if kind == "inlineStr":
        inline = cell.find(q(MAIN, "is"))
        return (
            ""
            if inline is None
            else "".join(n.text or "" for n in inline.iter(q(MAIN, "t")))
        )
    if value is None or value.text is None:
        return None
    if kind == "s":
        index = int(value.text)
        return strings[index] if 0 <= index < len(strings) else value.text
    if kind == "b":
        return value.text == "1"
    return value.text


def inspect_sheet(
    archive: zipfile.ZipFile,
    path: str,
    strings: list[str],
    suspect_limit: int,
) -> dict:
    formula_rows: Counter[int] = Counter()
    formula_cols: Counter[str] = Counter()
    numeric_cells: list[tuple[str, str]] = []
    function_counts: Counter[str] = Counter()
    volatile_cells: list[dict] = []
    error_cells: list[dict] = []
    formula_count = cell_count = row_count = 0
    min_row = min_col = None
    max_row = max_col = 0

    with archive.open(path) as stream:
        for _, cell in ET.iterparse(stream, events=("end",)):
            if cell.tag != q(MAIN, "c"):
                continue
            ref = cell.attrib.get("r", "")
            match = CELL_RE.fullmatch(ref)
            if not match:
                cell.clear()
                continue
            col, row_text = match.groups()
            row = int(row_text)
            col_number = 0
            for char in col:
                col_number = col_number * 26 + ord(char) - 64
            cell_count += 1
            min_row = row if min_row is None else min(min_row, row)
            min_col = col_number if min_col is None else min(min_col, col_number)
            max_row, max_col = max(max_row, row), max(max_col, col_number)

            formula = cell.find(q(MAIN, "f"))
            value = cell_value(cell, strings)
            if formula is not None:
                formula_count += 1
                formula_rows[row] += 1
                formula_cols[col] += 1
                formula_text = formula.text or ""
                functions = [
                    name.upper().split(".")[-1]
                    for name in FUNCTION_RE.findall(formula_text)
                ]
                function_counts.update(functions)
                hit = sorted(set(functions) & VOLATILE)
                if hit and len(volatile_cells) < suspect_limit:
                    volatile_cells.append(
                        {"cell": ref, "functions": hit, "formula": formula_text}
                    )
            if cell.attrib.get("t") == "e" and len(error_cells) < suspect_limit:
                error_cells.append(
                    {"cell": ref, "value": value, "has_formula": formula is not None}
                )
            elif (
                formula is None
                and cell.attrib.get("t") in {None, "n"}
                and value not in (None, "")
            ):
                try:
                    float(str(value))
                except ValueError:
                    pass
                else:
                    numeric_cells.append((ref, col))
            cell.clear()

    row_count = max_row if max_row else 0
    dense_formula_cols = {col for col, count in formula_cols.items() if count >= 3}
    suspects = [
        {"cell": ref, "reason": "numeric constant in a formula-bearing row or column"}
        for ref, col in numeric_cells
        if formula_rows[int(CELL_RE.fullmatch(ref).group(2))] >= 2
        or col in dense_formula_cols
    ][:suspect_limit]
    return {
        "path": path,
        "used_range": {
            "min_row": min_row,
            "max_row": max_row or None,
            "min_col_number": min_col,
            "max_col_number": max_col or None,
        },
        "row_extent": row_count,
        "cell_count": cell_count,
        "formula_count": formula_count,
        "formula_functions": dict(function_counts.most_common()),
        "volatile_formula_cells": volatile_cells,
        "error_cells": error_cells,
        "hardcoded_numeric_suspects": suspects,
        "hardcoded_suspects_truncated": len(suspects) == suspect_limit,
    }


def inventory(path: Path, suspect_limit: int) -> dict:
    with zipfile.ZipFile(path) as archive:
        archive.testzip()
        names = set(archive.namelist())
        workbook_path = "xl/workbook.xml"
        workbook = ET.fromstring(archive.read(workbook_path))
        rels = relationship_map(archive, "xl/_rels/workbook.xml.rels", workbook_path)
        strings = shared_strings(archive)

        sheets = []
        sheets_node = workbook.find(q(MAIN, "sheets"))
        for position, sheet in enumerate(
            [] if sheets_node is None else list(sheets_node), start=1
        ):
            rel_id = sheet.attrib[q(DOC_REL, "id")]
            sheet_path = rels.get(rel_id)
            base = {
                "position": position,
                "name": sheet.attrib["name"],
                "state": sheet.attrib.get("state", "visible"),
                "relationship_id": rel_id,
            }
            if not sheet_path or sheet_path not in names:
                base["error"] = f"worksheet target missing: {sheet_path}"
            else:
                base.update(inspect_sheet(archive, sheet_path, strings, suspect_limit))
            sheets.append(base)

        defined_names = []
        names_node = workbook.find(q(MAIN, "definedNames"))
        for item in [] if names_node is None else list(names_node):
            defined_names.append(
                {
                    "name": item.attrib.get("name"),
                    "local_sheet_id": item.attrib.get("localSheetId"),
                    "hidden": item.attrib.get("hidden") == "1",
                    "refers_to": item.text or "",
                    "broken_reference": "#REF!" in (item.text or ""),
                }
            )

        calc = workbook.find(q(MAIN, "calcPr"))
        return {
            "file": str(path.resolve()),
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "format": path.suffix.lower(),
            "macro_enabled": "xl/vbaProject.bin" in names,
            "calculation": {} if calc is None else dict(calc.attrib),
            "external_link_members": sorted(
                name
                for name in names
                if re.fullmatch(r"xl/externalLinks/externalLink\d+\.xml", name)
            ),
            "defined_names": defined_names,
            "broken_defined_name_count": sum(
                item["broken_reference"] for item in defined_names
            ),
            "sheets": sheets,
        }


def write_sheet_csv(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "position",
        "name",
        "state",
        "row_extent",
        "cell_count",
        "formula_count",
        "volatile_formula_count",
        "error_cell_count",
        "hardcoded_numeric_suspect_count",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for sheet in report["sheets"]:
            writer.writerow(
                {
                    "position": sheet.get("position"),
                    "name": sheet.get("name"),
                    "state": sheet.get("state"),
                    "row_extent": sheet.get("row_extent"),
                    "cell_count": sheet.get("cell_count"),
                    "formula_count": sheet.get("formula_count"),
                    "volatile_formula_count": len(
                        sheet.get("volatile_formula_cells", [])
                    ),
                    "error_cell_count": len(sheet.get("error_cells", [])),
                    "hardcoded_numeric_suspect_count": len(
                        sheet.get("hardcoded_numeric_suspects", [])
                    ),
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--json", type=Path, required=True, dest="json_path")
    parser.add_argument("--sheet-csv", type=Path)
    parser.add_argument("--suspect-limit", type=int, default=200)
    args = parser.parse_args()
    if args.workbook.suffix.lower() not in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        raise SystemExit(
            "This inventory reads OOXML workbooks only; convert ODS for formula inspection"
        )
    report = inventory(args.workbook, args.suspect_limit)
    args.json_path.parent.mkdir(parents=True, exist_ok=True)
    args.json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if args.sheet_csv:
        write_sheet_csv(report, args.sheet_csv)
    summary = {
        "file": report["file"],
        "sheets": len(report["sheets"]),
        "hidden_sheets": sum(sheet["state"] != "visible" for sheet in report["sheets"]),
        "formulas": sum(sheet.get("formula_count", 0) for sheet in report["sheets"]),
        "defined_names": len(report["defined_names"]),
        "broken_defined_names": report["broken_defined_name_count"],
        "external_links": len(report["external_link_members"]),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
