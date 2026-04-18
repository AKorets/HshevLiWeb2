"""
Verify that the word 'tax' (any case) does not appear in project source files.
Covers: backend Python, Flutter Dart, and Documentation Markdown files.
"""

import re
from pathlib import Path

import pytest

# Repo root is two levels up from this file (backend/tests/)
REPO_ROOT = Path(__file__).resolve().parents[2]

# File globs to scan
SCAN_PATTERNS = [
    ("backend", "**/*.py"),
    ("lib", "**/*.dart"),
    ("Documentation", "**/*.md"),
]

# Files excluded from the check (this file itself, and any known false-positives)
EXCLUDED_FILES = {
    Path(__file__).resolve(),
}

TAX_RE = re.compile(r"\btax\b", re.IGNORECASE)


def _collect_violations() -> list[tuple[Path, int, str]]:
    """Return list of (file, line_number, line_text) for every 'tax' hit."""
    violations = []
    for folder, pattern in SCAN_PATTERNS:
        base = REPO_ROOT / folder
        if not base.exists():
            continue
        for path in sorted(base.glob(pattern)):
            if path.resolve() in EXCLUDED_FILES:
                continue
            try:
                for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if TAX_RE.search(line):
                        violations.append((path, lineno, line.strip()))
            except (UnicodeDecodeError, OSError):
                pass  # skip unreadable files
    return violations


def _format_violation(path: Path, lineno: int, line: str) -> str:
    rel = path.relative_to(REPO_ROOT)
    return f"  {rel}:{lineno}  →  {line}"


def test_no_tax_wording_in_source_files():
    violations = _collect_violations()
    if violations:
        report = "\n".join(_format_violation(*v) for v in violations)
        pytest.fail(
            f"Found 'tax' wording in {len(violations)} location(s) — use 'fee' instead:\n{report}"
        )
