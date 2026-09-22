"""Explicit recovery of validated backups; damaged originals are retained."""
import os
from skillhub.infrastructure.json_store import read_json, recover_json
from skillhub.infrastructure.config_repository import valid_config
from skillhub.infrastructure.session_repository import valid_sessions
from skillhub.settings import CONFIG_PATH, CHAT_SESSIONS_PATH, AGENT_MEMORY_PATH, AGENT_TASKS_PATH

def memory_valid(v):
    return isinstance(v, dict) and v.get("version") == 1 and isinstance(v.get("projects"), dict) and isinstance(v.get("preferences"), list) and isinstance(v.get("decisions"), list)
def tasks_valid(v):
    return isinstance(v, list) and all(isinstance(t, dict) and isinstance(t.get("run_id"), str) for t in v)

class StorageRecoveryApiMixin:
    def _recovery_sources(self):
        return {"config": (CONFIG_PATH, valid_config), "sessions": (CHAT_SESSIONS_PATH, valid_sessions),
                "memory": (AGENT_MEMORY_PATH, memory_valid), "tasks": (AGENT_TASKS_PATH, tasks_valid)}
    def storage_health(self):
        issues = []
        for kind, (path, validate) in self._recovery_sources().items():
            if not os.path.exists(path):
                continue
            try:
                read_json(path, None, validate)
            except OSError:
                issues.append({"kind": kind, "has_backup": os.path.isfile(path + ".bak")})
        return {"issues": issues}
    def recover_storage(self, kind):
        source = self._recovery_sources().get(kind)
        if not source:
            return {"error": "Unknown storage kind"}
        if any(j["thread"].is_alive() for j in self._background_jobs.jobs.values()):
            return {"error": "请先停止当前任务 / Stop the active task first"}
        try:
            result = recover_json(*source)
            if kind == "config":
                for key, value in self._config_repository().load().items():
                    if key in self._config_snapshot():
                        setattr(self, key, value)
                self._config_load_error = ""
            if kind == "memory":
                self._agent_memory._data = self._agent_memory._load()
                self._agent_memory._load_error = ""
            return result
        except OSError as error:
            return {"error": str(error)}
