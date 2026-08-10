"""Run the complete V0.1 release quality gate."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STEPS = (
    (
        "Static analysis",
        [sys.executable, "-m", "ruff", "check", "app", "tests", "migrations", "scripts"],
    ),
    ("Sensitive-information scan", [sys.executable, "scripts/check_sensitive_info.py"]),
    (
        "Regression and coverage",
        [
            sys.executable,
            "-m",
            "pytest",
            "-W",
            "error",
            "--cov=app",
            "--cov-report=term-missing",
            "--cov-fail-under=90",
        ],
    ),
    ("Migration drift check", [sys.executable, "-m", "alembic", "check"]),
)


def main() -> None:
    for index, (label, command) in enumerate(STEPS, start=1):
        print(f"\n[{index}/{len(STEPS)}] {label}", flush=True)
        subprocess.run(command, cwd=REPO_ROOT, check=True)
    print("\nV0.1 quality gate passed.")


if __name__ == "__main__":
    main()
