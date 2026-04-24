#!/bin/bash
# Block running savebot locally — must deploy to server only
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('command',''))" 2>/dev/null)

if echo "$COMMAND" | grep -qE "python.*savebot\.bot|python.*-m savebot|python bot\.py"; then
    echo "BLOCKED: Never run the bot locally! Deploy to server instead." >&2
    echo "Use: /deploy skill or SSH deploy command" >&2
    exit 2
fi
exit 0
