"""
Storage service — MinIO when available, local filesystem fallback otherwise.
This lets the backend run fully without MinIO for local development/demo.
"""
import io
import os
from pathlib import Path
from app.core.config import settings


class StorageService:
    def __init__(self):
        self.bucket = settings.MINIO_BUCKET
        self._local_mode = False
        self._local_root = Path(__file__).resolve().parents[3] / "local_storage"

        # Try to connect to MinIO; fall back to local filesystem silently
        try:
            from minio import Minio
            from minio.error import S3Error
            self._client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE,
            )
            # Test connectivity with a short timeout
            self._ensure_bucket()
            print("[OK] MinIO connected")
        except Exception as e:
            print(f"[WARN] MinIO not available, using local filesystem storage: {e}")
            self._client = None
            self._local_mode = True
            self._local_root.mkdir(parents=True, exist_ok=True)

    def _ensure_bucket(self):
        from minio.error import S3Error
        try:
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)
        except S3Error:
            pass

    def upload(self, object_key: str, file_bytes: bytes, content_type: str = "application/octet-stream") -> str:
        if self._local_mode:
            dest = self._local_root / object_key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(file_bytes)
            return object_key

        self._client.put_object(
            self.bucket,
            object_key,
            io.BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=content_type,
        )
        return object_key

    def download(self, bucket: str, object_key: str) -> bytes:
        if self._local_mode:
            dest = self._local_root / object_key
            if dest.exists():
                return dest.read_bytes()
            raise FileNotFoundError(f"Local storage file not found: {object_key}")

        response = self._client.get_object(bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def presigned_get_url(self, object_key: str, expires_seconds: int = 3600) -> str:
        if self._local_mode:
            return f"/local-storage/{object_key}"

        from datetime import timedelta
        return self._client.presigned_get_object(
            self.bucket,
            object_key,
            expires=timedelta(seconds=expires_seconds),
        )


_storage_instance: StorageService | None = None


def get_storage() -> StorageService:
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = StorageService()
    return _storage_instance
