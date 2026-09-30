#!/bin/bash
cd "$(dirname "$0")"

if ! python3 -c "import PySide6, pdfplumber, pandas" >/dev/null 2>&1; then
    echo "First-time setup: installing required libraries. This can take a few minutes..."
    if ! python3 -m pip install -r requirements.txt; then
        echo
        echo "Setup failed. Take a screenshot of this window and send it for help."
        read -rp "Press Enter to close."
        exit 1
    fi
fi

python3 gui.py
