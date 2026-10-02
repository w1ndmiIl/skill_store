"""Application identity, runtime paths, and external endpoint configuration."""

import os
import sys


if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS
    APP_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    APP_DIR = BASE_DIR


def get_user_data_dir(environ=None) -> str:
    """Return the stable writable directory used for mutable application data."""
    environ = os.environ if environ is None else environ
    override = str(environ.get("SKILLHUB_DATA_DIR", "")).strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    user_data_root = environ.get("LOCALAPPDATA") or environ.get("APPDATA")
    if user_data_root:
        return os.path.join(user_data_root, "SkillHub")
    return os.path.join(os.path.expanduser("~"), ".skillhub")


USER_DATA_DIR = get_user_data_dir()
CONFIG_PATH = os.path.join(USER_DATA_DIR, "config.json")
LEGACY_CONFIG_PATHS = (os.path.join(APP_DIR, "config.json"),)
CHAT_SESSIONS_PATH = os.path.join(USER_DATA_DIR, "chat_sessions.json")
AGENT_MEMORY_PATH = os.path.join(USER_DATA_DIR, "agent_memory.json")
AGENT_TASKS_PATH = os.path.join(USER_DATA_DIR, "agent_tasks.json")
AGENT_RUNS_PATH = os.path.join(USER_DATA_DIR, "agent_runs.jsonl")
AGENT_BACKUPS_DIR = os.path.join(USER_DATA_DIR, "agent_backups")
AGENT_REMOTE_COLLECTIONS_DIR = os.path.join(
    USER_DATA_DIR,
    "agent-remote-collections",
)
APP_VERSION = "3.6.2"
SKILLHUB_INSTALL_GUIDE_URL = "https://skillhub.cn/install/skillhub.md"
SKILLHUB_SEARCH_URL = "https://api.skillhub.cn/api/v1/search"
SKILLHUB_DOWNLOAD_URL = "https://api.skillhub.cn/api/v1/download"
