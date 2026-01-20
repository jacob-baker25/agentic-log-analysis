"""
structure_check.py

Validates that a generated incident report follows the required schema:
- all required section headings are present
- headings appear in the correct order

This does not validate facts; it only validates structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
import re

@dataclass(frozen=True)
class StructureCheckResult:
    ok: bool
    errors: List[str]


# For v1: hard-code required headings to avoid brittle parsing.
# These should match the headings in docs/report/report_schema.md exactly.
REQUIRED_HEADINGS = [
    "Executive Summary",
    "Incident Window",
    "Impact",
    "Hotspots",
    "Traffic Context",
    "Likely Explanation",
    "Recommended Next Checks",
]

def _heading_pattern(title: str) -> re.Pattern:
    # Matches:
    #  "## Executive Summary"
    #  "## 1. Executive Summary"
    #  "## 1 Executive Summary"
    return re.compile(rf"^##\s*(?:\d+\.?\s*)?{re.escape(title)}\s*$", re.MULTILINE)

def check_report_structure(report_md: str) -> StructureCheckResult:
    errors: List[str] = []
    positions = {}

    for title in REQUIRED_HEADINGS:
        pat = _heading_pattern(title)
        match = pat.search(report_md)

        if not match:
            errors.append(f"Missing required heading: ## {title}")
            continue

        # Record position for ordering check
        positions[title] = match.start()

        # Check for duplicates
        second_match = pat.search(report_md, match.end())
        if second_match:
            errors.append(f"Heading appears more than once: ## {title}")

    # If missing or duplicate headings, ordering check is meaningless
    if errors:
        return StructureCheckResult(ok=False, errors=errors)

    # Check ordering
    last_pos = -1
    for title in REQUIRED_HEADINGS:
        pos = positions[title]
        if pos < last_pos:
            errors.append("Headings are out of order.")
            break
        last_pos = pos

    return StructureCheckResult(ok=(len(errors) == 0), errors=errors)
