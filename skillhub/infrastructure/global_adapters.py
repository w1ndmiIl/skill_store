"""Generation of isolated client adapters, links, and upload packages."""

import os
import shutil
import subprocess
import time
import uuid
import zipfile
from pathlib import PurePosixPath

from skillhub.domain.frontmatter import (
    build_agent_skill_view,
    preserve_frontmatter_with_missing_fields,
)
from skillhub.domain.global_targets import (
    ANTIGRAVITY_FRONTMATTER_KEYS,
    CLINE_FRONTMATTER_KEYS,
    CLAUDE_CODE_FRONTMATTER_KEYS,
    CLAUDE_UPLOAD_FRONTMATTER_KEYS,
    CODEX_ADAPTER_MANIFEST,
    CODEX_FRONTMATTER_KEYS,
    CURSOR_FRONTMATTER_KEYS,
    FORCE_PORTABLE_NAME_TARGETS,
    GEMINI_FRONTMATTER_KEYS,
    OPENCODE_FRONTMATTER_KEYS,
    VSCODE_FRONTMATTER_KEYS,
    WINDSURF_FRONTMATTER_KEYS,
)
from skillhub.domain.metadata import infer_skill_metadata
from skillhub.domain.naming import AGENT_SKILL_NAME_RE
from skillhub.infrastructure.filesystem import (
    atomic_copy_file,
    atomic_write_json,
    atomic_write_text,
    is_path_reparse_point,
    safe_child_path,
    safe_real_child_path,
)


class GlobalAdaptersMixin:
    """Render client-specific views without mutating source Skills."""

    def _write_codex_global_adapter(self, descriptor: dict):
        """Create a general folder adapter for legacy single-file library entries."""
        adapter = descriptor["link_source"]
        os.makedirs(adapter, exist_ok=True)
        with open(descriptor["entry_file"], "r", encoding="utf-8") as handle:
            content = handle.read()
        metadata = infer_skill_metadata(
            content,
            os.path.basename(descriptor["entry_file"]),
            self.language,
        )
        normalized, _missing = preserve_frontmatter_with_missing_fields(
            content,
            [
                ("name", descriptor["entry_name"]),
                ("description", metadata["description"]),
            ],
        )
        atomic_write_text(os.path.join(adapter, "SKILL.md"), normalized)

        source = descriptor.get("source", "")
        bundled_skills = os.path.join(source, ".agent", "skills")
        if os.path.isdir(bundled_skills):
            for item in os.listdir(bundled_skills):
                child = os.path.join(bundled_skills, item)
                if os.path.isfile(child) and item.lower().endswith(".md"):
                    atomic_copy_file(child, os.path.join(adapter, item))

        atomic_write_json(os.path.join(adapter, CODEX_ADAPTER_MANIFEST), {
            "version": 1,
            "source": descriptor["filename"],
            "source_hash": self._codex_global_source_hash(descriptor),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

    def _write_codex_standard_adapter(self, descriptor: dict, target_id="codex"):
        """Create an isolated client view while preserving source instructions."""
        adapter = descriptor.get("target_adapter_paths", {}).get(
            target_id,
            descriptor.get("codex_link_source", "") if target_id == "codex" else "",
        )
        adapter_root = self._target_standard_adapter_root(target_id)
        expected_adapter = safe_real_child_path(
            adapter_root, os.path.basename(adapter)
        )
        if (
            not adapter
            or not expected_adapter
            or os.path.normcase(os.path.abspath(adapter))
            != os.path.normcase(os.path.abspath(expected_adapter))
        ):
            raise OSError("Invalid client adapter path")

        parent = os.path.dirname(adapter)
        os.makedirs(parent, exist_ok=True)
        temporary = f"{adapter}.{uuid.uuid4().hex}.tmp"
        backup = f"{adapter}.{uuid.uuid4().hex}.bak"
        os.makedirs(temporary)
        try:
            source_root = descriptor.get("source_root", "")
            if os.path.isdir(source_root):
                for current_root, dirs, files in os.walk(
                    source_root, followlinks=False
                ):
                    dirs[:] = [
                        name for name in dirs
                        if not is_path_reparse_point(
                            os.path.join(current_root, name)
                        )
                    ]
                    for name in files:
                        source_file = os.path.join(current_root, name)
                        if (
                            name == CODEX_ADAPTER_MANIFEST
                            or is_path_reparse_point(source_file)
                        ):
                            continue
                        relative = os.path.relpath(source_file, source_root)
                        destination = safe_child_path(temporary, relative)
                        if not destination:
                            raise OSError("Invalid Skill resource path")
                        os.makedirs(os.path.dirname(destination), exist_ok=True)
                        shutil.copy2(source_file, destination)

            with open(
                descriptor["entry_file"], "r", encoding="utf-8", newline=""
            ) as handle:
                content = handle.read()
            metadata = infer_skill_metadata(
                content,
                os.path.basename(descriptor["entry_file"]),
                self.language,
            )
            allowed_keys = {
                "codex": CODEX_FRONTMATTER_KEYS,
                "claude_code": CLAUDE_CODE_FRONTMATTER_KEYS,
                "cursor": CURSOR_FRONTMATTER_KEYS,
                "cline": CLINE_FRONTMATTER_KEYS,
                "opencode": OPENCODE_FRONTMATTER_KEYS,
                "windsurf": WINDSURF_FRONTMATTER_KEYS,
                "antigravity": ANTIGRAVITY_FRONTMATTER_KEYS,
                "gemini_cli": GEMINI_FRONTMATTER_KEYS,
                "vscode": VSCODE_FRONTMATTER_KEYS,
                "claude_desktop": CLAUDE_UPLOAD_FRONTMATTER_KEYS,
            }.get(target_id, CODEX_FRONTMATTER_KEYS)
            forced_name = ""
            if target_id in FORCE_PORTABLE_NAME_TARGETS:
                forced_name = self._global_target_entry_name(
                    descriptor, target_id
                )
            normalized, removed_keys = build_agent_skill_view(
                content,
                self._global_target_entry_name(descriptor, target_id),
                metadata["description"],
                allowed_keys,
                forced_name=forced_name,
            )
            atomic_write_text(os.path.join(temporary, "SKILL.md"), normalized)
            atomic_write_json(
                os.path.join(temporary, CODEX_ADAPTER_MANIFEST),
                {
                    "version": 1,
                    "target": target_id,
                    "source": descriptor["filename"],
                    "source_hash": self._codex_global_source_hash(descriptor),
                    "removed_unsupported_frontmatter_keys": removed_keys,
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                },
            )

            if os.path.lexists(adapter):
                if is_path_reparse_point(adapter):
                    raise OSError("Refusing to replace a linked client adapter")
                os.replace(adapter, backup)
            try:
                os.replace(temporary, adapter)
            except Exception:
                if os.path.exists(backup) and not os.path.exists(adapter):
                    os.replace(backup, adapter)
                raise
            if os.path.exists(backup):
                shutil.rmtree(backup)
        finally:
            if os.path.exists(temporary):
                shutil.rmtree(temporary)

    def _create_codex_global_link(self, source: str, target: str):
        """Create a directory link without copying Skill contents onto the C drive."""
        parent = os.path.dirname(target)
        if not parent or not os.path.isdir(parent):
            raise OSError(
                "Agent Skill directory does not exist; SkillHub will not create it"
            )
        if os.name == "nt":
            completed = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    (
                        "& { param([string]$LinkPath, [string]$SourcePath) "
                        "New-Item -ItemType Junction -Path $LinkPath -Target "
                        "$SourcePath -ErrorAction Stop | Out-Null }"
                    ),
                    target,
                    source,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            if completed.returncode != 0:
                message = (completed.stderr or completed.stdout or "").strip()
                raise OSError(message or "Failed to create global Skill link")
            return
        os.symlink(source, target, target_is_directory=True)

    def _write_claude_desktop_export(self, descriptor: dict):
        """Create a Claude-uploadable ZIP; account installation remains manual."""
        self._write_codex_standard_adapter(descriptor, "claude_desktop")
        export_root = self._claude_desktop_export_root()
        os.makedirs(export_root, exist_ok=True)
        package_path = safe_child_path(
            export_root,
            f'{self._global_target_entry_name(descriptor, "claude_desktop")}.zip',
        )
        manifest_path = safe_child_path(
            export_root,
            f'{self._global_target_entry_name(descriptor, "claude_desktop")}.json',
        )
        if not package_path or not manifest_path:
            raise OSError("Invalid Claude Desktop export path")
        temporary = f"{package_path}.{uuid.uuid4().hex}.tmp"
        package_root = self._global_target_entry_name(
            descriptor, "claude_desktop"
        )
        source_root = descriptor["target_adapter_paths"]["claude_desktop"]
        if (
            not AGENT_SKILL_NAME_RE.fullmatch(package_root)
            or len(package_root) > 64
            or package_root in {"anthropic", "claude"}
        ):
            raise OSError("Claude upload Skill name is invalid or reserved")
        unpacked_size = sum(
            os.path.getsize(os.path.join(current_root, name))
            for current_root, dirs, files in os.walk(source_root, followlinks=False)
            for name in files
            if name != CODEX_ADAPTER_MANIFEST
            and not is_path_reparse_point(os.path.join(current_root, name))
        )
        if unpacked_size > 30 * 1024 * 1024:
            raise OSError("Claude upload package exceeds the 30 MB limit")
        try:
            with zipfile.ZipFile(
                temporary, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for current_root, dirs, files in os.walk(
                    source_root, followlinks=False
                ):
                    dirs[:] = [
                        name for name in dirs
                        if not is_path_reparse_point(
                            os.path.join(current_root, name)
                        )
                    ]
                    for name in files:
                        source_file = os.path.join(current_root, name)
                        if name == CODEX_ADAPTER_MANIFEST or is_path_reparse_point(
                            source_file
                        ):
                            continue
                        relative = os.path.relpath(source_file, source_root)
                        archive.write(
                            source_file,
                            str(PurePosixPath(package_root, *relative.split(os.sep))),
                        )
            os.replace(temporary, package_path)
            if os.path.getsize(package_path) > 30 * 1024 * 1024:
                os.remove(package_path)
                raise OSError("Claude upload ZIP exceeds the 30 MB limit")
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)
        atomic_write_json(manifest_path, {
            "version": 1,
            "source": descriptor["filename"],
            "source_hash": self._codex_global_source_hash(descriptor),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "manual_install": True,
        })
