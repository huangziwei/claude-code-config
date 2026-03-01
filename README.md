# claude-code-config

My custom Claude Code enhancements.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/huangziwei/claude-code-config/main/install.sh | bash
```

Or clone and run locally:

```bash
git clone https://github.com/huangziwei/claude-code-config.git
bash claude-code-config/install.sh
```

The installer is idempotent — safe to run multiple times. It merges into your existing `~/.claude/settings.json` without overwriting other settings.

## What's included

### Status line

Shows model, context remaining, session cost, working directory, and git branch:

```
Opus 4.6 · context: 77% left · $1.26 this session · ~/projects/myapp (main)
```

### Session cost logger

The status line also upserts the current session's cost to `~/.claude/session-costs.csv` on every tick, using the authoritative `cost.total_cost_usd` reported by Claude Code. A `SessionEnd` hook stamps the exit reason when the session ends.

```csv
timestamp,session_id,project,model,cost_usd,reason
2026-03-01T12:45:41Z,abc123,myapp,claude-opus-4-6,0.2481,prompt_input_exit
```

### Cost summary

```bash
python3 ~/.claude/claude-costs.py                          # monthly, all projects
python3 ~/.claude/claude-costs.py --weekly                 # weekly, all projects
python3 ~/.claude/claude-costs.py --daily                  # daily, all projects
python3 ~/.claude/claude-costs.py --project myapp          # monthly, one project
```

```
2026-03  $   47.23  (12 sessions)
  claude-code-config  $   31.05  (8 sessions)
  myapp               $   16.18  (4 sessions)

2026-02  $   25.00  (6 sessions)
  myapp               $   25.00  (6 sessions)
```

## Requirements

- `python3` (used by the status line and cost logger)
- `git` (optional, for branch display)

## Files

| Installed to | Purpose |
|---|---|
| `~/.claude/statusline-command.py` | Status line + live cost CSV upsert |
| `~/.claude/hooks/session-cost-logger.py` | Stamps exit reason on session end |
| `~/.claude/claude-costs.py` | Cost summary CLI |
| `~/.claude/settings.json` | Merged (not overwritten) |
| `~/.claude/session-costs.csv` | Accumulated session costs (updated live) |
