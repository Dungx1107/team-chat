import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

import redis

from app.domain.interfaces.cache import ICache
from app.infra.cache.memory_cache import _stats_dict

logger = logging.getLogger(__name__)

_KEY_PREFIX = "tc:cache:"
_STATS_PREFIX = "tc:stats:"
_STAT_NAMES = ("hits", "misses", "requests", "full_hits")


def _encode(value: Any) -> str:
    def default(obj):
        if isinstance(obj, datetime):
            return {"__dt__": obj.isoformat()}
        raise TypeError(f"Không lưu được kiểu {type(obj).__name__} vào cache")
    return json.dumps(value, default=default, ensure_ascii=False)


def _decode(raw: bytes) -> Any:
    def hook(obj):
        if len(obj) == 1 and "__dt__" in obj:
            return datetime.fromisoformat(obj["__dt__"])
        return obj
    return json.loads(raw, object_hook=hook)


class RedisCache(ICache):
    """Cache dùng chung cho mọi worker, lưu trên Redis.

    Cần khi chạy nhiều worker: xóa một key là đúng cho tất cả, khác với bản trong RAM.

    Giá trị lưu dạng JSON, không dùng pickle: ai ghi được vào Redis cũng không chạy
    được code trên server. Mọi lỗi Redis đều coi như trượt cache, nên Redis sập thì
    ứng dụng vẫn chạy (chậm hơn vì mọi request hỏi thẳng DB) -- cache không bao giờ
    được làm hệ thống chết.

    Circuit Breaker: một lần thử kết nối tới Redis đã sập có thể mất vài giây (phân
    giải tên máy không theo socket timeout), mà một request gọi cache vài lần. Nên
    sau lỗi đầu tiên, NGỪNG gọi Redis trong BREAK_SECONDS và trả "trượt cache" ngay;
    hết thời gian thì thử lại một lần, được thì dùng tiếp.
    """

    BREAK_SECONDS = 5.0

    def __init__(self, url: str, timeout_seconds: float = 0.5):
        self.client = redis.Redis.from_url(
            url, socket_timeout=timeout_seconds, socket_connect_timeout=timeout_seconds
        )
        self._last_error_log = 0.0
        self._open_until = 0.0

    def _available(self) -> bool:
        return time.monotonic() >= self._open_until

    def _failed(self, action: str, exc: Exception) -> None:
        now = time.monotonic()
        self._open_until = now + self.BREAK_SECONDS
        # Redis sập thì lỗi lặp lại liên tục: chỉ ghi log mỗi 30 giây một lần
        if now - self._last_error_log > 30:
            self._last_error_log = now
            logger.warning("Redis cache lỗi khi %s, coi như trượt cache và ngừng gọi Redis %.0f s: %s",
                           action, self.BREAK_SECONDS, exc)

    def get(self, key: str) -> Optional[Any]:
        return self.get_many([key]).get(key)

    def get_many(self, keys: Iterable[str]) -> Dict[str, Any]:
        keys = list(keys)
        if not keys or not self._available():
            return {}
        try:
            raws = self.client.mget([_KEY_PREFIX + k for k in keys])
            found = {k: _decode(raw) for k, raw in zip(keys, raws) if raw is not None}
            pipe = self.client.pipeline(transaction=False)
            pipe.incrby(_STATS_PREFIX + "hits", len(found))
            pipe.incrby(_STATS_PREFIX + "misses", len(keys) - len(found))
            pipe.execute()
            return found
        except redis.RedisError as exc:
            self._failed("đọc", exc)
            return {}

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if not self._available():
            return
        try:
            # Redis tự xóa khi hết hạn; đầy bộ nhớ thì bỏ theo chính sách maxmemory của Redis
            self.client.set(_KEY_PREFIX + key, _encode(value), ex=max(1, int(ttl_seconds)))
        except redis.RedisError as exc:
            self._failed("ghi", exc)

    def delete(self, *keys: str) -> None:
        if not keys or not self._available():
            return
        try:
            self.client.delete(*[_KEY_PREFIX + k for k in keys])
        except redis.RedisError as exc:
            self._failed("xóa", exc)

    def delete_prefix(self, prefix: str) -> None:
        if not self._available():
            return
        try:
            batch = []
            for key in self.client.scan_iter(match=_KEY_PREFIX + prefix + "*", count=500):
                batch.append(key)
                if len(batch) >= 500:
                    self.client.delete(*batch)
                    batch = []
            if batch:
                self.client.delete(*batch)
        except redis.RedisError as exc:
            self._failed("xóa theo tiền tố", exc)

    def record_request(self, full_hit: bool) -> None:
        if not self._available():
            return
        try:
            pipe = self.client.pipeline(transaction=False)
            pipe.incr(_STATS_PREFIX + "requests")
            if full_hit:
                pipe.incr(_STATS_PREFIX + "full_hits")
            pipe.execute()
        except redis.RedisError as exc:
            self._failed("đếm", exc)

    def stats(self) -> dict:
        try:
            values = self.client.mget([_STATS_PREFIX + n for n in _STAT_NAMES])
            counts = {n: int(v or 0) for n, v in zip(_STAT_NAMES, values)}
            return _stats_dict(counts["hits"], counts["misses"], counts["requests"], counts["full_hits"],
                               backend="redis")
        except redis.RedisError as exc:
            return {"backend": "redis", "error": str(exc)}
