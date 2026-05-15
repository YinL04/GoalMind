from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional


class JsonTTLCache:
    def __init__(self, path: str | os.PathLike[str], ttl_seconds: int = 21600) -> None:
        self.path = Path(path)
        self.ttl_seconds = ttl_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def make_key(namespace: str, value: str) -> str:
        digest = hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()
        return f"{namespace}:{digest}"

    def get(self, key: str) -> Optional[Any]:
        data = self._read()
        item = data.get(key)
        if not item:
            return None

        created_at = float(item.get("created_at", 0))
        if time.time() - created_at > self.ttl_seconds:
            data.pop(key, None)
            self._write(data)
            return None

        return item.get("value")

    def set(self, key: str, value: Any) -> None:
        data = self._read()
        data[key] = {"created_at": time.time(), "value": value}
        self._write(data)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)


def default_cache() -> JsonTTLCache:
    cache_path = os.getenv("FOOTBALL_AGENT_CACHE_PATH", ".cache/football_agent_cache.json")
    ttl_seconds = int(os.getenv("FOOTBALL_AGENT_CACHE_TTL_SECONDS", "21600"))
    return JsonTTLCache(cache_path, ttl_seconds=ttl_seconds)
