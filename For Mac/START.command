#!/bin/bash
cd "$(dirname "$0")/../_engine"

kill $(lsof -ti:5000) 2>/dev/null
sleep 0.5

pip3 install -q --disable-pip-version-check -r requirements.txt 2>/dev/null

echo ""
echo "  ============================================"
echo "   990 Compensation Pipeline is starting..."
echo "  ============================================"
echo ""
echo "  Your browser will open automatically in a few seconds."
echo "  If it does not open, check above in this window for the correct URL."
echo ""
echo "  To stop the server: close this window, or press Control+C."
echo ""

PYTHONWARNINGS=ignore python3 app.py
