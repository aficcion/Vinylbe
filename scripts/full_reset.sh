#!/bin/bash

echo "=== FULL RESET SCRIPT ==="
echo ""

# 1. Clean database
echo "1. Cleaning database..."
python3 scripts/cleanup_db.py

# 2. Kill all Python processes on port 5000
echo ""
echo "2. Killing services..."
lsof -ti:5000 | xargs kill -9 2>/dev/null || true
sleep 2

# 3. Restart services
echo ""
echo "3. Restarting services..."
python3 start_services.py > /dev/null 2>&1 &
sleep 3

echo ""
echo "=== RESET COMPLETE ==="
echo ""
echo "NOW IN YOUR BROWSER:"
echo "1. Close ALL incognito windows"
echo "2. Open a NEW incognito window"  
echo "3. Press Cmd+Shift+R (force reload)"
echo "4. In the console, run: localStorage.clear(); location.reload();"
echo "5. Go to http://localhost:5000"
echo "6. Select 3 artists as guest"
echo "7. Login with Last.fm"
echo "8. Send me the console logs with [Sync Debug]"
echo ""
