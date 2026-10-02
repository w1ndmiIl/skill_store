"""Configuration persistence and legacy migration for the desktop application."""

import os
from urllib.parse import urlparse

DEFAULT_AI_MODEL = "deepseek-flash"

from .filesystem import atomic_write_json, load_json_file
from .json_store import read_json, write_json

def valid_config(value):
    if not isinstance(value, dict):
        return False
    strings = ("skills_dir", "language", "theme", "default_scan_dir", "deepseek_api_key", "deepseek_model", "api_base")
    return (all(isinstance(value.get(k, ""), str) for k in strings)
            and isinstance(value.get("projects", []), list)
            and all(isinstance(p, dict) and isinstance(p.get("path"), str)
                    and isinstance(p.get("name"), str) for p in value.get("projects", []))
            and isinstance(value.get("global_skill_targets", []), list))


def get_default_skills_dir() -> str:
    """Return a writable per-user library path outside the application files."""
    user_data_root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if user_data_root:
        return os.path.join(user_data_root, "SkillHub", "skills")
    return os.path.join(os.path.expanduser("~"), ".skillhub", "skills")


class ConfigRepository:
    """Own the on-disk config schema while keeping API state out of persistence."""

    def __init__(
        self,
        config_path: str,
        app_dir: str,
        default_global_targets: tuple,
        legacy_config_paths: tuple = (),
    ):
        self.config_path = config_path
        self.app_dir = app_dir
        self.default_global_targets = tuple(default_global_targets)
        adjacent_legacy_path = os.path.join(app_dir, "config.json")
        self.legacy_config_paths = tuple(dict.fromkeys(
            path
            for path in (*legacy_config_paths, adjacent_legacy_path)
            if path and os.path.abspath(path) != os.path.abspath(config_path)
        ))

    def defaults(self) -> dict:
        return {
            "skills_dir": get_default_skills_dir(),
            "projects": [],
            "language": "zh",
            "theme": "light",
            "default_scan_dir": os.path.expanduser("~"),
            "ai_import_optimization": False,
            "ai_display_translation": False,
            "deepseek_model": DEFAULT_AI_MODEL,
            "ai_reasoning_effort": "high",
            "global_skill_targets": list(self.default_global_targets),
        }

    def load(self) -> dict:
        defaults = self.defaults()
        if not os.path.exists(self.config_path):
            for legacy_path in self.legacy_config_paths:
                legacy_config = load_json_file(legacy_path, None)
                if not isinstance(legacy_config, dict):
                    continue
                migrated = dict(defaults)
                migrated.update(legacy_config)
                try:
                    atomic_write_json(self.config_path, migrated)
                except OSError:
                    return migrated
                break

        old_projects_path = os.path.join(self.app_dir, "projects.json")
        if not os.path.exists(self.config_path) and os.path.exists(old_projects_path):
            old_projects = load_json_file(old_projects_path, [])
            if isinstance(old_projects, list):
                migrated = {
                    "skills_dir": defaults["skills_dir"],
                    "projects": old_projects,
                    "language": "zh",
                    "theme": "light",
                    "default_scan_dir": os.path.expanduser("~"),
                }
                try:
                    atomic_write_json(self.config_path, migrated)
                except OSError:
                    pass

        loaded = read_json(self.config_path, defaults, valid_config)
        if not isinstance(loaded, dict):
            return defaults
        config = dict(loaded)
        if not config.get("skills_dir"):
            config["skills_dir"] = defaults["skills_dir"]
        for key in (
            "projects",
            "ai_import_optimization",
            "ai_display_translation",
            "global_skill_targets",
            "deepseek_model",
            "ai_reasoning_effort",
        ):
            if key not in config:
                config[key] = defaults[key]
        if (urlparse(config.get("api_base", "https://api.deepseek.com/v1")).hostname == "api.deepseek.com"
                and config["deepseek_model"] in ("deepseek-chat", "deepseek-reasoner", "deepseek-v4-flash", "deepseek-v4-flash-vision-exp")):
            config["deepseek_model"] = DEFAULT_AI_MODEL
            # Preserve all original fields and a validated backup on migration.
            if os.path.exists(self.config_path):
                write_json(self.config_path, config, valid_config)
        return config

    def save(self, config: dict) -> bool:
        try:
            write_json(self.config_path, config, valid_config)
            return True
        except (OSError, ValueError):
            return False
