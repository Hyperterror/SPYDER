#!/usr/bin/env bash
# SPYDER-DETECT PostgreSQL + MinIO Forensic Backup Script
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-./backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET_DIR="${BACKUP_ROOT}/${STAMP}"
mkdir -p "${TARGET_DIR}"

echo "[1/3] Dumping PostgreSQL database..."
pg_dump "${DATABASE_URL:?DATABASE_URL must be set}" --format=custom --no-owner \
  --file="${TARGET_DIR}/postgres_spyder.dump"

echo "[2/3] Mirroring MinIO / local evidence bucket..."
if command -v mc >/dev/null 2>&1 && [ -n "${MINIO_ALIAS:-}" ]; then
  mc mirror "${MINIO_ALIAS}/${MINIO_BUCKET:-evidence}" "${TARGET_DIR}/evidence_objects"
elif [ -d "./backend/local_evidence_store" ]; then
  cp -R "./backend/local_evidence_store" "${TARGET_DIR}/local_evidence_store"
else
  echo "[WARN] Neither mc alias nor local_evidence_store found; skipping object mirror"
fi

echo "[3/3] Writing SHA-256 backup manifest..."
(
  cd "${TARGET_DIR}"
  find . -type f ! -name 'SHA256SUMS' -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)

echo "Backup complete: ${TARGET_DIR}"
