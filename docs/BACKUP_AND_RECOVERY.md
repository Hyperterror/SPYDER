# Backup and Recovery Procedures

## 1. Automated Backups
Two reproducible backup scripts are provided:
- **Linux / macOS**: `scripts/backup.sh`
- **Windows PowerShell**: `scripts/backup.ps1`

Each backup captures:
1. Custom-format PostgreSQL dump (`pg_dump --format=custom --no-owner`) into `postgres_spyder.dump`
2. MinIO evidence object mirror (`mc mirror`) or `backend/local_evidence_store`
3. Cryptographic SHA-256 manifest (`SHA256SUMS` / `SHA256SUMS.txt`)

## 2. Verification & Restore Drill
Use `scripts/restore_verify.sh <backup_dir>` to verify:
1. All backed-up files match `SHA256SUMS`.
2. PostgreSQL archive structure parses cleanly (`pg_restore -l`).
3. When `VERIFY_DATABASE_URL` is configured, restores into a scratch/ephemeral PostgreSQL database and validates `cases` & `audit_events` counts.

## 3. Knowledge Graph Reconstruction
Neo4j and `output/graphsage/snapshots/` are derived projections. In disaster recovery, restoring PostgreSQL + MinIO restores 100% of authoritative state; running canonical reprocessing or `publish_graph_snapshot()` reconstructs the knowledge graph cleanly without altering original evidence.
