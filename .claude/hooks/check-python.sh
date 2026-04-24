#!/bin/bash
# Check Python syntax after edit
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [[ "$FILE_PATH" == *.py ]] && [[ -f "$FILE_PATH" ]]; then
    python -m py_compile "$FILE_PATH" 2>&1
    if [ $? -ne 0 ]; then
        echo "Python syntax error in $FILE_PATH" >&2
    fi
fi
exit 0
