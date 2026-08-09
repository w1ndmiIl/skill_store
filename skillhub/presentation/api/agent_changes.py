"""Agent tools for draft, Skill mutation, and project synchronization."""

import difflib
import hashlib
import os
import uuid

from agent_runtime import SENSITIVE_INLINE_RE, SENSITIVE_VALUE_RE

from skillhub.domain.naming import normalize_skill_filename
from skillhub.infrastructure.filesystem import (
    atomic_copy_file,
    atomic_write_text,
    safe_child_path,
)
from skillhub.settings import AGENT_BACKUPS_DIR


class AgentChangesApiMixin:
    """Bind mutations to immutable previews and approval state."""

    def _tool_draft_skill_change(self, arguments):
        filename = normalize_skill_filename(
            arguments["filename"], ensure_md=True
        )
        if not filename:
            return {"error": "Invalid skill filename"}
        content = arguments["content"]
        source = self._editable_skill_source(filename)
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
        filename = normalize_skill_filename(
            arguments["filename"], ensure_md=True
        )
        if not filename or filename != arguments["filename"]:
            return {"error": "Invalid or normalized skill filename"}
        content = arguments["content"]
        content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if content_sha256 != arguments["expected_content_sha256"]:
            return {"error": "Skill content no longer matches the approved preview"}
        if SENSITIVE_VALUE_RE.search(content) or SENSITIVE_INLINE_RE.search(content):
            return {"error": "Content appears to contain a secret and was not saved"}
        source = self._editable_skill_source(filename)
        target = source.get("path", "") if source else safe_child_path(
            self.skills_dir, filename
        )
        if not target:
            return {"error": "Unsafe skill target path"}
        target_exists = bool(source and os.path.isfile(target))
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
            atomic_write_text(target, content)
            self._register_library_entry(
                filename,
                source="skillops-agent",
            )
            self._agent_memory.remember(
                "decision",
                f"已批准并应用 Skill 修改：{filename}。原因：{arguments['reason']}",
                metadata={
                    "transaction_id": transaction_id,
                    "had_backup": bool(backup),
                },
                source="runtime",
            )
            return {
                "ok": True,
                "filename": filename,
                "transaction_id": transaction_id,
                "backup_created": bool(backup),
            }
        except Exception as error:
            if backup and os.path.isfile(backup):
                try:
                    atomic_copy_file(backup, target)
                except OSError:
                    pass
            return {"error": str(error)}

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
