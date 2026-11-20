#!/usr/bin/env bash
# Start Heckle & Hint on this computer (Mac / Linux). Needs Python 3.10+.
set -e
cd "$(dirname "$0")"
python3 -m pip install -q -r backend/requirements.txt
echo ""
echo "  Heckle & Hint is running:  http://localhost:8000"
echo "  Phones on the same Wi-Fi:  http://$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}'):8000"
echo "  Stop with Ctrl+C"
echo ""
python3 -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
