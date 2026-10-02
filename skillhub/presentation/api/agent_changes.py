"""Agent tools for draft, Skill mutation, and project synchronization."""

import difflib
import hashlib
import os
from skillhub.domain.naming import is_project_rules_document
import uuid
import json
import shutil

from agent_runtime import SENSITIVE_INLINE_RE, SENSITIVE_VALUE_RE

from skillhub.domain.naming import normalize_skill_filename, normalize_agent_skill_name
from skillhub.domain.frontmatter import preserve_frontmatter_with_missing_fields
from skillhub.domain.metadata import infer_skill_metadata
from skillhub.infrastructure.json_store import file_lock
from skillhub.infrastructure.transactions import restore_files
from skillhub.infrastructure.filesystem import (
    atomic_copy_file,
    atomic_write_text,
    safe_child_path,
    safe_real_child_path,
)
from skillhub.settings import AGENT_BACKUPS_DIR


class AgentChangesApiMixin:
    """Bind mutations to immutable previews and approval state."""

    def _agent_change_target(self, requested):
        source = self._editable_skill_source(requested)
        if source:
            target = source["path"]
            if not safe_real_child_path(self.skills_dir, os.path.relpath(target, self.skills_dir)):
                return {}
            return {"filename": requested, "path": target, "owner": source["owner"], "exists": True}
        name = normalize_skill_filename(requested)
        if name.lower().endswith(".md"):
            name = name[:-3]
        if not name or requested.startswith("@"):
            return {}
        name = normalize_agent_skill_name(name, name)
        folder = safe_real_child_path(self.skills_dir, name)
        if not folder or os.path.exists(folder) or os.path.exists(folder + ".md"):
            return {}
        return {"filename": name, "path": os.path.join(folder, "SKILL.md"),
                "owner": name, "exists": False, "new_folder": folder}

    def _tool_draft_skill_change(self, arguments):
        if is_project_rules_document(arguments.get("filename")):
            return {"error": "AGENTS.md 不允许自动 AI 修改；请在项目规约编辑器手动编辑或单独授权 AI 起草。"}
        resolved = self._agent_change_target(arguments["filename"])
        if not resolved:
            return {"error": "Invalid skill filename"}
        filename = resolved["filename"]
        content = arguments["content"]
        source = resolved if resolved["exists"] else None
        if not source:
            metadata = infer_skill_metadata(content, filename, self.language)
            content, _ = preserve_frontmatter_with_missing_fields(content, [
                ("name", filename), ("description", json.dumps(metadata["description"], ensure_ascii=False)),
            ])
        before = ""
        if source:
            try:
                with open(source["path"], "r", encoding="utf-8") as handle:
                    before = handle.read()
            except OSError as error:
                return {"error": str(error)}
        diff = "".join(difflib.unified_diff(
            before.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        ))
        return {
            "ok": True,
            "target_file": filename,
            "change_type": "modify" if source else "create",
            "target_exists": bool(source),
            "before_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
            "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "summary": arguments["summary"],
            "content": content,
            "diff": diff[:12000],
            "diff_truncated": len(diff) > 12000,
        }

    def _tool_preview_project_sync(self, arguments):
        return self.preview_sync(
            arguments["project_path"],
            arguments["enabled_skills"],
        )

    def _tool_apply_skill_change(self, arguments):
        with file_lock(self.skills_dir):
            return self._apply_agent_skill_change(arguments)

    def _apply_agent_skill_change(self, arguments):
        if is_project_rules_document(arguments.get("filename")):
            return {"error": "AGENTS.md 不允许自动 AI 修改；请在项目规约编辑器手动编辑或单独授权 AI 起草。"}
        resolved = self._agent_change_target(arguments["filename"])
        if not resolved or resolved["filename"] != arguments["filename"]:
            return {"error": "Invalid or normalized skill filename"}
        filename = resolved["filename"]
        content = arguments["content"]
        content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if content_sha256 != arguments["expected_content_sha256"]:
            return {"error": "Skill content no longer matches the approved preview"}
        if SENSITIVE_VALUE_RE.search(content) or SENSITIVE_INLINE_RE.search(content):
            return {"error": "Content appears to contain a secret and was not saved"}
        target = resolved["path"]
        if not target:
            return {"error": "Unsafe skill target path"}
        if is_project_rules_document(os.path.realpath(target)):
            return {"error": "AGENTS.md 不允许自动 AI 修改；请在项目规约编辑器手动编辑或单独授权 AI 起草。"}
        target_exists = resolved["exists"]
        if target_exists != arguments["expected_target_exists"]:
            return {"error": "Skill target existence changed after preview; preview again"}
        before = ""
        if target_exists:
            try:
                with open(target, "r", encoding="utf-8") as handle:
                    before = handle.read()
            except OSError as error:
                return {"error": str(error)}
        before_sha256 = hashlib.sha256(before.encode("utf-8")).hexdigest()
        if before_sha256 != arguments["expected_before_sha256"]:
            return {"error": "Skill target changed after preview; preview again"}
        transaction_id = uuid.uuid4().hex
        backup = ""
        snapshot = self._library_metadata_snapshot()
        try:
            if os.path.isfile(target):
                backup_root = os.path.join(
                    AGENT_BACKUPS_DIR, transaction_id
                )
                os.makedirs(backup_root, exist_ok=True)
                backup = os.path.join(
                    backup_root, os.path.basename(target) + ".bak"
                )
                atomic_copy_file(target, backup)
            elif resolved.get("new_folder"):
                os.mkdir(resolved["new_folder"])
            atomic_write_text(target, content)
            self._register_library_entry(
                resolved["owner"],
                source="skillops-agent",
            )
        except Exception as error:
            rollback_errors = []
            try:
                if backup and os.path.isfile(backup):
                    atomic_copy_file(backup, target)
                elif resolved.get("new_folder") and os.path.isdir(resolved["new_folder"]):
                    shutil.rmtree(resolved["new_folder"])
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
            rollback_errors.extend(restore_files(snapshot))
            return {"error": str(error), "rolled_back": not rollback_errors,
                    "rollback_errors": rollback_errors, "recovery_path": backup if rollback_errors else ""}
        warning = ""
        try:
            self._agent_memory.remember(
                "decision",
                f"已批准并应用 Skill 修改：{filename}。原因：{arguments['reason']}",
                metadata={
                    "transaction_id": transaction_id,
                    "had_backup": bool(backup),
                },
                source="runtime",
            )
        except OSError:
            warning = "Skill 已保存，但辅助记忆未更新 / Skill saved; memory update failed"
        return {
                "ok": True,
                "filename": filename,
                "transaction_id": transaction_id,
                "backup_created": bool(backup),
                "warning": warning,
            }

    def _tool_apply_project_sync(self, arguments):
        result = self.sync_skills(
            arguments["project_path"],
            arguments["enabled_skills"],
            allow_conflicts=arguments.get("allow_conflicts", False),
            preview_token=arguments["plan_token"],
            allow_bundle_files=arguments.get("allow_bundle_files", False),
        )
        if result.get("ok"):
            self._agent_memory.remember(
                "project",
                (
                    f"最近一次同步成功，启用 {len(arguments['enabled_skills'])} 个 Skill，"
                    f"事务 {result.get('transaction_id', '')}。"
                ),
                project_path=arguments["project_path"],
                metadata={
                    "enabled_skills": arguments["enabled_skills"],
                    "transaction_id": result.get("transaction_id", ""),
                },
                source="runtime",
            )
        return result
