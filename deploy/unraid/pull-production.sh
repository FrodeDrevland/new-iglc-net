#!/bin/bash
# Weekly copy of the production database (Azure) to the Unraid server.
#
# 1. Keeps a dated dump in $APPDATA/backups (the last $KEEP are kept) - an off-site backup
#    in addition to Azure's own 35 days of backups.
# 2. With --restore, also loads it into the preview database, so the preview has current data.
#
# Needs PROD_DATABASE_URL in $APPDATA/src/.env.prod, for example
#   PROD_DATABASE_URL=postgresql://iglcadmin:PASSWORD@iglc-db.postgres.database.azure.com:5432/iglc?sslmode=require
# and this server's public IP allowed in the Azure database firewall.
# Run it from Unraid's User Scripts plugin, for example weekly.
set -euo pipefail

APPDATA=${APPDATA:-/mnt/user/appdata/iglc}
KEEP=${KEEP:-8}
PROD_DATABASE_URL=$(grep -E '^PROD_DATABASE_URL=' "$APPDATA/src/.env.prod" | cut -d= -f2-)
[ -n "$PROD_DATABASE_URL" ] || { echo "PROD_DATABASE_URL is not set in .env.prod"; exit 1; }

mkdir -p "$APPDATA/backups"
FILE="$APPDATA/backups/iglc-$(date +%Y-%m-%d).dump"

docker run --rm postgres:16 pg_dump --format=custom --no-owner --no-privileges "$PROD_DATABASE_URL" > "$FILE"
echo "Saved $FILE ($(du -h "$FILE" | cut -f1))"

ls -1t "$APPDATA"/backups/iglc-*.dump | tail -n +$((KEEP + 1)) | xargs -r rm --

if [ "${1:-}" = "--restore" ]; then
    docker exec -i iglc-db pg_restore --clean --if-exists --no-owner -U iglc -d iglc < "$FILE"
    echo "Restored into the preview database."
fi
