#!/usr/bin/env bash
set -euo pipefail

CLAUDE_DIR="$HOME/.claude"
SETTINGS="$CLAUDE_DIR/settings.json"

# Resolve the repo root (works whether cloned or piped via curl).
if [ -f "${BASH_SOURCE[0]:-}" ]; then
  REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-}")" && pwd)"
else
  # Piped via curl — download to a temp dir first.
  REPO_DIR="$(mktemp -d)"
  trap 'rm -rf "$REPO_DIR"' EXIT
  echo "Downloading config files..."
  git clone --depth 1 https://github.com/huangziwei/claude-code-config.git "$REPO_DIR" 2>/dev/null
fi

CONFIG_DIR="$REPO_DIR/config"

printf "\033[1mInstalling Claude Code config...\033[0m\n\n"

# --- Copy config files into ~/.claude/ ------------------------------------
mkdir -p "$CLAUDE_DIR/hooks"
cp "$CONFIG_DIR/statusline-command.py"        "$CLAUDE_DIR/statusline-command.py"
cp "$CONFIG_DIR/hooks/session-cost-logger.py" "$CLAUDE_DIR/hooks/session-cost-logger.py"
cp "$CONFIG_DIR/claude-costs.py"              "$CLAUDE_DIR/claude-costs.py"
# Clean up old bash statusline if present.
rm -f "$CLAUDE_DIR/statusline-command.sh"

# --- Merge into settings.json (non-destructive) ---------------------------
python3 - "$SETTINGS" << 'MERGE'
import json, sys, os

settings_path = sys.argv[1]

# Our config to merge in.
statusline_cmd = "python3 " + os.path.expanduser("~/.claude/statusline-command.py")
cost_logger_cmd = "python3 " + os.path.expanduser("~/.claude/hooks/session-cost-logger.py")

our_statusline = {"type": "command", "command": statusline_cmd}
our_hook = {"type": "command", "command": cost_logger_cmd}

# Load existing settings.
settings = {}
if os.path.isfile(settings_path):
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, ValueError):
        pass

# Always set statusLine to our command (overwrite old bash version).
settings["statusLine"] = our_statusline

# Merge SessionEnd hook without duplicating.
hooks = settings.setdefault("hooks", {})
session_end = hooks.setdefault("SessionEnd", [])

# Check if our hook command is already present.
already = any(
    h.get("command") == cost_logger_cmd
    for entry in session_end
    for h in (entry.get("hooks") or [])
)
if not already:
    session_end.append({"hooks": [our_hook]})

with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2, ensure_ascii=False)
    f.write("\n")
MERGE

# --- Summary ---------------------------------------------------------------
printf "\n\033[32mDone!\033[0m Installed:\n"
printf "  \033[90m%s\033[0m  %s\n" "statusline" "$CLAUDE_DIR/statusline-command.py"
printf "  \033[90m%s\033[0m  %s\n" "cost logger" "$CLAUDE_DIR/hooks/session-cost-logger.py"
printf "  \033[90m%s\033[0m  %s\n" "cost summary" "$CLAUDE_DIR/claude-costs.py"
printf "  \033[90m%s\033[0m  %s\n" "settings" "$SETTINGS (merged)"
printf "\nSession costs will be logged to \033[90m%s\033[0m\n" "$CLAUDE_DIR/session-costs.csv"
