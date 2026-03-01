#!/usr/bin/env python3
"""Summarize Claude Code session costs from ~/.claude/session-costs.csv."""

import argparse
import csv
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


def period_key(timestamp: str, weekly: bool) -> str:
    try:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    if weekly:
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return dt.strftime("%Y-%m")


def summarize(rows: list[dict], weekly: bool) -> None:
    # {period: {project: {"cost": float, "sessions": int}}}
    data: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"cost": 0.0, "sessions": 0})
    )

    for row in rows:
        period = period_key(row.get("timestamp", ""), weekly)
        project = row.get("project", "unknown")
        cost = float(row.get("cost_usd", 0))
        data[period][project]["cost"] += cost
        data[period][project]["sessions"] += 1

    if not data:
        print("No session data found.")
        return

    # Find the longest project name for alignment.
    all_projects = {p for projects in data.values() for p in projects}
    pad = max(len(p) for p in all_projects) if all_projects else 0

    for period in sorted(data.keys(), reverse=True):
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
    parser.add_argument(
        "--weekly", action="store_true",
        help="Group by week instead of month.",
    )
    parser.add_argument(
        "--project", type=str, default=None,
        help="Filter to a specific project name.",
    )
    args = parser.parse_args()

    rows = load_rows(project_filter=args.project)
    summarize(rows, weekly=args.weekly)


if __name__ == "__main__":
    main()
