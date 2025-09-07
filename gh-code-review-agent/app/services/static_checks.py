from __future__ import annotations
import re
from typing import Dict, List, Tuple


# Very light heuristics; language-agnostic where possible
LINE_TOO_LONG = 120


ISSUE_TYPES = {
"style": "style",
"bug": "bug",
"performance": "performance",
"best": "best_practice",
"security": "security",
}


PATTERNS = [
(ISSUE_TYPES["security"], re.compile(r"\b(eval|exec)\s*\("), "Avoid eval/exec; use safer alternatives"),
(ISSUE_TYPES["bug"], re.compile(r"except\s*:\s*pass\b"), "Do not use bare except:pass; log or handle specific exceptions"),
(ISSUE_TYPES["best"], re.compile(r"\bprint\("), "Use structured logging instead of print statements"),
(ISSUE_TYPES["performance"], re.compile(r"for\s+.+:\s*\n\s*\w+\s*\+=\s*\w+"), "String concat in loops; prefer join or io.StringIO"),
(ISSUE_TYPES["bug"], re.compile(r"def\s+\w+\(.*=\s*\[|\{\|\(\)"), "Mutable default arguments can cause bugs"),
]


def run_static_checks(file_path: str, content: str) -> List[dict]:
    issues: List[dict] = []
    lines = content.splitlines()
    for idx, line in enumerate(lines, start=1):
        if len(line) > LINE_TOO_LONG:
            issues.append({
            "type": ISSUE_TYPES["style"],
            "line": idx,
            "description": f"Line too long: {len(line)} chars",
            "suggestion": f"Limit to <= {LINE_TOO_LONG} chars; wrap or refactor",
            "severity": "low"
            })
    for t, pat, msg in PATTERNS:
        if pat.search(line):
            issues.append({
            "type": t,
            "line": idx,
            "description": msg,
            "suggestion": None,
            "severity": "medium" if t != ISSUE_TYPES["security"] else "high",
            })
    return issues