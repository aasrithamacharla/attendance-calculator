#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "==============================================="
echo " Starting Attendance Web Server                "
echo "==============================================="

python3 database.py
python3 app.py
