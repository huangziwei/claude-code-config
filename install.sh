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
  git clone --depth 1 https://github.com/huangziwei/claude-costs.git "$REPO_DIR" 2>/dev/null
fi

CONFIG_DIR="$REPO_DIR/config"

# Detect install vs update.
if [ -f "$CLAUDE_DIR/statusline-command.py" ]; then
  ACTION="Updating"
else
  ACTION="Installing"
fi

printf "\033[1m%s Claude Code config...\033[0m\n\n" "$ACTION"

# --- Find a working python3 -----------------------------------------------
# macOS system python3 (/usr/bin/python3) is a shim that requires Xcode CLT.
# Prefer Homebrew or other standalone installs that always work.
PYTHON3=""
for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
  if command -v "$candidate" &>/dev/null && "$candidate" -c "pass" 2>/dev/null; then
    PYTHON3="$(command -v "$candidate")"
    break
  fi
done
if [ -z "$PYTHON3" ]; then
  printf "\033[31mError: no working python3 found.\033[0m\n" >&2
  exit 1
fi

# --- Copy config files into ~/.claude/ ------------------------------------
mkdir -p "$CLAUDE_DIR"
cp "$CONFIG_DIR/statusline-command.py"        "$CLAUDE_DIR/statusline-command.py"
# Clean up old files if present.
rm -f "$CLAUDE_DIR/statusline-command.sh"
rm -f "$CLAUDE_DIR/hooks/session-cost-logger.py"
rm -f "$CLAUDE_DIR/claude-costs.py"

# --- Install claude-costs TUI via uv tool ---------------------------------
if command -v uv &>/dev/null; then
  printf "Installing claude-costs tool...\n"
  uv tool install --force --reinstall "$REPO_DIR"
fi

# --- Merge into settings.json (non-destructive) ---------------------------
"$PYTHON3" - "$SETTINGS" "$PYTHON3" << 'MERGE'
import json, sys, os

settings_path = sys.argv[1]
python3_path = sys.argv[2]

# Our config to merge in.
statusline_cmd = python3_path + " " + os.path.expanduser("~/.claude/statusline-command.py")
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
printf "  \033[90m%s\033[0m  %s\n" "settings" "$SETTINGS (merged)"
if command -v claude-costs &>/dev/null; then
  printf "  \033[90m%s\033[0m  %s\n" "claude-costs" "installed (run 'claude-costs' for interactive TUI)"
else
  printf "\n  To install the cost tracker TUI:\n"
  printf "    \033[90muv tool install git+https://github.com/huangziwei/claude-costs.git\033[0m\n"
fi
printf "\nSession costs will be logged to \033[90m%s\033[0m\n" "$CLAUDE_DIR/session-costs.csv"
