import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class CacheEntry:
    value: dict
    expiry: float


class SearchCache:
    def __init__(self, ttl_seconds: int = 300, max_entries: int = 100):
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()

    def _make_key(self, query: str, engines: str | None, page: int, count: int) -> str:
        return f"{query}|{engines or ''}|{page}|{count}"

    def _purge_expired(self) -> None:
        now = time.time()
        for key, entry in list(self._cache.items()):
            if entry.expiry <= now:
                del self._cache[key]

    def get(self, query: str, engines: str | None, page: int, count: int) -> dict | None:
        key = self._make_key(query, engines, page, count)
        now = time.time()

        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._purge_expired()
                logger.info("Cache miss")
                return None

            if entry.expiry <= now:
                del self._cache[key]
                logger.info("Cache expired")
                return None

            self._cache.move_to_end(key)
            logger.info("Cache hit")
            return entry.value

    def set(self, query: str, engines: str | None, page: int, count: int, value: dict) -> None:
        key = self._make_key(query, engines, page, count)
        expiry = time.time() + self._ttl_seconds

        with self._lock:
            self._purge_expired()
            self._cache[key] = CacheEntry(value=value, expiry=expiry)
            self._cache.move_to_end(key)

            if len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)


search_cache = SearchCache()
