# QuantClaw Doctor Command — Design Document

**Date:** 2026-04-05
**Status:** Approved
**Author:** Harry + Claude

## Overview

`quantclaw doctor` is a health check and auto-repair command inspired by OpenClaw's doctor. It diagnoses the full QuantClaw stack and optionally fixes common issues.

## Usage

```
quantclaw doctor          # Diagnose only
quantclaw doctor --repair # Diagnose + auto-fix what it can
```

## Health Checks

| # | Check | Auto-repair |
|---|---|---|
| 1 | Python 3.12+ installed | No |
| 2 | pip dependencies installed | Yes — `pip install -e .` |
| 3 | Node.js + npm installed | No |
| 4 | Dashboard deps installed | Yes — `npm install` |
| 5 | Data directory exists | Yes — `mkdir data/` |
| 6 | SQLite DB connectable, schema current | Yes — create/migrate |
| 7 | Playbook file valid JSONL | Yes — create empty file |
| 8 | Config valid | Yes — create from default |
| 9 | LLM provider available (Ollama OR API key) | No (report) |
| 10 | Backend port 8000 | No (report status) |
| 11 | Sidecar port 8001 | No (report status) |
| 12 | Dashboard port 3000 | No (report status) |
| 13 | Agents registered, match trust level | No (report) |
| 14 | OODA loop background task | No (report) |

## Output Format

```
QuantClaw Doctor

  [OK]    Python 3.12.10
  [OK]    pip dependencies
  [WARN]  Dashboard deps missing — run with --repair to fix
  [OK]    Data directory
  [OK]    SQLite database
  [OK]    Playbook (42 entries)
  [OK]    Config loaded
  [FAIL]  No LLM provider — install Ollama or set ANTHROPIC_API_KEY
  [OK]    Backend (port 8000)
  [SKIP]  Sidecar (port 8001) — not running
  [SKIP]  Dashboard (port 3000) — not running
  [OK]    13 agents registered
  [SKIP]  OODA loop — server not running

  12 passed, 1 failed, 3 skipped
  Run 'quantclaw doctor --repair' to fix issues.
```

## Implementation

- `quantclaw/doctor.py` — Python module with all 14 checks
- `bin/quantclaw.mjs` — Add `doctor` command that calls `python -m quantclaw.doctor`
- Each check is a function returning `{status, message}`
- Statuses: `ok`, `warn`, `fail`, `skip`, `fixed`
- `--repair` flag passed as CLI arg
