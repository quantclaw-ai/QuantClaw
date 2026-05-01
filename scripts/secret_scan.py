"""Fail if tracked files look like they contain real secrets.

This is intentionally small and dependency-free so it can run in CI and before
publishing. It scans tracked files, skips generated/binary-heavy paths, and
looks for high-confidence secret patterns rather than every use of words like
``token`` in tests or docs.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".next",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "data",
    "dist",
    "build",
}

SKIP_EXTS = {
    ".ico",
    ".jpg",
    ".jpeg",
    ".png",
    ".psd",
    ".pyc",
    ".tgz",
    ".webp",
    ".zip",
}

DENY_FILENAMES = {
    ".env",
    "oauth_credentials.json",
    "credentials.json",
    "client_secret.json",
}

DENY_EXTS = {".key", ".pem", ".p12", ".pfx", ".sqlite", ".db"}

PATTERNS = [
    ("private key", re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}\b")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{32,}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{80,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
]


def tracked_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return [ROOT / line for line in result.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.CalledProcessError):
        files: list[Path] = []
        for path in ROOT.rglob("*"):
            if path.is_file() and not any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
                files.append(path)
        return files


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return any(part in SKIP_DIRS for part in rel.parts) or path.suffix.lower() in SKIP_EXTS


def scan() -> list[str]:
    findings: list[str] = []
    for path in tracked_files():
        rel = path.relative_to(ROOT)
        lower_name = path.name.lower()
        if lower_name in DENY_FILENAMES or path.suffix.lower() in DENY_EXTS:
            findings.append(f"{rel}: sensitive file type should not be tracked")
            continue
        if should_skip(path):
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\0" in raw or len(raw) > 1_500_000:
            continue
        text = raw.decode("utf-8", errors="ignore")
        for name, pattern in PATTERNS:
            match = pattern.search(text)
            if match:
                line = text[: match.start()].count("\n") + 1
                findings.append(f"{rel}:{line}: possible {name}")
    return findings


def main() -> int:
    findings = scan()
    if findings:
        print("Secret scan failed:")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print("Secret scan passed: no high-confidence tracked secrets found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
