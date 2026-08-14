#!/usr/bin/env python3
"""Apply an explicit formula manifest to a new XLSX copy without recalculation."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"x": MAIN, "r": DOC_REL, "p": PKG_REL, "ct": CT}
ET.register_namespace("", MAIN)
ET.register_namespace("r", DOC_REL)


def q(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def normalize_target(target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return str(PurePosixPath("xl/workbook.xml").parent.joinpath(target))


def sheet_paths(workbook_xml: bytes, rels_xml: bytes) -> dict[str, str]:
    workbook = ET.fromstring(workbook_xml)
    rels = ET.fromstring(rels_xml)
    targets = {
        rel.attrib["Id"]: normalize_target(rel.attrib["Target"])
        for rel in rels.findall("p:Relationship", NS)
    }
    return {
        sheet.attrib["name"]: targets[sheet.attrib[q(DOC_REL, "id")]]
        for sheet in workbook.findall("x:sheets/x:sheet", NS)
    }


def normalized_formula(value: str | None) -> str | None:
    if value is None:
        return None
    return "=" + value.lstrip("=")


def numeric_text(value: object) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return format(float(value), ".15g")


def patch_sheet(xml: bytes, records: list[dict], allow_old_mismatch: bool) -> bytes:
    root = ET.fromstring(xml)
    cells = {cell.attrib.get("r"): cell for cell in root.findall(".//x:c", NS)}
    for record in records:
        ref = record["cell"]
        if not re.fullmatch(r"[A-Z]+[1-9][0-9]*", ref):
            raise ValueError(f"Invalid cell reference {ref!r}")
        cell = cells.get(ref)
        if cell is None:
            raise ValueError(
                f"Refusing to create missing cell {ref}; formula rewrites must target existing cells"
            )
        formula = cell.find("x:f", NS)
        actual_old = normalized_formula(None if formula is None else formula.text)
        expected_old = normalized_formula(record.get("old_formula"))
        if expected_old is None:
            raise ValueError(
                f"Patch {record.get('sheet')}!{ref} is missing old_formula"
            )
        if actual_old != expected_old and not allow_old_mismatch:
            raise ValueError(
                f"Old formula mismatch at {record.get('sheet')}!{ref}: "
                f"manifest={expected_old!r}, workbook={actual_old!r}"
            )
        new_formula = normalized_formula(record.get("new_formula"))
        if new_formula is None or new_formula == "=":
            raise ValueError(
                f"Patch {record.get('sheet')}!{ref} is missing new_formula"
            )
        cell.attrib.pop("t", None)
        for child in list(cell):
            if child.tag in {q(MAIN, "f"), q(MAIN, "v"), q(MAIN, "is")}:
                cell.remove(child)
        new_node = ET.Element(q(MAIN, "f"))
        new_node.text = new_formula[1:]
        cell.insert(0, new_node)
        if record.get("expected_after") is not None:
            cached = ET.Element(q(MAIN, "v"))
            cached.text = numeric_text(record["expected_after"])
            cell.insert(1, cached)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def validate_records(records: object) -> list[dict]:
    if not isinstance(records, list) or not records:
        raise ValueError("Patch manifest must be a non-empty JSON list")
    seen = set()
    required = {"sheet", "cell", "old_formula", "new_formula", "reason"}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Every patch record must be an object")
        missing = sorted(required - set(record))
        if missing:
            raise ValueError(f"Patch record is missing {missing}: {record}")
        key = (record["sheet"], record["cell"])
        if key in seen:
            raise ValueError(f"Duplicate patch target {key[0]}!{key[1]}")
        seen.add(key)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--patches", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-old-mismatch", action="store_true")
    args = parser.parse_args()

    if args.base.suffix.lower() != ".xlsx" or args.output.suffix.lower() != ".xlsx":
        raise SystemExit(
            "Only .xlsx input and output are supported; preserve macro-enabled files separately"
        )
    if args.base.resolve() == args.output.resolve():
        raise SystemExit("Refusing to overwrite the base workbook")
    records = validate_records(json.loads(args.patches.read_text(encoding="utf-8")))
    by_sheet: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        by_sheet[record["sheet"]].append(record)

    with zipfile.ZipFile(args.base) as source:
        bad = source.testzip()
        if bad:
            raise ValueError(f"Corrupt base workbook member: {bad}")
        payloads = {name: source.read(name) for name in source.namelist()}

    workbook_name = "xl/workbook.xml"
    rels_name = "xl/_rels/workbook.xml.rels"
    content_types_name = "[Content_Types].xml"
    paths = sheet_paths(payloads[workbook_name], payloads[rels_name])
    missing_sheets = sorted(set(by_sheet) - set(paths))
    if missing_sheets:
        raise ValueError(f"Patch sheets not found: {missing_sheets}")
    for sheet_name, sheet_records in by_sheet.items():
        sheet_path = paths[sheet_name]
        payloads[sheet_path] = patch_sheet(
            payloads[sheet_path], sheet_records, args.allow_old_mismatch
        )

    workbook = ET.fromstring(payloads[workbook_name])
    calc = workbook.find("x:calcPr", NS)
    if calc is None:
        calc = ET.SubElement(workbook, q(MAIN, "calcPr"))
    calc.attrib.update(
        {"calcMode": "auto", "fullCalcOnLoad": "1", "forceFullCalc": "1"}
    )
    payloads[workbook_name] = ET.tostring(
        workbook, encoding="utf-8", xml_declaration=True
    )

    rels = ET.fromstring(payloads[rels_name])
    removed_targets = []
    for rel in list(rels):
        if rel.attrib.get("Type", "").endswith("/calcChain"):
            removed_targets.append(normalize_target(rel.attrib.get("Target", "")))
            rels.remove(rel)
    payloads[rels_name] = ET.tostring(rels, encoding="utf-8", xml_declaration=True)
    for target in removed_targets:
        payloads.pop(target, None)
    payloads.pop("xl/calcChain.xml", None)

    content_types = ET.fromstring(payloads[content_types_name])
    for override in list(content_types):
        if override.attrib.get("PartName") == "/xl/calcChain.xml":
            content_types.remove(override)
    payloads[content_types_name] = ET.tostring(
        content_types, encoding="utf-8", xml_declaration=True
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        args.output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as target:
        for name, data in payloads.items():
            target.writestr(name, data)

    with zipfile.ZipFile(args.output) as check:
        bad = check.testzip()
        if bad:
            raise ValueError(f"Corrupt output workbook member: {bad}")
    print(
        json.dumps(
            {
                "base": str(args.base),
                "output": str(args.output),
                "patched_formulas": len(records),
                "recalculation": "requested_on_open_not_executed",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
