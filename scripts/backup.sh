#!/usr/bin/env bash
set -euo pipefail

# Backup PostgreSQL database and upload to S3
# Usage: ./scripts/backup.sh [DATABASE_URL]
# Requires: pg_dump, aws-cli, configured S3 env vars

DATABASE_URL="${1:-${DATABASE_URL:-}}"
S3_BUCKET="${S3_BUCKET:-lms-conteudos}"
BACKUP_DIR="/tmp/lms-backups"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="lms_idesp_${TIMESTAMP}.sql.gz"
S3_PATH="backups/${FILENAME}"

if [ -z "$DATABASE_URL" ]; then
    echo "ERROR: DATABASE_URL not set. Pass as argument or set environment variable."
    echo "Usage: $0 postgresql://user:pass@host:port/dbname"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

echo "Dumping database to ${BACKUP_DIR}/${FILENAME}..."
pg_dump "$DATABASE_URL" --schema=lms --no-owner | gzip > "${BACKUP_DIR}/${FILENAME}"

echo "Uploading to s3://${S3_BUCKET}/${S3_PATH}..."
aws s3 cp "${BACKUP_DIR}/${FILENAME}" "s3://${S3_BUCKET}/${S3_PATH}"

echo "Cleaning local backup..."
rm "${BACKUP_DIR}/${FILENAME}"

echo "Cleaning old backups (>${RETENTION_DAYS} days)..."
aws s3 ls "s3://${S3_BUCKET}/backups/" | while read -r line; do
    date_part=$(echo "$line" | awk '{print $1" "$2}')
    file_date=$(date -d "$date_part" +%s 2>/dev/null || true)
    if [ -n "$file_date" ]; then
        age=$(( ($(date +%s) - file_date) / 86400 ))
        if [ "$age" -gt "$RETENTION_DAYS" ]; then
            filename=$(echo "$line" | awk '{print $4}')
            echo "  Removing expired: ${filename}"
            aws s3 rm "s3://${S3_BUCKET}/backups/${filename}"
        fi
    fi
done

echo "Backup complete: s3://${S3_BUCKET}/${S3_PATH}"
