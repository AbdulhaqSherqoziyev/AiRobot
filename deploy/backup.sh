#!/usr/bin/env bash
# Daily backup. Cron: 0 3 * * * /opt/airobot/deploy/backup.sh >> /var/log/quantlab-backup.log 2>&1
# It holds encrypted API keys, so keep it off the public internet. QL_SECRET_KEY is required to
# read them and is deliberately not in the backup: store it separately.
set -euo pipefail
cd "$(dirname "$0")"
DEST="${BACKUP_DIR:-/var/backups/quantlab}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$DEST"
docker compose exec -T postgres pg_dump -U quantlab -d quantlab -Fc > "$DEST/db-$STAMP.dump"
docker compose run --rm --no-deps -T --entrypoint tar api -C /data -czf - models > "$DEST/models-$STAMP.tgz"
find "$DEST" -type f -mtime +"${KEEP_DAYS:-14}" -delete
# Candles are not backed up: `python -m quantlab.cli download` can restore them from Binance.
echo "backup ok: $STAMP"
