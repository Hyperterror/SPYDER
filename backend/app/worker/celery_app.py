"""
Durable Celery application configuration with safe local fallback when Celery
is not installed in minimal unit-test environments.
"""
from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    from celery import Celery  # type: ignore

    celery_app = Celery(
        "spyder_worker",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=["app.worker.tasks"],
    )
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
        task_eager_propagates=False,
        broker_connection_retry_on_startup=True,
    )
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    _LOCAL_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="spyder-worker")

    class _LocalAsyncResult:
        def __init__(self, task_id: str):
            self.id = task_id

    class _LocalTask:
        def __init__(self, fn: Callable[..., Any], name: str):
            self.fn = fn
            self.name = name

        def __call__(self, *args, **kwargs):
            return self.fn(None, *args, **kwargs)

        def delay(self, *args, **kwargs) -> _LocalAsyncResult:
            tid = f"local-{uuid.uuid4().hex[:12]}"
            if settings.CELERY_TASK_ALWAYS_EAGER:
                self.fn(None, *args, **kwargs)
            else:
                _LOCAL_POOL.submit(self.fn, None, *args, **kwargs)
            return _LocalAsyncResult(tid)

    class _FallbackCelery:
        def task(self, *d_args, **d_kwargs):
            name = d_kwargs.get("name", "local_task")
            def _decorator(fn: Callable[..., Any]):
                return _LocalTask(fn, name)
            return _decorator

    celery_app = _FallbackCelery()  # type: ignore[assignment]
