"""Interactive TUI for Claude Code session costs."""

import argparse
import csv
import io
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Static, Tree

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
        sunday = dt - timedelta(days=(dt.weekday() + 1) % 7)
        iso = sunday.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return dt.strftime("%Y-%m")


def aggregate(rows: list[dict], granularity: str) -> dict:
    data: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"cost": 0.0, "sessions": 0, "in_tok": 0, "out_tok": 0})
    )
    for row in rows:
        period = period_key(row.get("timestamp", ""), granularity)
        project = row.get("project", "unknown")
        cost = float(row.get("cost_usd", 0))
        in_tok = int(row.get("input_tokens", 0) or 0)
        out_tok = int(row.get("output_tokens", 0) or 0)
        data[period][project]["cost"] += cost
        data[period][project]["sessions"] += 1
        data[period][project]["in_tok"] += in_tok
        data[period][project]["out_tok"] += out_tok
    return data


def _cost_style(cost: float) -> str:
    if cost >= 50:
        return "bold red"
    if cost >= 10:
        return "yellow"
    return "green"


def _sess(n: int) -> str:
    return f"{n} session{'s' if n != 1 else ''}"


def _tok(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


class CostsApp(App):
    TITLE = "Claude Code Costs"
    CSS = """
    Screen {
        background: $surface;
    }
    #granularity-bar {
        dock: top;
        height: 1;
        padding: 0 2;
        background: $primary-background;
    }
    #total-bar {
        dock: bottom;
        height: 1;
        padding: 0 2;
        background: $primary-background;
    }
    Tree {
        padding: 1 2;
    }
    """
    BINDINGS = [
        Binding("m", "set_granularity('monthly')", "Monthly"),
        Binding("w", "set_granularity('weekly')", "Weekly"),
        Binding("d", "set_granularity('daily')", "Daily"),
        Binding("t", "toggle_tokens", "Tokens"),
        Binding("r", "reload", "Reload"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        rows: list[dict],
        initial_granularity: str = "monthly",
        project_filter: str | None = None,
        remote_hosts: list[str] | None = None,
    ):
        super().__init__()
        self.rows = rows
        self.granularity = initial_granularity
        self.show_tokens = False
        self._project_filter = project_filter
        self._remote_hosts = remote_hosts or []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="granularity-bar")
        yield Tree("", id="cost-tree")
        yield Static(id="total-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._rebuild()

    def action_set_granularity(self, g: str) -> None:
        if self.granularity != g:
            self.granularity = g
            self._rebuild()

    def action_toggle_tokens(self) -> None:
        self.show_tokens = not self.show_tokens
        self._rebuild()

    def action_reload(self) -> None:
        self.rows = load_rows(project_filter=self._project_filter)
        for host in self._remote_hosts:
            self.rows.extend(
                load_remote_rows(host, project_filter=self._project_filter)
            )
        self._rebuild()

    def _rebuild(self) -> None:
        g = self.granularity

        # Granularity indicator
        labels = {"monthly": "Monthly", "weekly": "Weekly", "daily": "Daily"}
        parts = []
        for key, label in labels.items():
            if key == g:
                parts.append(f"[bold reverse] {label} [/]")
            else:
                parts.append(f"[dim] {label} [/]")
        self.query_one("#granularity-bar", Static).update("  ".join(parts))

        # Aggregate
        data = aggregate(self.rows, g)
        tree: Tree = self.query_one("#cost-tree", Tree)
        tree.clear()
        tree.show_root = False

        if not data:
            tree.root.add_leaf(
                Text("No session data found.", style="dim")
            )
            self.query_one("#total-bar", Static).update("")
            return

        periods = sorted(data.keys(), reverse=True)

        show_tok = self.show_tokens

        # Value to display and scale bars by
        def _val(p: dict) -> float:
            if show_tok:
                return p["in_tok"] + p["out_tok"]
            return p["cost"]

        max_val = max(
            (_val(p) for projects in data.values() for p in projects.values()),
            default=1,
        ) or 1

        all_projects = {p for projects in data.values() for p in projects}
        pad = max(len(p) for p in all_projects) if all_projects else 12

        grand_total = 0.0
        grand_sessions = 0
        grand_in = 0
        grand_out = 0

        for period in periods:
            projects = data[period]
            total = sum(p["cost"] for p in projects.values())
            total_sessions = sum(p["sessions"] for p in projects.values())
            total_in = sum(p["in_tok"] for p in projects.values())
            total_out = sum(p["out_tok"] for p in projects.values())
            grand_total += total
            grand_sessions += total_sessions
            grand_in += total_in
            grand_out += total_out

            label = Text()
            label.append(f"{period}", style="bold")
            if show_tok:
                label.append(f"  {_tok(total_in)} in / {_tok(total_out)} out", style="blue")
            else:
                label.append(f"  ${total:>8.2f}", style=_cost_style(total))
            label.append(f"  ({_sess(total_sessions)})", style="dim")

            node = tree.root.add(label, expand=True)

            for proj_name in sorted(
                projects, key=lambda p: -_val(projects[p])
            ):
                p = projects[proj_name]
                bar_len = int(20 * _val(p) / max_val)
                bar = "\u2588" * bar_len

                sess_str = f"({_sess(p['sessions'])})"
                if show_tok:
                    val_str = f"  {_tok(p['in_tok']):>6} in / {_tok(p['out_tok']):>6} out"
                else:
                    val_str = f"  ${p['cost']:>8.2f}"
                text_len = pad + len(val_str) + 2 + len(sess_str)
                bar_col = pad + 40
                gap = max(2, bar_col - text_len)

                plabel = Text()
                plabel.append(f"{proj_name:<{pad}}", style="cyan")
                if show_tok:
                    plabel.append(val_str, style="blue")
                else:
                    plabel.append(val_str, style=_cost_style(p["cost"]))
                plabel.append(f"  {sess_str}", style="dim")
                plabel.append(" " * gap)
                if bar:
                    plabel.append(bar, style="magenta")

                node.add_leaf(plabel)

        total_text = Text()
        total_text.append("Total: ", style="bold")
        if show_tok:
            total_text.append(f"{_tok(grand_in)} in / {_tok(grand_out)} out", style="bold blue")
        else:
            total_text.append(f"${grand_total:.2f}", style="bold green")
        total_text.append(f"  ({_sess(grand_sessions)})", style="dim")
        self.query_one("#total-bar", Static).update(total_text)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize Claude Code session costs."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-d", "--daily", action="store_const", const="daily",
        dest="granularity", help="Start with daily view.",
    )
    group.add_argument(
        "-w", "--weekly", action="store_const", const="weekly",
        dest="granularity", help="Start with weekly view.",
    )
    group.add_argument(
        "-m", "--monthly", action="store_const", const="monthly",
        dest="granularity", help="Start with monthly view (default).",
    )
    parser.set_defaults(granularity="monthly")
    parser.add_argument(
        "--project", type=str, default=None,
        help="Filter to a specific project name.",
    )
    parser.add_argument(
        "--remote", type=str, action="append", default=[], metavar="HOST",
        help="SSH host to read remote costs from (can be repeated).",
    )
    args = parser.parse_args()

    rows = load_rows(project_filter=args.project)
    for host in args.remote:
        rows.extend(load_remote_rows(host, project_filter=args.project))

    app = CostsApp(
        rows,
        initial_granularity=args.granularity,
        project_filter=args.project,
        remote_hosts=args.remote,
    )
    app.run()
