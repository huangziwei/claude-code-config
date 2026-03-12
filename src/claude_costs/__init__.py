"""Interactive TUI for Claude Code session costs."""

from importlib.metadata import version as _pkg_version

__version__ = _pkg_version("claude-costs")

import argparse
import csv
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Header, Static, Tree

CSV_PATH = Path.home() / ".claude" / "session-costs.csv"


def load_rows(project_filter: str | None = None) -> list[dict]:
    if not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0:
        return []
    with open(CSV_PATH, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if project_filter:
        rows = [r for r in rows if r.get("project") == project_filter]
    rows = [r for r in rows if float(r.get("cost_usd", 0)) > 0]
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
        lambda: defaultdict(
            lambda: {
                "cost": 0.0,
                "sessions": 0,
                "in_tok": 0,
                "out_tok": 0,
                "duration_ms": 0,
                "rows": [],
            }
        )
    )
    for row in rows:
        period = period_key(row.get("timestamp", ""), granularity)
        project = row.get("project", "unknown")
        cost = float(row.get("cost_usd", 0))
        in_tok = int(row.get("input_tokens", 0) or 0)
        out_tok = int(row.get("output_tokens", 0) or 0)
        dur_ms = int(row.get("duration_api_ms", 0) or 0)
        data[period][project]["cost"] += cost
        data[period][project]["sessions"] += 1
        data[period][project]["in_tok"] += in_tok
        data[period][project]["out_tok"] += out_tok
        data[period][project]["duration_ms"] += dur_ms
        data[period][project]["rows"].append(row)
    return data


def _display_width(s: str) -> int:
    """Return the number of terminal columns a string occupies."""
    w = 0
    for ch in s:
        eaw = unicodedata.east_asian_width(ch)
        w += 2 if eaw in ("W", "F") else 1
    return w


def _ljust(s: str, width: int) -> str:
    """Left-justify *s* to *width* terminal columns."""
    return s + " " * (width - _display_width(s))


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


def _duration(ms: int) -> str:
    """Format milliseconds as a human-readable duration."""
    seconds = ms // 1000
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h{mins:02d}m"


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
        layout: horizontal;
    }
    .tab {
        width: auto;
        min-width: 0;
        margin: 0 1 0 0;
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
    ):
        super().__init__()
        self.rows = rows
        self.granularity = initial_granularity
        self.show_tokens = False
        self._project_filter = project_filter

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="granularity-bar"):
            yield Static("Monthly", id="tab-monthly", classes="tab")
            yield Static("Weekly", id="tab-weekly", classes="tab")
            yield Static("Daily", id="tab-daily", classes="tab")
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
        self._rebuild()

    def on_click(self, event) -> None:
        widget = event.widget
        if isinstance(widget, Static) and widget.id and widget.id.startswith("tab-"):
            granularity = widget.id.removeprefix("tab-")
            self.action_set_granularity(granularity)

    def _rebuild(self) -> None:
        g = self.granularity

        # Granularity indicator
        tabs = {"monthly": "Monthly", "weekly": "Weekly", "daily": "Daily"}
        for key, label in tabs.items():
            widget = self.query_one(f"#tab-{key}", Static)
            if key == g:
                widget.update(f"[bold reverse] {label} [/]")
            else:
                widget.update(f"[dim] {label} [/]")

        # Aggregate
        data = aggregate(self.rows, g)
        tree: Tree = self.query_one("#cost-tree", Tree)
        tree.clear()
        tree.show_root = False

        if not data:
            tree.root.add_leaf(Text("No session data found.", style="dim"))
            self.query_one("#total-bar", Static).update("")
            return

        periods = sorted(data.keys(), reverse=True)

        show_tok = self.show_tokens

        # Value to display and scale bars by
        def _val(p: dict) -> float:
            if show_tok:
                return p["in_tok"] + p["out_tok"]
            return p["cost"]

        # Fixed scale for bars: 1 block = $1 (cost) or 50k tokens.
        # Capped at 50 blocks max to avoid overflow.
        max_bar = 300
        if show_tok:
            bar_unit = 50_000  # tokens per block
        else:
            bar_unit = 1.0  # dollars per block

        all_projects = {p for projects in data.values() for p in projects}
        pad = max(_display_width(p) for p in all_projects) if all_projects else 12

        # Compute global max widths for sessions and duration columns
        max_sess_width = 0
        max_dur_width = 0
        for projects in data.values():
            for p in projects.values():
                sess_str = f"({_sess(p['sessions'])})"
                dur_str = _duration(p["duration_ms"]) if p["duration_ms"] else ""
                max_sess_width = max(max_sess_width, len(sess_str))
                max_dur_width = max(max_dur_width, len(dur_str))

        grand_total = 0.0
        grand_sessions = 0
        grand_in = 0
        grand_out = 0
        grand_dur = 0

        for period in periods:
            projects = data[period]
            total = sum(p["cost"] for p in projects.values())
            total_sessions = sum(p["sessions"] for p in projects.values())
            total_in = sum(p["in_tok"] for p in projects.values())
            total_out = sum(p["out_tok"] for p in projects.values())
            total_dur = sum(p["duration_ms"] for p in projects.values())
            grand_total += total
            grand_sessions += total_sessions
            grand_in += total_in
            grand_out += total_out
            grand_dur += total_dur

            label = Text()
            label.append(f"{period}", style="bold")
            if show_tok:
                label.append(
                    f"  {_tok(total_in)} in / {_tok(total_out)} out", style="blue"
                )
            else:
                label.append(f"  ${total:>8.2f}", style=_cost_style(total))
            label.append(f"  ({_sess(total_sessions)})", style="dim")
            if total_dur:
                label.append(f"  {_duration(total_dur)}", style="italic")

            node = tree.root.add(label, expand=True)

            for proj_name in sorted(projects, key=lambda p: -_val(projects[p])):
                p = projects[proj_name]
                sess_str = f"({_sess(p['sessions'])})"
                dur_str = _duration(p["duration_ms"]) if p["duration_ms"] else ""
                bar_len = min(max_bar, int(_val(p) / bar_unit))
                bar = "\u2588" * bar_len

                if show_tok:
                    val_str = (
                        f"  {_tok(p['in_tok']):>6} in / {_tok(p['out_tok']):>6} out"
                    )
                else:
                    val_str = f"  ${p['cost']:>8.2f}"

                # Build entire prefix as one plain string to guarantee
                # fixed width, then apply styles by character position.
                name_padded = _ljust(proj_name, pad)
                prefix = name_padded
                prefix += val_str
                prefix += f"  {sess_str:>{max_sess_width}}"
                if max_dur_width:
                    prefix += f"  {dur_str:>{max_dur_width}}"
                prefix += "  "

                plabel = Text(prefix)
                # Apply styles by character ranges (indices are character-based)
                c = 0
                name_len = len(name_padded)
                plabel.stylize("cyan", c, c + name_len)
                c += name_len
                val_style = "blue" if show_tok else _cost_style(p["cost"])
                plabel.stylize(val_style, c, c + len(val_str))
                c += len(val_str)
                plabel.stylize("dim", c, c + 2 + max_sess_width)
                c += 2 + max_sess_width
                if max_dur_width and dur_str:
                    plabel.stylize("italic", c, c + 2 + max_dur_width)

                if bar:
                    plabel.append(bar, style="magenta")

                proj_node = node.add(plabel, expand=False)
                for srow in sorted(
                    p["rows"],
                    key=lambda r: r.get("timestamp", ""),
                    reverse=True,
                ):
                    slabel = Text()
                    ts = srow.get("timestamp", "")
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        dt = dt.astimezone()
                        ts_fmt = dt.strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        ts_fmt = ts
                    scost = float(srow.get("cost_usd", 0))
                    slabel.append(f"{ts_fmt}", style="dim")
                    slabel.append(f"  ${scost:>7.2f}", style=_cost_style(scost))
                    s_in = int(srow.get("input_tokens", 0) or 0)
                    s_out = int(srow.get("output_tokens", 0) or 0)
                    if s_in or s_out:
                        slabel.append(
                            f"  {_tok(s_in)} in / {_tok(s_out)} out", style="blue"
                        )
                    s_dur = int(srow.get("duration_api_ms", 0) or 0)
                    if s_dur:
                        slabel.append(f"  {_duration(s_dur)}", style="italic")
                    model = srow.get("model", "")
                    if model:
                        slabel.append(f"  [{model}]", style="dim italic")
                    proj_node.add_leaf(slabel)

        total_text = Text()
        total_text.append("Total: ", style="bold")
        if show_tok:
            total_text.append(
                f"{_tok(grand_in)} in / {_tok(grand_out)} out", style="bold blue"
            )
        else:
            total_text.append(f"${grand_total:.2f}", style="bold green")
        total_text.append(f"  ({_sess(grand_sessions)})", style="dim")
        if grand_dur:
            total_text.append(f"  {_duration(grand_dur)} api", style="bold italic")
        self.query_one("#total-bar", Static).update(total_text)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Claude Code session costs.")
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-d",
        "--daily",
        action="store_const",
        const="daily",
        dest="granularity",
        help="Start with daily view.",
    )
    group.add_argument(
        "-w",
        "--weekly",
        action="store_const",
        const="weekly",
        dest="granularity",
        help="Start with weekly view.",
    )
    group.add_argument(
        "-m",
        "--monthly",
        action="store_const",
        const="monthly",
        dest="granularity",
        help="Start with monthly view (default).",
    )
    parser.set_defaults(granularity="monthly")
    parser.add_argument(
        "--project",
        type=str,
        default=None,
        help="Filter to a specific project name.",
    )
    args = parser.parse_args()

    rows = load_rows(project_filter=args.project)

    app = CostsApp(
        rows,
        initial_granularity=args.granularity,
        project_filter=args.project,
    )
    app.run()
