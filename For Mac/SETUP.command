#!/bin/bash
cd "$(dirname "$0")/../_engine"

echo ""
echo "  ============================================"
echo "   990 Pipeline -- Mac Setup"
echo "  ============================================"
echo ""
echo "  Checking your computer has everything needed..."
echo "  This only needs to be run ONCE."
echo ""

if ! command -v python3 &>/dev/null; then
    echo "  [!] Python 3 is not installed."
    echo ""
    echo "  Install it from: https://www.python.org/downloads/"
    echo "  Then run SETUP.command again."
    echo ""
    open "https://www.python.org/downloads/"
    read -p "  Press Enter to close..."
    exit 1
fi

python3 --version
echo ""
echo "  Installing required libraries..."
echo "  (This may take 1-2 minutes on first run)"
echo ""

pip3 install -r requirements.txt --quiet --disable-pip-version-check

if [ $? -ne 0 ]; then
    echo ""
    echo "  [!] Something went wrong installing libraries."
    echo "  Try running: sudo pip3 install -r requirements.txt"
    echo ""
    read -p "  Press Enter to close..."
    exit 1
fi

echo ""
echo "  ============================================"
echo "   Setup complete!"
echo "  ============================================"
echo ""
echo "  Double-click START.command to run the pipeline."
echo ""
read -p "  Press Enter to close..."
