#!/bin/bash
cd "$(dirname "$0")"

# Use the same Python the Mac app looks for (python.org, then Homebrew, then PATH)
PYTHON=""
for p in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 \
         /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3)"; do
    if [ -x "$p" ] && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
        PYTHON="$p"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "Python 3.10 or newer was not found. Install it from python.org, then try again."
    read -rp "Press Enter to close."
    exit 1
fi

# Downloaded files are quarantined, which makes macOS run the Mac app from a
# temporary copy where it can't find the app files. This folder is trusted now.
xattr -dr com.apple.quarantine . 2>/dev/null

if ! "$PYTHON" -c "import PySide6, pdfplumber, pandas" >/dev/null 2>&1; then
    echo "First-time setup: installing required libraries. This can take a few minutes..."
    if ! "$PYTHON" -m pip install -r requirements.txt; then
        echo
        echo "Setup failed. Take a screenshot of this window and send it for help."
        read -rp "Press Enter to close."
        exit 1
    fi
fi

"$PYTHON" gui.py
