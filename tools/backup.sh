#!/usr/bin/env bash
#
# Local backup of the Retro Hardware Database.
#
# Writes two timestamped files into ./backups (override with RHDB_BACKUP_DIR):
#   db-<stamp>.sql.gz      the whole MariaDB database (computers + parts)
#   images-<stamp>.tgz     the uploaded photos
#
# Restore (into a running stack):
#   gunzip -c backups/db-<stamp>.sql.gz \
#     | docker compose exec -T -e MYSQL_PWD="$DB_ROOT_PASSWORD" db mariadb -uroot
#   docker compose exec -T api tar -xzf - -C /app < backups/images-<stamp>.tgz
#
# Note: .env (DB + login passwords) is config, not data -- keep a copy of it too
# if you want to restore with the same credentials.
set -euo pipefail

cd "$(dirname "$0")/.."
if [ -f .env ]; then
    set -a
    . ./.env
    set +a
fi

DEST="${RHDB_BACKUP_DIR:-backups}"
mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M%S)"
DB="${DB_NAME:-retro}"

echo "==> Dumping database ($DB)"
docker compose exec -T -e MYSQL_PWD="${DB_ROOT_PASSWORD:-}" db \
    mariadb-dump -uroot --single-transaction --databases "$DB" \
    | gzip > "$DEST/db-$STAMP.sql.gz"

echo "==> Archiving photos"
docker compose exec -T api tar -czf - -C /app images > "$DEST/images-$STAMP.tgz"

echo "==> Done:"
ls -lh "$DEST/db-$STAMP.sql.gz" "$DEST/images-$STAMP.tgz" | awk '{print "    " $9 "  (" $5 ")"}'
