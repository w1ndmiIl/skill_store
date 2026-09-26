"""Validated chat persistence; one transaction covers read, edit and write."""
import copy
import os
from .json_store import file_lock, read_json, write_json, recover_json

def valid_sessions(value):
    return (isinstance(value, list) and all(
        isinstance(s, dict) and isinstance(s.get("id"), str) and bool(s["id"])
        and isinstance(s.get("title", ""), str)
        and isinstance(s.get("created_at", ""), str)
        and isinstance(s.get("updated_at", ""), str)
        and isinstance(s.get("messages"), list)
        and all(isinstance(m, dict) and m.get("role") in ("user", "assistant", "system")
                and isinstance(m.get("content"), str) for m in s["messages"])
        for s in value) and len({s["id"] for s in value}) == len(value))

class ChatSessionRepository:
    _cache = {}
    def __init__(self, path):
        self.path = path
    def transaction(self):
        return file_lock(self.path)
    def load(self):
        with self.transaction():
            return copy.deepcopy(self._read_cached())
    def summaries(self, language="zh"):
        with self.transaction():
            return [{"id": s["id"], "title": s.get("title") or ("新会话" if language == "zh" else "New Chat"), "created_at": s.get("created_at", ""), "updated_at": s.get("updated_at", s.get("created_at", "")), "msg_count": len(s["messages"])} for s in sorted(self._read_cached(), key=lambda s: s.get("updated_at", s.get("created_at", "")), reverse=True)]
    def session(self, session_id):
        with self.transaction():
            return copy.deepcopy(next((s for s in self._read_cached() if s["id"] == session_id), None))
    def _read_cached(self):
        with self.transaction():
            try:
                stat = os.stat(self.path)
                signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            except FileNotFoundError:
                return []
            cached = self._cache.get(self.path)
            if cached and cached[0] == signature:
                return cached[1]
            value = read_json(self.path, [], valid_sessions)
            if len(self._cache) >= 16:
                self._cache.pop(next(iter(self._cache)))
            self._cache[self.path] = (signature, value)
            return value
    def save(self, sessions):
        try:
            write_json(self.path, sessions, valid_sessions)
            self._cache.pop(self.path, None)
            return True
        except (OSError, ValueError):
            return False
    def recover(self):
        result = recover_json(self.path, valid_sessions)
        self._cache.pop(self.path, None)
        return result
