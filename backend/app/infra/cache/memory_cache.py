import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Iterable, Optional

from app.domain.interfaces.cache import ICache


class InMemoryCache(ICache):
    """Cache trong RAM của tiến trình, có thời hạn cho từng key, đầy thì bỏ theo LRU.

    Endpoint đồng bộ của FastAPI chạy song song trong threadpool nên mọi thao tác
    đều khóa. Mỗi worker uvicorn có một bản riêng: chỉ đúng khi chạy MỘT worker.
    """

    def __init__(self, max_entries: int = 50_000):
        # Thứ tự trong OrderedDict = thứ tự dùng gần nhất; đầu danh sách là lâu nhất không ai dùng
        self._data: "OrderedDict[str, tuple]" = OrderedDict()
        self._lock = threading.Lock()
        self._max_entries = max_entries
        # Đếm để đo tỉ lệ trúng cache khi đo hiệu năng (/health)
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._get_locked(key, time.monotonic())

    def get_many(self, keys: Iterable[str]) -> Dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            found = {}
            for key in keys:
                value = self._get_locked(key, now)
                if value is not None:
                    found[key] = value
            return found

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        with self._lock:
            self._data[key] = (value, time.monotonic() + ttl_seconds)
            self._data.move_to_end(key)
            # Đầy thì bỏ mục lâu nhất không ai dùng (LRU), giữ lại mục đang được dùng nhiều
            while len(self._data) > self._max_entries:
                self._data.popitem(last=False)
                self.evictions += 1

    def delete(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._data.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        with self._lock:
            for key in [k for k in self._data if k.startswith(prefix)]:
                del self._data[key]

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "entries": len(self._data),
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
                "hit_rate": round(self.hits / total, 4) if total else None,
            }

    def _get_locked(self, key: str, now: float) -> Optional[Any]:
        entry = self._data.get(key)
        if entry is None:
            self.misses += 1
            return None
        value, expires_at = entry
        if expires_at <= now:
            del self._data[key]
            self.misses += 1
            return None
        self._data.move_to_end(key)
        self.hits += 1
        return value
