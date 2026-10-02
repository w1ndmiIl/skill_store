import os
import sys
import atexit
import ctypes
import json
import shutil
import hashlib
import difflib
import time
import re
import uuid
import zipfile
from pathlib import PurePosixPath
import webview
import requests
import yaml
from ddgs import DDGS
from agent_runtime import (
    AgentMemoryStore,
    AgentRuntime,
    AgentTaskStore,
    OpenAICompatibleModel,
    RunRecorder,
    ToolDefinition,
    SENSITIVE_INLINE_RE,
    SENSITIVE_VALUE_RE,
)
from skillhub.application.chat_sessions import ChatSessionService
from skillhub.infrastructure.sync_status import (
    SYNC_LAST_TRANSACTION_NAME,
    SYNC_MANIFEST_NAME,
    SYNC_STATE_DIR,
    check_dir_sync_status,
)
from skillhub.domain.agent_index import (
    AGENTS_MANAGED_END,
    AGENTS_MANAGED_START,
    build_agents_managed_section,
    merge_agents_managed_section,
)
from skillhub.domain.catalog import (
    collect_folder_skill_metadata,
    parse_markdown_metadata,
    upsert_metadata,
)
from skillhub.domain.collections import COLLECTION_DISPLAY_LOCALIZATIONS
from skillhub.domain.compatibility import (
    build_codex_skill_view,
    inspect_agent_skill_compatibility,
)
from skillhub.domain.frontmatter import (
    build_agent_skill_view,
    frontmatter_top_level_keys,
    preserve_frontmatter_with_missing_fields,
    remove_markdown_frontmatter_field,
    split_markdown_frontmatter,
    split_markdown_frontmatter_source,
)
from skillhub.domain.global_targets import (
    ANTIGRAVITY_FRONTMATTER_KEYS,
    CLINE_FRONTMATTER_KEYS,
    CLAUDE_CODE_FRONTMATTER_KEYS,
    CLAUDE_UPLOAD_FRONTMATTER_KEYS,
    CODEX_ADAPTER_MANIFEST,
    CODEX_FRONTMATTER_KEYS,
    CURSOR_FRONTMATTER_KEYS,
    DEFAULT_GLOBAL_SKILL_TARGETS,
    GEMINI_FRONTMATTER_KEYS,
    GLOBAL_SKILL_TARGETS,
    OPENCODE_FRONTMATTER_KEYS,
    SKILL_LIBRARY_STATE_DIR,
    VSCODE_FRONTMATTER_KEYS,
    WINDSURF_FRONTMATTER_KEYS,
    normalize_global_skill_targets,
)
from skillhub.domain.metadata import (
    clean_frontmatter_value as _clean_frontmatter_value,
    infer_skill_metadata,
    markdown_title_and_description as _markdown_title_and_description,
)
from skillhub.domain.imports import (
    SKILL_IMPORT_DIFF_MAX_CHARS,
    SKILL_IMPORT_MAX_ENTRIES,
    SKILL_IMPORT_MAX_FILE_BYTES,
    SKILL_IMPORT_MAX_TOTAL_BYTES,
    build_import_diff,
    normalize_skillhub_markdown,
    scan_skill_text,
)
from skillhub.domain.naming import (
    AGENT_SKILL_NAME_RE,
    normalize_agent_skill_name,
    normalize_skill_filename,
)
from skillhub.domain.optimization import guard_conservative_ai_optimization
from skillhub.infrastructure.filesystem import (
    atomic_copy_file,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    get_bytes_md5,
    get_file_md5,
    get_tree_sha256,
    is_path_reparse_point,
    load_json_file,
    normalize_relative_path,
    paths_overlap,
    safe_child_path,
    safe_real_child_path,
)
from skillhub.infrastructure.config_repository import (
    ConfigRepository,
    get_default_skills_dir,
)
from skillhub.infrastructure.global_targets import GlobalTargetService
from skillhub.infrastructure.session_repository import ChatSessionRepository
from skillhub.infrastructure.single_instance import (
    ERROR_ALREADY_EXISTS,
    SINGLE_INSTANCE_MUTEX_NAME,
    SingleInstanceGuard,
    acquire_skillhub_single_instance,
    focus_existing_skillhub_window,
)
from skillhub.infrastructure.windowing import set_window_icon
from skillhub.settings import (
    AGENT_MEMORY_PATH,
    AGENT_RUNS_PATH,
    AGENT_TASKS_PATH,
    APP_DIR,
    APP_VERSION,
    BASE_DIR,
    CONFIG_PATH,
    SKILLHUB_DOWNLOAD_URL,
    SKILLHUB_INSTALL_GUIDE_URL,
    SKILLHUB_SEARCH_URL,
)
from skillhub.presentation.api.agent_catalog import AgentCatalogApiMixin
from skillhub.presentation.api.agent_changes import AgentChangesApiMixin
from skillhub.presentation.api.agent_remote import AgentRemoteApiMixin
from skillhub.presentation.api.agent_runtime import AgentRuntimeApiMixin
from skillhub.presentation.api.ai_provider import AiProviderApiMixin
from skillhub.presentation.api.ai_skills import AiSkillsApiMixin
from skillhub.presentation.api.chat import ChatApiMixin
from skillhub.presentation.api.collections import CollectionsApiMixin
from skillhub.presentation.api.configuration import ConfigurationApiMixin
from skillhub.presentation.api.imports import ImportsApiMixin
from skillhub.presentation.api.import_candidates import ImportCandidatesApiMixin
from skillhub.presentation.api.import_preparation import ImportPreparationApiMixin
from skillhub.presentation.api.library import LibraryApiMixin
from skillhub.presentation.api.skill_editor import SkillEditorApiMixin
from skillhub.presentation.api.project_sync import ProjectSyncApiMixin
from skillhub.presentation.api.projects import ProjectsApiMixin

# ============================================================
# pywebview JavaScript API Bridge
# ============================================================

from skillhub.presentation.api.background_agent import BackgroundAgentApiMixin
from skillhub.presentation.api.trash import TrashApiMixin
from skillhub.presentation.api.project_rules_editor import ProjectRulesEditorApiMixin
from skillhub.presentation.api.workspace_state import WorkspaceStateApiMixin
from skillhub.presentation.api.storage_recovery import StorageRecoveryApiMixin


class Api(
    BackgroundAgentApiMixin,
    TrashApiMixin,
    ProjectRulesEditorApiMixin,
    WorkspaceStateApiMixin,
    StorageRecoveryApiMixin,
    ConfigurationApiMixin,
    AiProviderApiMixin,
    AgentCatalogApiMixin,
    AgentRemoteApiMixin,
    AgentChangesApiMixin,
    AgentRuntimeApiMixin,
    ChatApiMixin,
    AiSkillsApiMixin,
    SkillEditorApiMixin,
    LibraryApiMixin,
    CollectionsApiMixin,
    ImportPreparationApiMixin,
    ImportCandidatesApiMixin,
    ImportsApiMixin,
    ProjectsApiMixin,
    ProjectSyncApiMixin,
    GlobalTargetService,
):
    def __init__(self):
        self._window = None
        # Load configuration on startup (with migration)
        config = self._load_config()
        self.skills_dir = config.get("skills_dir")
        self.projects = config.get("projects", [])
        self.language = config.get("language", "zh")
        self.theme = config.get("theme", "light")
        self.default_scan_dir = config.get("default_scan_dir", os.path.expanduser("~"))
        self.deepseek_api_key = config.get("deepseek_api_key", "")
        self.deepseek_model = config.get("deepseek_model", "deepseek-flash")
        self.ai_reasoning_effort = config.get("ai_reasoning_effort", "high")
        self.api_base = config.get("api_base", "https://api.deepseek.com/v1")
        self.ai_import_optimization = bool(
            config.get("ai_import_optimization", False)
        )
        self.ai_display_translation = bool(
            config.get("ai_display_translation", False)
        )
        configured_targets = config.get(
            "global_skill_targets", list(DEFAULT_GLOBAL_SKILL_TARGETS)
        )
        self.global_skill_targets = self._normalize_global_skill_targets(
            configured_targets
        )
        self._agent_memory = AgentMemoryStore(
            AGENT_MEMORY_PATH
        )
        self._agent_tasks = AgentTaskStore(
            AGENT_TASKS_PATH
        )
        self._agent_recorder = RunRecorder(
            AGENT_RUNS_PATH
        )
    def set_window(self, window):
        self._window = window

# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    # Safe stream handling for pythonw.exe
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    if not acquire_skillhub_single_instance():
        focus_existing_skillhub_window()
        sys.exit(0)

    api = Api()
    icon_path = os.path.join(APP_DIR, 'app.ico')
    if not os.path.exists(icon_path):
        icon_path = os.path.join(BASE_DIR, 'app.ico')

    window = webview.create_window(
        'SkillHub',
        url=os.path.join(BASE_DIR, 'static', 'index.html'),
        js_api=api,
        width=1280,
        height=840,
        min_size=(720, 620),
        background_color='#f6f8fa',
        text_select=True,
    )
    api.set_window(window)
    window.events.closing += api.can_close_window
    webview.start(debug=False, func=lambda: set_window_icon(icon_path))
