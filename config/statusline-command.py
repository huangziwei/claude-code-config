#!/usr/bin/env python3
"""Claude Code status line with live session cost logging.

Reads the status-line JSON from stdin, prints a formatted status line,
and upserts the current session's cost to ~/.claude/session-costs.csv.
"""

import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CSV_PATH = Path.home() / ".claude" / "session-costs.csv"
CSV_FIELDS = [
    "timestamp",
    "session_id",
    "project",
    "model",
    "cost_usd",
    "input_tokens",
    "output_tokens",
]


def _git_branch(cwd: str) -> str:
    """Return the current git branch or short SHA, or empty string."""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "symbolic-ref", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def _upsert_csv(session_id: str, project: str, model: str,
                cost_usd: float, timestamp: str,
                input_tokens: int, output_tokens: int) -> None:
    """Update or insert the session's row in the CSV."""
    rows: list[dict] = []
    if CSV_PATH.exists() and CSV_PATH.stat().st_size > 0:
        with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    # Find and update existing row, or append new one.
    found = False
    for row in rows:
        if row.get("session_id") == session_id:
            row["timestamp"] = timestamp
            row["cost_usd"] = f"{cost_usd:.4f}"
            row["model"] = model
            row["input_tokens"] = str(input_tokens)
            row["output_tokens"] = str(output_tokens)
            found = True
            break

    if not found:
        rows.append({
            "timestamp": timestamp,
            "session_id": session_id,
            "project": project,
            "model": model,
            "cost_usd": f"{cost_usd:.4f}",
            "input_tokens": str(input_tokens),
            "output_tokens": str(output_tokens),
        })

    # Atomic write via temp file + rename.
    fd, tmp = tempfile.mkstemp(dir=CSV_PATH.parent, suffix=".csv")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})
        os.replace(tmp, CSV_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        return

    model_display = data.get("model", {}).get("display_name", "unknown")
    model_id = data.get("model", {}).get("id", "unknown")
    ctx = data.get("context_window", {})
    ctx_remaining = ctx.get("remaining_percentage", "?")
    input_tokens = ctx.get("total_input_tokens", 0)
    output_tokens = ctx.get("total_output_tokens", 0)
    cost_usd = data.get("cost", {}).get("total_cost_usd", 0)
    cwd = data.get("cwd", "")
    session_id = data.get("session_id", "unknown")

    # Shorten home dir to ~.
    home = os.path.expanduser("~")
    short_path = cwd.replace(home, "~", 1) if cwd.startswith(home) else cwd

    # Git branch.
    branch = _git_branch(cwd) if cwd else ""
    location = f"{short_path} ({branch})" if branch else short_path

    # Project name from cwd.
    project = os.path.basename(cwd) if cwd else "unknown"

    # Print status line.
    grey = "\033[90m"
    reset = "\033[0m"
    print(
        f"{grey}{model_display} \u00b7 context: {ctx_remaining}% left"
        f" \u00b7 ${cost_usd:.2f} this session \u00b7 {location}{reset}"
    )

    # Upsert CSV — best effort, never break the status line.
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _upsert_csv(session_id, project, model_id, cost_usd, now,
                    input_tokens, output_tokens)
    except Exception:
        pass


if __name__ == "__main__":
    main()
