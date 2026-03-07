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

# Detect install vs update.
if [ -f "$CLAUDE_DIR/statusline-command.py" ]; then
  ACTION="Updating"
else
  ACTION="Installing"
fi

printf "\033[1m%s Claude Code config...\033[0m\n\n" "$ACTION"

# --- Copy config files into ~/.claude/ ------------------------------------
mkdir -p "$CLAUDE_DIR"
cp "$CONFIG_DIR/statusline-command.py"        "$CLAUDE_DIR/statusline-command.py"
cp "$CONFIG_DIR/claude-costs.py"              "$CLAUDE_DIR/claude-costs.py"
# Clean up old files if present.
rm -f "$CLAUDE_DIR/statusline-command.sh"
rm -f "$CLAUDE_DIR/hooks/session-cost-logger.py"

# --- Merge into settings.json (non-destructive) ---------------------------
python3 - "$SETTINGS" << 'MERGE'
import json, sys, os

settings_path = sys.argv[1]

# Our config to merge in.
statusline_cmd = "python3 " + os.path.expanduser("~/.claude/statusline-command.py")
our_statusline = {"type": "command", "command": statusline_cmd}

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

# Clean up old SessionEnd hook if present.
cost_logger_cmd = "python3 " + os.path.expanduser("~/.claude/hooks/session-cost-logger.py")
hooks = settings.get("hooks", {})
if "SessionEnd" in hooks:
    hooks["SessionEnd"] = [
        entry for entry in hooks["SessionEnd"]
        if not any(h.get("command") == cost_logger_cmd for h in (entry.get("hooks") or []))
    ]
    if not hooks["SessionEnd"]:
        del hooks["SessionEnd"]
    if not hooks:
        del settings["hooks"]

with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2, ensure_ascii=False)
    f.write("\n")
MERGE

# --- Summary ---------------------------------------------------------------
printf "\n\033[32mDone!\033[0m\n"
printf "  \033[90m%s\033[0m  %s\n" "statusline" "$CLAUDE_DIR/statusline-command.py"
printf "  \033[90m%s\033[0m  %s\n" "cost summary" "$CLAUDE_DIR/claude-costs.py"
printf "  \033[90m%s\033[0m  %s\n" "settings" "$SETTINGS (merged)"
printf "\nSession costs will be logged to \033[90m%s\033[0m\n" "$CLAUDE_DIR/session-costs.csv"
