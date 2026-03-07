# claude-costs

Interactive TUI for tracking Claude Code session costs and token usage.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/huangziwei/claude-costs/main/install.sh | bash
```

Or clone and run locally:

```bash
git clone https://github.com/huangziwei/claude-costs.git
bash claude-costs/install.sh
```

The installer copies the status line script, merges settings into `~/.claude/settings.json`, and installs the `claude-costs` TUI via `uv tool install`. It is safe to run multiple times.

## Usage

```bash
claude-costs        # launch interactive TUI (monthly view)
claude-costs -d     # start with daily view
claude-costs -w     # start with weekly view
```

### TUI keybindings

| Key | Action |
|-----|--------|
| `m` | Monthly view |
| `w` | Weekly view |
| `d` | Daily view |
| `t` | Toggle between costs and tokens |
| `r` | Reload data |
| `q` | Quit |

## What's included

### Status line

Shows model, context remaining, session cost, working directory, and git branch:

```
Opus 4.6 · context: 77% left · $1.26 this session · ~/projects/myapp (main)
```

### Session data logger

The status line upserts the current session's cost and token counts to `~/.claude/session-costs.csv` on every tick.

```csv
timestamp,session_id,project,model,cost_usd,input_tokens,output_tokens
2026-03-01T12:45:41Z,abc123,myapp,claude-opus-4-6,0.2481,52340,8120
```

## Requirements

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) (for tool install)
- `git` (optional, for branch display in status line)

## Files

| Installed to | Purpose |
|---|---|
| `~/.claude/statusline-command.py` | Status line + live CSV upsert |
| `~/.claude/settings.json` | Merged (not overwritten) |
| `~/.claude/session-costs.csv` | Accumulated session data (updated live) |
