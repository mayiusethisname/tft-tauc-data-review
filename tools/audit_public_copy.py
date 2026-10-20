"""Check the portfolio tree for obvious private-path and source-material leaks."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache"}
SENSITIVE_NAMES = (
    "자소서",
    "draft_review",
    "local_validation",
    "qa_fixtures",
    "report_snapshot.sql",
)
PRIVATE_TEXT_MARKERS = (
    "D:" + chr(92) + "AMD" + chr(92) + "8주차",
    "C:" + chr(92) + "Users" + chr(92) + "MSI",
    "local_" + "validation",
    "draft_" + "review",
    "자소서" + "용",
)


def audit() -> list[str]:
    issues: list[str] = []
    required = (
        "README.md",
        "VALIDATION.md",
        "analysis/profile_8week.py",
        "analysis/tauc_analysis.py",
        "analysis_service.py",
        "examples.py",
        "api/index.py",
        "index.html",
        "docs/guide.md",
        "docs/cases.md",
        "docs/method.md",
        "docs/references.md",
        "docs/assets/normal.svg",
        "docs/assets/spike.svg",
        "docs/assets/incomplete-spectrum.svg",
    )
    for relative in required:
        if not (ROOT / relative).is_file():
            issues.append(f"missing:{relative}")

    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if any(marker.lower() in relative.lower() for marker in SENSITIVE_NAMES):
            issues.append(f"private_name:{relative}")
            continue
        if path.suffix.lower() in {".pyc", ".pyo"} or path.name.lower() in {".env", ".env.local"}:
            issues.append(f"private_file:{relative}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if path.suffix == ".md":
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
                target = target.strip("<>").split("#", 1)[0]
                if target and not re.match(r"^[a-zA-Z]+:", target) and not (path.parent / target).is_file():
                    issues.append(f"broken_link:{relative}:{target}")
        # Marker definitions intentionally contain the strings this audit searches for.
        if path.resolve() == Path(__file__).resolve():
            continue
        for marker in PRIVATE_TEXT_MARKERS:
            if marker.lower() in text.lower():
                issues.append(f"private_text:{relative}:{marker}")
                break
        if re.search(r"(?i)(?:[A-Z]:" + re.escape(chr(92)) + r"|/Users/[^/]+/)", text):
            issues.append(f"absolute_machine_path:{relative}")
    return issues


if __name__ == "__main__":
    found = audit()
    if found:
        print("PUBLIC_COPY_AUDIT_FAILED")
        print("\n".join(found))
        raise SystemExit(1)
    print("PUBLIC_COPY_AUDIT_OK")
