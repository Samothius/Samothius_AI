#!/usr/bin/env bash
set -e

cd ~/samothius_ai
source .venv/bin/activate

echo "1) Syntax check..."
python3 -m py_compile games.py database.py

echo "2) Service restart..."
sudo systemctl restart samothius-twitch

echo "3) Service status..."
sudo systemctl status samothius-twitch --no-pager -l | sed -n '1,20p'

echo "4) Latest logs..."
journalctl -u samothius-twitch -n 20 --no-pager

echo "✅ Deployment complete."
