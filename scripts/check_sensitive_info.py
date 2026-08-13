"""Fail when tracked files contain likely credentials or private key material."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".css",
    ".env",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
FORBIDDEN_TRACKED_PATTERNS = (
    re.compile(r"(^|/)\.env$"),
    re.compile(r"(^|/)(var|\.venv)/"),
    re.compile(r"\.(db|sqlite|sqlite3|pem|key|p12|pfx)$", re.IGNORECASE),
)
SECRET_PATTERNS = {
    "PEM private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "OpenAI API key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "credentialed URL": re.compile(
        r"\b(?:https?|postgres(?:ql)?|mysql)://[^\s/:]+:[^\s/@]+@",
        re.IGNORECASE,
    ),
    "literal secret assignment": re.compile(
        r"(?i)\b(?:api_key|access_token|client_secret)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]"
    ),
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    reason: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.reason}"


def scan_text(path: str, content: str) -> list[Finding]:
    findings: list[Finding] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        for reason, pattern in SECRET_PATTERNS.items():
            if pattern.search(line):
                findings.append(Finding(path, line_number, reason))
    return findings


def tracked_files(repo_root: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return tuple(
        item.decode("utf-8")
        for item in result.stdout.split(b"\0")
        if item
    )


def scan_repository(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for relative_path in tracked_files(repo_root):
        normalized = relative_path.replace("\\", "/")
        if any(pattern.search(normalized) for pattern in FORBIDDEN_TRACKED_PATTERNS):
            findings.append(Finding(normalized, 0, "forbidden tracked file"))
            continue
        path = repo_root / relative_path
        # ``git ls-files`` still returns an index entry while a tracked file is
        # staged or unstaged for deletion. Scan the current worktree state and
        # safely skip entries that no longer exist there.
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(scan_text(normalized, content))
    return findings


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    findings = scan_repository(repo_root)
    if findings:
        print("Sensitive-information gate failed:")
        for finding in findings:
            print(f"- {finding}")
        raise SystemExit(1)
    print("Sensitive-information gate passed.")


if __name__ == "__main__":
    main()
