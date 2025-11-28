#!/bin/bash

# Session logging hook for Claude Code
# Logs all session activity to .claude/session/<date>.log

LOG_DIR="${CLAUDE_PROJECT_DIR}/.claude/session"
mkdir -p "$LOG_DIR"

# Use date-based log file (one per day)
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).log"

# Helper function to log with timestamp
log_entry() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

case "$CLAUDE_HOOK_EVENT" in
  SessionStart)
    log_entry "==================== SESSION START ===================="
    log_entry "Session ID: ${CLAUDE_SESSION_ID:-unknown}"
    log_entry "Working Directory: $CLAUDE_PROJECT_DIR"
    log_entry "======================================================="
    ;;

  SessionEnd)
    log_entry "==================== SESSION END ======================"
    log_entry "Session ID: ${CLAUDE_SESSION_ID:-unknown}"
    log_entry "======================================================="
    echo "" >> "$LOG_FILE"
    ;;

  PostToolUse)
    log_entry "Tool executed: ${CLAUDE_HOOK_TOOL:-unknown}"
    # Optionally log tool result summary (truncated)
    if [ -n "$CLAUDE_HOOK_RESULT" ]; then
        echo "$CLAUDE_HOOK_RESULT" | head -n 5 >> "$LOG_FILE"
    fi
    ;;

  UserPromptSubmit)
    log_entry "User prompt submitted"
    ;;

  Stop)
    log_entry "Claude response completed"
    ;;
esac
