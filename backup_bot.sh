#!/usr/bin/env bash
set -e

PROJECT_DIR="/root/samothius_ai"
BACKUP_DIR="/root/backups"
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR"

TS=$(date +%F_%H-%M-%S)
WORK_DIR="$BACKUP_DIR/samothius_ai_$TS"

mkdir -p "$WORK_DIR"

cp -a "$PROJECT_DIR"/*.py "$WORK_DIR"/ 2>/dev/null || true
cp -a "$PROJECT_DIR"/.env "$WORK_DIR"/ 2>/dev/null || true
cp -a "$PROJECT_DIR"/requirements.txt "$WORK_DIR"/ 2>/dev/null || true
cp -a "$PROJECT_DIR"/deploy_twitch.sh "$WORK_DIR"/ 2>/dev/null || true

cp -a "$PROJECT_DIR"/economy.db* "$WORK_DIR"/ 2>/dev/null || true

tar -czf "$BACKUP_DIR/samothius_ai_$TS.tar.gz" -C "$BACKUP_DIR" "samothius_ai_$TS"
rm -rf "$WORK_DIR"

find "$BACKUP_DIR" -type f -name "samothius_ai_*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "[$(date)] Backup complete: $BACKUP_DIR/samothius_ai_$TS.tar.gz"
