#!/bin/bash
# Hook: remind model to always decompose work into trackable subtasks
# Event: UserPromptSubmit
# Always injects a reminder to use TodoWrite for task tracking

cat <<'EOF'
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "TASK DECOMPOSITION: Before starting any implementation work, break it down into discrete subtasks using TodoWrite. Each subtask should be independently completable and testable. Mark subtasks in_progress when starting, completed when done. This applies especially after a plan has been approved."
  }
}
EOF
