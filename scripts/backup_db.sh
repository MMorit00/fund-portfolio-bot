#!/usr/bin/env bash
set -euo pipefail

DB_PATH=${1:-data/portfolio.db}
TS=$(date +"%Y%m%d-%H%M%S")
DEST="data/portfolio-${TS}.db"

if [ ! -f "$DB_PATH" ]; then
  echo "DB not found: $DB_PATH" >&2
  exit 2
fi

cp "$DB_PATH" "$DEST"
echo "Backup created: $DEST"

