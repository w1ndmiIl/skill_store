"""Configuration and local preferences exposed to the desktop UI."""

import os

import webview

from skillhub.domain.global_targets import (
    DEFAULT_GLOBAL_SKILL_TARGETS,
    GLOBAL_SKILL_TARGETS,
)
from skillhub.infrastructure.config_repository import ConfigRepository
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
        except Exception:
            return repository.defaults()

    def _save_config(self):
        try:
            config = {
                "skills_dir": self.skills_dir,
                "projects": self.projects,
                "language": self.language,
                "theme": self.theme,
                "default_scan_dir": self.default_scan_dir,
                "deepseek_api_key": self.deepseek_api_key,
                "deepseek_model": self.deepseek_model,
                "api_base": self.api_base,
                "ai_import_optimization": self.ai_import_optimization,
                "ai_display_translation": self.ai_display_translation,
                "global_skill_targets": self._configured_global_target_ids(),
            }
            return self._config_repository().save(config)
        except Exception:
            return False

    def get_config(self):
        """Return the current system configuration (skills_dir, projects)."""
        os.makedirs(self.skills_dir, exist_ok=True)
        return {
            "app_version": APP_VERSION,
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
        self.skills_dir = new_path
        self._save_config()
        os.makedirs(self.skills_dir, exist_ok=True)
        return {"skills_dir": self.skills_dir}

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
        self.default_scan_dir = new_path
        self._save_config()
        return {"default_scan_dir": self.default_scan_dir}

    def save_settings(self, settings):
        """Save config settings (skills_dir, language, theme, default_scan_dir)."""
        if "skills_dir" in settings:
            self.skills_dir = os.path.normpath(settings["skills_dir"])
            os.makedirs(self.skills_dir, exist_ok=True)
        if "language" in settings:
            self.language = settings["language"]
        if "theme" in settings:
            self.theme = settings["theme"]
        if "default_scan_dir" in settings:
            self.default_scan_dir = os.path.normpath(settings["default_scan_dir"])
        if "ai_import_optimization" in settings:
            self.ai_import_optimization = bool(
                settings["ai_import_optimization"]
            )
        if "ai_display_translation" in settings:
            self.ai_display_translation = bool(
                settings["ai_display_translation"]
            )
        if "global_skill_targets" in settings:
            targets = self._normalize_global_skill_targets(
                settings["global_skill_targets"]
            )
            if not targets:
                return {"error": "Select at least one global Skill target"}
            unavailable = [
                target_id for target_id in targets
                if not self._global_skill_target_available(target_id)
            ]
            if unavailable:
                labels = ", ".join(
                    GLOBAL_SKILL_TARGETS[target_id]["label"]
                    for target_id in unavailable
                )
                return {
                    "error": (
                        f"Agent Skill directories were not detected for: {labels}. "
                        "SkillHub will not create them automatically"
                    )
                }
            self.global_skill_targets = targets

        self._save_config()
        return {
            "skills_dir": self.skills_dir,
            "language": self.language,
            "theme": self.theme,
            "default_scan_dir": self.default_scan_dir,
            "ai_import_optimization": self.ai_import_optimization,
            "ai_display_translation": self.ai_display_translation,
            "global_skill_targets": self._configured_global_target_ids(),
            "global_skill_target_options": self._global_skill_target_options(),
        }

    def save_ai_config(self, api_key, model="deepseek-chat", api_base="https://api.deepseek.com/v1"):
        """Save AI configuration. Empty api_key means keep existing."""
        if api_key:
            self.deepseek_api_key = api_key
        self.deepseek_model = model or self.deepseek_model
        self.api_base = api_base or self.api_base
        self._save_config()
        return {
            "ok": True,
            "has_ai_key": bool(self.deepseek_api_key),
            "api_key_hint": (
                f"••••{self.deepseek_api_key[-4:]}"
                if self.deepseek_api_key
                else ""
            ),
        }
