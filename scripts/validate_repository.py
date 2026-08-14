#!/usr/bin/env python3
"""Validate the public MEGA country-onboarding skill repository."""

from __future__ import annotations

import json
import re
import runpy
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
EXPECTED_GATE_ORDER = (
    "intake",
    "workbook_audit",
    "subnational_scope",
    "workbook_duplicates",
    "overcounting",
    "foreign_funding",
    "boost_etl",
    "subnational_data",
    "cross_country",
    "dashboard",
    "staging",
    "production",
)


def validate_skill(skill: Path) -> list[str]:
    issues: list[str] = []
    skill_md = skill / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill.name}: SKILL.md is missing"]
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return [f"{skill.name}: SKILL.md has no YAML frontmatter"]
    try:
        _, raw_frontmatter, body = text.split("---", 2)
        metadata = yaml.safe_load(raw_frontmatter)
    except (ValueError, yaml.YAMLError) as exc:
        return [f"{skill.name}: invalid frontmatter: {exc}"]
    if not isinstance(metadata, dict):
        return [f"{skill.name}: frontmatter must be an object"]
    if set(metadata) != {"name", "description"}:
        issues.append(
            f"{skill.name}: frontmatter must contain only name and description"
        )
    if metadata.get("name") != skill.name:
        issues.append(f"{skill.name}: frontmatter name does not match directory")
    if not NAME_PATTERN.fullmatch(skill.name) or len(skill.name) > 64:
        issues.append(f"{skill.name}: invalid skill name")
    description = metadata.get("description")
    if not isinstance(description, str) or not description.strip():
        issues.append(f"{skill.name}: description is empty")
    if not body.strip():
        issues.append(f"{skill.name}: instruction body is empty")
    if not (skill / "agents" / "openai.yaml").is_file():
        issues.append(f"{skill.name}: agents/openai.yaml is missing")
    return issues


def validate_orchestrator_contract() -> list[str]:
    issues: list[str] = []
    orchestrator = SKILLS / "mega-country-onboarding"
    checker = orchestrator / "scripts" / "check_manifest.py"
    template_path = orchestrator / "assets" / "onboarding-manifest.json"
    try:
        namespace = runpy.run_path(str(checker))
        template = json.loads(template_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot load orchestrator contract: {exc}"]

    code_order = tuple(namespace.get("GATE_ORDER", ()))
    required_gates = set(namespace.get("REQUIRED_GATES", set()))
    template_order = tuple((template.get("gates") or {}).keys())
    if namespace.get("CURRENT_SCHEMA_VERSION") != 5:
        issues.append("check_manifest.py must use schema version 5")
    if template.get("schema_version") != 5:
        issues.append("onboarding-manifest.json must use schema version 5")
    if code_order != EXPECTED_GATE_ORDER:
        issues.append("GATE_ORDER does not match the schema-v5 dependency order")
    if required_gates != set(EXPECTED_GATE_ORDER):
        issues.append("REQUIRED_GATES does not match the schema-v5 gate set")
    if template_order != EXPECTED_GATE_ORDER:
        issues.append("manifest template gate order does not match GATE_ORDER")

    skill_text = (orchestrator / "SKILL.md").read_text(encoding="utf-8")
    labels = ("| Subnational scope |", "| BOOST ETL |", "| Subnational data |")
    if not all(label in skill_text for label in labels):
        issues.append("orchestrator gate table is missing schema-v5 subnational labels")
    elif not (
        skill_text.index(labels[0])
        < skill_text.index(labels[1])
        < skill_text.index(labels[2])
    ):
        issues.append("orchestrator gate table has the wrong subnational order")
    return issues


def main() -> int:
    issues: list[str] = []
    skill_dirs = sorted(path for path in SKILLS.iterdir() if path.is_dir())
    if not skill_dirs:
        issues.append("no skill directories found")
    for skill in skill_dirs:
        issues.extend(validate_skill(skill))
    issues.extend(validate_orchestrator_contract())
    for path in sorted(SKILLS.rglob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
    result = {
        "passed": not issues,
        "skills": len(skill_dirs),
        "json_files": len(list(SKILLS.rglob("*.json"))),
        "issues": issues,
    }
    print(json.dumps(result, indent=2))
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
