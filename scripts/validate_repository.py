#!/usr/bin/env python3
"""Validate the public MEGA country-onboarding skill repository."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


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


def main() -> int:
    issues: list[str] = []
    skill_dirs = sorted(path for path in SKILLS.iterdir() if path.is_dir())
    if not skill_dirs:
        issues.append("no skill directories found")
    for skill in skill_dirs:
        issues.extend(validate_skill(skill))
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
