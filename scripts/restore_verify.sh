#!/usr/bin/env bash
# SPYDER-DETECT Backup Integrity & Ephemeral Restore Verification Script
set -euo pipefail

BACKUP_DIR="${1:?Usage: restore_verify.sh <backup_dir>}"
TEST_DB_URL="${VERIFY_DATABASE_URL:-}"

echo "[1/3] Verifying SHA-256 manifest in ${BACKUP_DIR}..."
(
  cd "${BACKUP_DIR}"
  sha256sum -c SHA256SUMS
)

DUMP_FILE="${BACKUP_DIR}/postgres_spyder.dump"
if [ ! -f "${DUMP_FILE}" ]; then
  echo "[ERROR] Missing ${DUMP_FILE}" >&2
  exit 1
fi

echo "[2/3] Checking archive table of contents via pg_restore -l..."
pg_restore -l "${DUMP_FILE}" >/dev/null

if [ -n "${TEST_DB_URL}" ]; then
  echo "[3/3] Restoring into verification database and counting core records..."
  pg_restore --clean --if-exists --no-owner --dbname="${TEST_DB_URL}" "${DUMP_FILE}"
  psql "${TEST_DB_URL}" -c "SELECT count(*) AS cases_count FROM cases; SELECT count(*) AS audit_count FROM audit_events;"
else
  echo "[3/3] Skipping live pg_restore (set VERIFY_DATABASE_URL to test full SQL restore)."
fi

echo "Restore verification succeeded."
