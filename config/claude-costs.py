#!/usr/bin/env python3
"""Summarize Claude Code session costs from ~/.claude/session-costs.csv."""

import argparse
import csv
import io
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

CSV_PATH = Path.home() / ".claude" / "session-costs.csv"


def load_rows(project_filter: str | None = None) -> list[dict]:
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        return []
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if project_filter:
        rows = [r for r in rows if r.get("project") == project_filter]
    return rows


def load_remote_rows(
    host: str, project_filter: str | None = None
) -> list[dict]:
    """Read session-costs.csv from a remote host via SSH."""
    remote_path = "~/.claude/session-costs.csv"
    try:
        result = subprocess.run(
            ["ssh", host, "cat", remote_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"Warning: failed to read from {host}: {e}", file=sys.stderr)
        return []
    if result.returncode != 0:
        print(
            f"Warning: ssh {host} failed: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return []
    rows = list(csv.DictReader(io.StringIO(result.stdout)))
    if project_filter:
        rows = [r for r in rows if r.get("project") == project_filter]
    return rows


def period_key(timestamp: str, granularity: str) -> str:
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    if granularity == "daily":
        return dt.strftime("%Y-%m-%d")
    if granularity == "weekly":
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return dt.strftime("%Y-%m")


def summarize(rows: list[dict], granularity: str, last: int | None = None) -> None:
    # {period: {project: {"cost": float, "sessions": int}}}
    data: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"cost": 0.0, "sessions": 0})
    )

    for row in rows:
        period = period_key(row.get("timestamp", ""), granularity)
        project = row.get("project", "unknown")
        cost = float(row.get("cost_usd", 0))
        data[period][project]["cost"] += cost
        data[period][project]["sessions"] += 1

    if not data:
        print("No session data found.")
        return

    periods = sorted(data.keys(), reverse=True)
    if last is not None:
        periods = periods[:last]

    # Find the longest project name for alignment (only within shown periods).
    all_projects = {p for k in periods for p in data[k]}
    pad = max(len(p) for p in all_projects) if all_projects else 0

    for period in periods:
        projects = data[period]
        total = sum(p["cost"] for p in projects.values())
        total_sessions = sum(p["sessions"] for p in projects.values())
        print(f"{period}  ${total:>8.2f}  ({total_sessions} sessions)")
        for project in sorted(projects.keys()):
            p = projects[project]
            print(f"  {project:<{pad}}  ${p['cost']:>8.2f}  ({p['sessions']} sessions)")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize Claude Code session costs."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--daily", action="store_const", const="daily", dest="granularity",
        help="Group by day.",
    )
    group.add_argument(
        "--weekly", action="store_const", const="weekly", dest="granularity",
        help="Group by week.",
    )
    parser.set_defaults(granularity="monthly")
    parser.add_argument(
        "--last", type=int, default=None, metavar="N",
        help="Show only the last N periods.",
    )
    parser.add_argument(
        "--project", type=str, default=None,
        help="Filter to a specific project name.",
    )
    parser.add_argument(
        "--remote",
        type=str,
        action="append",
        default=[],
        metavar="HOST",
        help="SSH host to read remote costs from (can be repeated).",
    )
    args = parser.parse_args()

    rows = load_rows(project_filter=args.project)
    for host in args.remote:
        rows.extend(load_remote_rows(host, project_filter=args.project))
    summarize(rows, granularity=args.granularity, last=args.last)


if __name__ == "__main__":
    main()
