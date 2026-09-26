"""Configuration and local preferences exposed to the desktop UI."""

import os

import webview

from skillhub.domain.global_targets import (
    DEFAULT_GLOBAL_SKILL_TARGETS,
    GLOBAL_SKILL_TARGETS,
)
from skillhub.infrastructure.config_repository import ConfigRepository, valid_config
from skillhub.infrastructure.json_store import file_lock, recover_json
from skillhub.settings import (
    APP_DIR,
    APP_VERSION,
    CONFIG_PATH,
    LEGACY_CONFIG_PATHS,
)


class ConfigurationApiMixin:
    """Manage persisted desktop configuration."""

    @staticmethod
    def _config_repository() -> ConfigRepository:
        return ConfigRepository(
            CONFIG_PATH,
            APP_DIR,
            DEFAULT_GLOBAL_SKILL_TARGETS,
            LEGACY_CONFIG_PATHS,
        )

    def _load_config(self) -> dict:
        repository = self._config_repository()
        try:
            return repository.load()
        except Exception as error:
            self._config_load_error = str(error)
            return repository.defaults()

    def _config_snapshot(self):
        keys = ("skills_dir", "projects", "language", "theme", "default_scan_dir",
                "deepseek_api_key", "deepseek_model", "api_base",
                "ai_import_optimization", "ai_display_translation", "global_skill_targets")
        return {key: getattr(self, key) for key in keys}

    def _save_config(self):
        return self._config_repository().save(self._config_snapshot())

    def _commit_config(self, changes):
        with file_lock(CONFIG_PATH):
            candidate = self._config_snapshot()
            candidate.update(changes)
            if not self._config_repository().save(candidate):
                return {"error": "配置保存失败，原设置已保留。请检查权限或恢复备份。 / Settings were not saved."}
            for key, value in changes.items():
                setattr(self, key, value)
            return {"ok": True}

    def recover_config(self):
        try:
            result = recover_json(CONFIG_PATH, valid_config)
            for key, value in self._config_repository().load().items():
                if key in self._config_snapshot():
                    setattr(self, key, value)
            self._config_load_error = ""
            return result
        except OSError as error:
            return {"error": str(error)}

    def get_config(self):
        """Return the current system configuration (skills_dir, projects)."""
        os.makedirs(self.skills_dir, exist_ok=True)
        return {
            "app_version": APP_VERSION,
            "storage_warning": getattr(self, "_config_load_error", ""),
            "skills_dir": self.skills_dir,
            "projects": self.projects,
            "language": self.language,
            "theme": self.theme,
            "default_scan_dir": self.default_scan_dir,
            "deepseek_api_key": "***" if self.deepseek_api_key else "",
            "deepseek_model": self.deepseek_model,
            "api_base": self.api_base,
            "has_ai_key": bool(self.deepseek_api_key),
            "api_key_hint": (
                f"••••{self.deepseek_api_key[-4:]}"
                if self.deepseek_api_key
                else ""
            ),
            "ai_import_optimization": self.ai_import_optimization,
            "ai_display_translation": self.ai_display_translation,
            "global_skill_targets": self._configured_global_target_ids(),
            "global_skill_target_options": self._global_skill_target_options(),
        }

    def change_skills_dir(self):
        """Open native folder picker and change the Global Skill Library path."""
        try:
            result = self._window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=self.skills_dir if os.path.isdir(self.skills_dir) else "C:\\"
            )
        except Exception:
            result = None
        if not result or len(result) == 0:
            return None
        new_path = os.path.normpath(result[0])
        return self.save_settings({"skills_dir": new_path})

    def pick_default_scan_dir(self):
        """Open native folder picker and select Default Projects starting directory."""
        try:
            result = self._window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=self.default_scan_dir if os.path.isdir(self.default_scan_dir) else "C:\\"
            )
        except Exception:
            result = None
        if not result or len(result) == 0:
            return None
        new_path = os.path.normpath(result[0])
        return self.save_settings({"default_scan_dir": new_path})

    def save_settings(self, settings):
        if not isinstance(settings, dict):
            return {"error": "Invalid settings"}
        changes = {}
        for key in ("skills_dir", "default_scan_dir"):
            if key in settings:
                if not isinstance(settings[key], str) or not os.path.isabs(settings[key]):
                    return {"error": "Select an absolute directory"}
                changes[key] = os.path.normpath(settings[key])
        for key, allowed in (("language", ("zh", "en")), ("theme", ("light", "dark"))):
            if key in settings:
                if settings[key] not in allowed:
                    return {"error": "Invalid " + key}
                changes[key] = settings[key]
        for key in ("ai_import_optimization", "ai_display_translation"):
            if key in settings:
                if not isinstance(settings[key], bool):
                    return {"error": "Invalid " + key}
                changes[key] = settings[key]
        for key in ("deepseek_model", "api_base", "deepseek_api_key"):
            if key in settings:
                if not isinstance(settings[key], str):
                    return {"error": "Invalid AI settings"}
                if key == "api_base" and not settings[key].startswith(("https://", "http://")):
                    return {"error": "API URL must use HTTP or HTTPS"}
                if settings[key]:
                    changes[key] = settings[key]
        if "global_skill_targets" in settings:
            targets = self._normalize_global_skill_targets(settings["global_skill_targets"])
            if not targets:
                return {"error": "Select at least one global Skill target"}
            unavailable = [t for t in targets if not self._global_skill_target_available(t)]
            if unavailable:
                return {"error": "Agent Skill directories were not detected: " + ", ".join(unavailable)}
            changes["global_skill_targets"] = targets
        try:
            if "skills_dir" in changes:
                os.makedirs(changes["skills_dir"], exist_ok=True)
            result = self._commit_config(changes)
        except OSError as error:
            return {"error": str(error)}
        return result if result.get("error") else self.get_config()

    def save_ai_config(self, api_key, model="deepseek-chat", api_base="https://api.deepseek.com/v1", clear_key=False):
        if not all(isinstance(value, str) for value in (api_key, model, api_base)):
            return {"error": "Invalid AI settings"}
        if api_base and not api_base.startswith(("https://", "http://")):
            return {"error": "API URL must use HTTP or HTTPS"}
        result = self._commit_config({
            "deepseek_api_key": "" if clear_key else (api_key or self.deepseek_api_key),
            "deepseek_model": model or self.deepseek_model,
            "api_base": api_base or self.api_base,
        })
        if result.get("error"):
            return result
        return {"ok": True, "has_ai_key": bool(self.deepseek_api_key),
                "api_key_hint": "••••" + self.deepseek_api_key[-4:] if self.deepseek_api_key else ""}
