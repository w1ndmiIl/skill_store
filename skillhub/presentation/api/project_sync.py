"""Project registration, sync planning, transactional apply, and undo endpoints."""

import json
import os
import re
import time
import uuid

from skillhub.domain.agent_index import (
    build_agents_managed_section,
    merge_agents_managed_section,
)
from skillhub.domain.catalog import (
    collect_folder_skill_metadata,
    parse_markdown_metadata,
    upsert_metadata,
)
from skillhub.domain.naming import normalize_relative_path
from skillhub.infrastructure.filesystem import (
    atomic_copy_file,
    atomic_write_json,
    atomic_write_text,
    get_bytes_md5,
    get_file_md5,
    load_json_file,
    safe_real_child_path,
)
from skillhub.infrastructure.sync_status import (
    SYNC_STATE_DIR,
)


from skillhub.infrastructure.json_store import file_lock


class ProjectSyncApiMixin:
    """Plan and apply project synchronization with rollback and undo."""









    def _collect_desired_sync_files(
        self, project_path: str, enabled_skills: list, *, global_skills=None
    ):
        enabled_set = set(enabled_skills or [])
        if global_skills is None:
            global_skills = self._collect_skills(include_global_state=False)
        enabled = [skill for skill in global_skills if skill.get("filename") in enabled_set]
        bundle_collections = {
            collection.get("bundle_parent"): collection
            for collection in self._load_skill_collections().get("collections", [])
            if collection.get("kind") == "bundle"
            and collection.get("bundle_parent")
        }
        desired = {}
        desired_paths = {}
        active_metadata = []
        source_collision_keys = set()

        def add_desired(
            relative_path,
            owner,
            source=None,
            content=None,
            merge_safe=False,
            requires_bundle_authorization=False,
        ):
            relative_path = normalize_relative_path(relative_path)
            if relative_path.lower().startswith(normalize_relative_path(SYNC_STATE_DIR).lower() + "/"):
                return
            path_key = relative_path.casefold()
            previous_path = desired_paths.get(path_key)
            if previous_path:
                previous = desired[previous_path]
                if (
                    previous_path != relative_path
                    or previous.get("owner") != owner
                ):
                    source_collision_keys.add(path_key)
                if previous_path != relative_path:
                    desired.pop(previous_path, None)
            if source:
                digest = get_file_md5(source)
            else:
                digest = get_bytes_md5((content or "").encode("utf-8"))
            desired_paths[path_key] = relative_path
            desired[relative_path] = {
                "path": relative_path,
                "owner": owner,
                "source": source,
                "content": content,
                "hash": digest,
                "merge_safe": merge_safe,
                "requires_bundle_authorization": requires_bundle_authorization,
            }

        # Folder skills are applied first. Standalone skills then override bundled files.
        for skill in enabled:
            if not skill.get("is_dir", False):
                continue
            filename = skill["filename"]
            source_root = safe_real_child_path(self.skills_dir, filename)
            if not source_root or not os.path.isdir(source_root):
                continue

            if skill.get("folder_kind") == "standard":
                skill_path = os.path.join(source_root, "SKILL.md")
                if not os.path.isfile(skill_path):
                    continue
                folder_meta = parse_markdown_metadata(skill_path)
                folder_meta["filename"] = filename
                folder_meta["is_dir"] = True
                folder_meta["folder_kind"] = "standard"
                upsert_metadata(
                    active_metadata,
                    self._skill_metadata_for_index(folder_meta),
                )
                for root, dirs, files in os.walk(source_root):
                    dirs[:] = sorted(item for item in dirs if not item.startswith(".git"))
                    files.sort()
                    for item in files:
                        source = os.path.join(root, item)
                        relative_path = normalize_relative_path(
                            os.path.relpath(source, source_root)
                        )
                        add_desired(
                            os.path.join(
                                ".agent", "skills", filename, relative_path
                            ),
                            filename,
                            source=source,
                        )
                continue

            readme_path = os.path.join(source_root, "README.md")
            bundle_collection = bundle_collections.get(filename, {})
            virtual_by_source = {
                normalize_relative_path(relative).lower(): virtual_id
                for virtual_id, relative in bundle_collection.get(
                    "member_sources",
                    {},
                ).items()
            }
            if os.path.isfile(readme_path):
                folder_meta = parse_markdown_metadata(readme_path)
                add_desired(
                    os.path.join(".agent", "skills", f"{filename}.md"),
                    filename,
                    source=readme_path,
                )
            else:
                folder_meta = {
                    "title": filename,
                    "emoji": "",
                    "category": "工作流" if self.language == "zh" else "Workflow",
                    "tags": ["项目级"] if self.language == "zh" else ["Project-Level"],
                    "description": "项目级技能文件夹" if self.language == "zh" else "Project-level skill folder",
                }
                fallback = f"# {filename}\n"
                add_desired(
                    os.path.join(".agent", "skills", f"{filename}.md"),
                    filename,
                    content=fallback,
                )
            folder_meta["filename"] = filename
            folder_meta["is_dir"] = True
            upsert_metadata(active_metadata, self._skill_metadata_for_index(folder_meta))

            for bundled_meta in collect_folder_skill_metadata(source_root):
                source_relative = normalize_relative_path(os.path.join(
                    ".agent",
                    "skills",
                    bundled_meta.get("filename", ""),
                )).lower()
                virtual_id = virtual_by_source.get(source_relative)
                if virtual_id and virtual_id not in enabled_set:
                    continue
                upsert_metadata(
                    active_metadata,
                    self._skill_metadata_for_index(bundled_meta),
                )

            for root, dirs, files in os.walk(source_root):
                dirs.sort()
                files.sort()
                for item in files:
                    source = os.path.join(root, item)
                    if not safe_real_child_path(source_root, os.path.relpath(source, source_root)):
                        continue
                    relative_path = normalize_relative_path(os.path.relpath(source, source_root))
                    if relative_path.lower() in ("agents.md", "readme.md"):
                        continue
                    virtual_id = virtual_by_source.get(relative_path.lower())
                    if virtual_id and virtual_id not in enabled_set:
                        continue
                    bundle_allowed = relative_path.casefold().startswith(
                        ".agent/skills/"
                    )
                    add_desired(
                        relative_path,
                        filename,
                        source=source,
                        requires_bundle_authorization=not bundle_allowed,
                    )

        for skill in enabled:
            if skill.get("is_dir", False):
                continue
            filename = skill["filename"]
            if skill.get("is_virtual"):
                parent = skill.get("virtual_parent", "")
                if parent in enabled_set:
                    continue
                source = safe_real_child_path(
                    os.path.join(self.skills_dir, parent),
                    skill.get("virtual_source", ""),
                )
                target_filename = skill.get("target_filename", "")
            else:
                source = safe_real_child_path(self.skills_dir, filename)
                target_filename = filename
            if not source or not os.path.isfile(source):
                continue
            add_desired(
                os.path.join(".agent", "skills", target_filename),
                filename,
                source=source,
            )
            metadata = parse_markdown_metadata(source)
            metadata["filename"] = target_filename
            metadata["is_dir"] = False
            upsert_metadata(active_metadata, self._skill_metadata_for_index(metadata))

        agents_path = os.path.join(project_path, "AGENTS.md")
        existing_agents = ""
        if os.path.isfile(agents_path):
            try:
                with open(agents_path, "r", encoding="utf-8") as handle:
                    existing_agents = handle.read()
            except OSError:
                existing_agents = ""
        managed_section = build_agents_managed_section(active_metadata, self.language)
        agents_content = merge_agents_managed_section(existing_agents, managed_section)
        add_desired(
            "AGENTS.md",
            "__agents_index__",
            content=agents_content,
            merge_safe=True,
        )
        return desired, active_metadata, source_collision_keys

    def _build_sync_plan(self, project_path: str, enabled_skills: list) -> dict:
        registered_path = self._registered_project_path(project_path)
        if not registered_path or not os.path.isdir(registered_path):
            return {"error": "Project path is not registered or does not exist"}

        previous_manifest = self._load_sync_manifest(registered_path)
        previous_files = previous_manifest.get("files", {})
        preserved_files = previous_manifest.get("preserved_files", {})
        if not isinstance(preserved_files, dict):
            preserved_files = {}
        effective_enabled = self._effective_enabled_skills(enabled_skills)
        scope_conflicts = self._project_global_scope_conflicts(effective_enabled)
        # Share metadata only within this plan. Apply builds a fresh plan and
        # retains its source/target hash checks against the reviewed preview.
        global_skills = self._collect_skills(include_global_state=False)
        desired, active_metadata, source_collision_keys = self._collect_desired_sync_files(
            registered_path, effective_enabled, global_skills=global_skills
        )
        changes = []
        desired_keys = {
            relative_path.casefold(): relative_path
            for relative_path in desired
        }
        previous_by_key = {
            relative_path.casefold(): (relative_path, metadata)
            for relative_path, metadata in previous_files.items()
        }

        for relative_path, spec in desired.items():
            target = safe_real_child_path(registered_path, relative_path)
            if not target:
                return {"error": f"Unsafe project path: {relative_path}"}
            if os.path.isdir(target):
                return {"error": f"File destination is a directory: {relative_path}"}

            exists = os.path.isfile(target)
            current_hash = get_file_md5(target) if exists else ""
            previous = previous_by_key.get(relative_path.casefold(), ("", {}))[1]
            owner_matches = previous.get("owner") == spec["owner"]
            if not exists:
                action = "add"
            elif current_hash == spec["hash"]:
                action = "unchanged" if owner_matches else "adopt"
            else:
                action = "modify"

            conflict = False
            reason = ""
            reason_code = ""
            if action == "adopt":
                reason = "Existing matching project copy will be added to the SkillHub manifest"
                reason_code = "adopt_existing_copy"
            if relative_path.casefold() in source_collision_keys:
                conflict = True
                reason = "Multiple selected skills provide this path"
            if action == "modify" and not spec.get("merge_safe"):
                if not previous:
                    conflict = True
                    reason = "The destination is not managed by SkillHub"
                elif current_hash != previous.get("hash", ""):
                    conflict = True
                    reason = "The managed destination was modified in the project"

            changes.append({
                "path": relative_path,
                "action": action,
                "owner": spec["owner"],
                "before_hash": current_hash,
                "after_hash": spec["hash"],
                "conflict": conflict,
                "reason": reason,
                "reason_code": reason_code,
                "requires_bundle_authorization": bool(
                    spec.get("requires_bundle_authorization")
                ),
                "spec": spec,
            })

        change_keys = {
            item["path"].casefold()
            for item in changes
        }
        previous_keys = {
            relative_path.casefold()
            for relative_path in previous_files
        }
        preserved_keys = {
            relative_path.casefold()
            for relative_path in preserved_files
        }
        enabled_set = set(effective_enabled)
        disabled_filenames = [
            skill.get("filename", "")
            for skill in global_skills
            if skill.get("filename")
            and skill.get("filename") not in enabled_set
            and not skill.get("project_only")
        ]
        legacy_desired, _metadata, legacy_collisions = (
            self._collect_desired_sync_files(
                registered_path,
                disabled_filenames,
                global_skills=global_skills,
            )
        )
        for relative_path, spec in legacy_desired.items():
            filename = spec.get("owner", "")
            if not filename or filename == "__agents_index__":
                continue
            path_key = relative_path.casefold()
            if (
                path_key in change_keys
                or path_key in previous_keys
                or path_key in preserved_keys
                or path_key in desired_keys
            ):
                continue
            target = safe_real_child_path(registered_path, relative_path)
            if not target or not os.path.isfile(target):
                continue
            current_hash = get_file_md5(target)
            matches_source = current_hash == spec["hash"]
            source_collision = path_key in legacy_collisions
            changes.append({
                "path": relative_path,
                "action": "delete",
                "owner": filename,
                "before_hash": current_hash,
                "after_hash": "",
                "conflict": not matches_source or source_collision,
                "reason": (
                    "Multiple disabled Skills map to this unmanaged project path"
                    if source_collision
                    else "Unmanaged project copy differs from the global Skill"
                    if not matches_source
                    else "Matching legacy project copy is not recorded in the SkillHub manifest"
                ),
                "reason_code": (
                    "unmanaged_source_collision"
                    if source_collision
                    else "unmanaged_modified_copy"
                    if not matches_source
                    else "unmanaged_matching_copy"
                ),
                "requires_bundle_authorization": False,
                "spec": None,
            })
            change_keys.add(path_key)

        for relative_path, previous in previous_files.items():
            if relative_path.casefold() in desired_keys:
                continue
            target = safe_real_child_path(registered_path, relative_path)
            if not target or not os.path.isfile(target):
                continue
            current_hash = get_file_md5(target)
            if current_hash == previous.get("hash", ""):
                action = "delete"
                reason = ""
            else:
                action = "preserve"
                reason = "The managed file was modified in the project"
            changes.append({
                "path": relative_path,
                "action": action,
                "owner": previous.get("owner", ""),
                "before_hash": current_hash,
                "after_hash": "",
                "conflict": False,
                "reason": reason,
                "reason_code": (
                    "managed_modified_copy_preserved"
                    if action == "preserve"
                    else ""
                ),
                "requires_bundle_authorization": False,
                "spec": None,
            })

        changes.sort(key=lambda item: (item["action"], item["path"].lower()))
        return {
            "project_path": registered_path,
            "enabled_skills": effective_enabled,
            "desired": desired,
            "active_metadata": active_metadata,
            "previous_manifest": previous_manifest,
            "preserved_files": preserved_files,
            "scope_conflicts": scope_conflicts,
            "changes": changes,
        }

    def _public_sync_preview(self, plan: dict) -> dict:
        if plan.get("error"):
            return {"error": plan["error"]}
        summary = {
            "add": 0,
            "adopt": 0,
            "modify": 0,
            "delete": 0,
            "preserve": 0,
            "unchanged": 0,
            "conflict": 0,
        }
        changes = []
        for item in plan["changes"]:
            summary[item["action"]] += 1
            if item["conflict"]:
                summary["conflict"] += 1
            changes.append({
                "path": item["path"],
                "action": item["action"],
                "owner": item["owner"],
                "conflict": item["conflict"],
                "reason": item["reason"],
                "reason_code": item.get("reason_code", ""),
                "requires_bundle_authorization": item[
                    "requires_bundle_authorization"
                ],
            })
        scope_conflicts = list(plan.get("scope_conflicts", []))
        summary["conflict"] += len(scope_conflicts)
        token_payload = {
            "enabled_skills": plan["enabled_skills"],
            "scope_conflicts": scope_conflicts,
            "changes": [
                {
                    "path": item["path"],
                    "action": item["action"],
                    "before_hash": item["before_hash"],
                    "after_hash": item["after_hash"],
                    "conflict": item["conflict"],
                    "requires_bundle_authorization": item[
                        "requires_bundle_authorization"
                    ],
                }
                for item in plan["changes"]
            ],
        }
        plan_token = get_bytes_md5(
            json.dumps(token_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        )
        restricted_bundle_files = [
            item["path"]
            for item in plan["changes"]
            if item["requires_bundle_authorization"]
            and item["action"] in ("add", "modify")
        ]
        return {
            "ok": True,
            "summary": summary,
            "changes": changes,
            "enabled_skills": list(plan["enabled_skills"]),
            "synced_count": len(plan["active_metadata"]),
            "scope_conflict_count": len(scope_conflicts),
            "scope_conflicts": scope_conflicts,
            "has_conflicts": summary["conflict"] > 0,
            "has_restricted_bundle_files": bool(restricted_bundle_files),
            "restricted_bundle_files": restricted_bundle_files,
            "plan_token": plan_token,
        }

    def preview_sync(self, project_path, enabled_skills):
        """Return a read-only synchronization plan."""
        return self._public_sync_preview(self._build_sync_plan(project_path, enabled_skills))

    def _rollback_applied_changes(self, project_path: str, backup_root: str, changes: list):
        for change in reversed(changes):
            target = safe_real_child_path(project_path, change["path"])
            if not target:
                continue
            backup_name = change.get("backup")
            backup = os.path.join(backup_root, backup_name) if backup_name else ""
            try:
                if change["action"] == "add":
                    if os.path.isfile(target):
                        os.remove(target)
                elif backup and os.path.isfile(backup):
                    atomic_copy_file(backup, target)
            except OSError:
                continue

    def _write_sync_target(self, target: str, spec: dict):
        if spec.get("source"):
            if get_file_md5(spec["source"]) != spec["hash"]:
                raise OSError(f"Source changed while syncing: {spec['path']}")
            atomic_copy_file(spec["source"], target)
        else:
            atomic_write_text(target, spec.get("content") or "")

    def sync_skills(self, project_path, enabled_skills, allow_conflicts=False, preview_token="", allow_bundle_files=False):
        with file_lock(project_path):
            return self._sync_skills(project_path, enabled_skills, allow_conflicts, preview_token, allow_bundle_files)

    def _sync_skills(
        self,
        project_path,
        enabled_skills,
        allow_conflicts=False,
        preview_token="",
        allow_bundle_files=False,
    ):
        """Apply a previewed synchronization plan with backup and ownership tracking."""
        plan = self._build_sync_plan(project_path, enabled_skills)
        preview = self._public_sync_preview(plan)
        if preview.get("error"):
            return preview
        if preview_token and preview_token != preview["plan_token"]:
            return {
                "requires_confirmation": True,
                "plan_changed": True,
                "preview": preview,
                "error": "",
            }
        if preview["has_conflicts"] and not allow_conflicts:
            return {
                "requires_confirmation": True,
                "preview": preview,
                "error": "",
            }
        if preview["has_restricted_bundle_files"] and not allow_bundle_files:
            return {
                "requires_bundle_file_confirmation": True,
                "preview": preview,
                "error": "",
            }

        project_path = plan["project_path"]
        actionable = [
            item for item in plan["changes"]
            if item["action"] in ("add", "modify", "delete")
        ]

        # Abort before writing if any destination changed after planning.
        for item in actionable:
            target = safe_real_child_path(project_path, item["path"])
            current_hash = get_file_md5(target) if target and os.path.isfile(target) else ""
            if current_hash != item["before_hash"]:
                return {"error": f"Project file changed during synchronization: {item['path']}"}

        state_paths = self._sync_state_paths(project_path)
        if not state_paths["state_dir"]:
            return {"error": "Unsafe synchronization state directory"}
        transaction_id = uuid.uuid4().hex
        backup_root = os.path.join(state_paths["backups"], transaction_id)
        os.makedirs(os.path.join(backup_root, "files"), exist_ok=True)
        applied = []

        try:
            for index, item in enumerate(actionable):
                target = safe_real_child_path(project_path, item["path"])
                if not target:
                    raise OSError(f"Unsafe project path: {item['path']}")
                change = {
                    "path": item["path"],
                    "action": item["action"],
                    "before_hash": item["before_hash"],
                    "after_hash": item["after_hash"],
                }
                if item["action"] in ("modify", "delete"):
                    backup_name = normalize_relative_path(
                        os.path.join("files", f"{index:04d}.bak")
                    )
                    atomic_copy_file(target, os.path.join(backup_root, backup_name))
                    change["backup"] = backup_name

                applied.append(change)
                if item["action"] == "delete":
                    os.remove(target)
                else:
                    self._write_sync_target(target, item["spec"])

            preserved_manifest = {}
            desired_keys = {
                relative_path.casefold()
                for relative_path in plan["desired"]
            }
            for relative_path, metadata in plan.get("preserved_files", {}).items():
                if relative_path.casefold() in desired_keys:
                    continue
                target = safe_real_child_path(project_path, relative_path)
                if target and os.path.isfile(target):
                    preserved_manifest[relative_path] = {
                        "hash": get_file_md5(target),
                        "owner": metadata.get("owner", ""),
                    }
            for item in plan["changes"]:
                if item["action"] != "preserve":
                    continue
                preserved_manifest[item["path"]] = {
                    "hash": item["before_hash"],
                    "owner": item["owner"],
                }

            new_manifest = {
                "version": 1,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "enabled_skills": list(enabled_skills or []),
                "files": {
                    relative_path: {
                        "hash": spec["hash"],
                        "owner": spec["owner"],
                    }
                    for relative_path, spec in plan["desired"].items()
                },
                "preserved_files": preserved_manifest,
            }
            transaction = {
                "version": 1,
                "id": transaction_id,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "had_manifest": bool(plan["previous_manifest"]),
                "previous_manifest": plan["previous_manifest"],
                "changes": applied,
            }
            atomic_write_json(state_paths["manifest"], new_manifest)
            atomic_write_json(os.path.join(backup_root, "transaction.json"), transaction)
            atomic_write_json(
                state_paths["last_transaction"],
                {"id": transaction_id, "created_at": transaction["created_at"]},
            )
        except Exception as exc:
            self._rollback_applied_changes(project_path, backup_root, applied)
            if plan["previous_manifest"]:
                atomic_write_json(state_paths["manifest"], plan["previous_manifest"])
            elif os.path.exists(state_paths["manifest"]):
                os.remove(state_paths["manifest"])
            return {"error": str(exc)}

        history_warning = ""
        if hasattr(self, "_remember_sync_result"):
            try:
                self._remember_sync_result(project_path, preview, transaction, backup_root)
            except OSError:
                history_warning = "同步成功，但结果记录未保存 / Sync succeeded, but result history could not be saved"
        return {
            "ok": True,
            "history_warning": history_warning,
            "synced_count": len(plan["active_metadata"]),
            "summary": preview["summary"],
            "transaction_id": transaction_id,
        }

    def undo_last_sync(self, project_path):
        with file_lock(project_path):
            return self._undo_last_sync(project_path)

    def _undo_last_sync(self, project_path):
        """Undo the most recent sync unless a resulting file was edited afterward."""
        registered_path = self._registered_project_path(project_path)
        if not registered_path or not os.path.isdir(registered_path):
            return {"error": "Project path is not registered or does not exist"}
        state_paths = self._sync_state_paths(registered_path)
        if not state_paths["state_dir"]:
            return {"error": "Unsafe synchronization state directory"}
        pointer = load_json_file(state_paths["last_transaction"], {})
        transaction_id = pointer.get("id", "") if isinstance(pointer, dict) else ""
        if not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
            return {"error": "No synchronization is available to undo"}

        backup_root = safe_real_child_path(
            state_paths["backups"], transaction_id
        )
        if not backup_root:
            return {"error": "Invalid synchronization backup"}
        transaction_path = os.path.join(backup_root, "transaction.json")
        transaction = load_json_file(transaction_path, {})
        if transaction.get("id") != transaction_id:
            return {"error": "Synchronization backup is missing or invalid"}

        restored = []
        skipped = []
        for change in reversed(transaction.get("changes", [])):
            relative_path = change.get("path", "")
            target = safe_real_child_path(registered_path, relative_path)
            if not target:
                skipped.append(relative_path)
                continue
            action = change.get("action")
            current_hash = get_file_md5(target) if os.path.isfile(target) else ""
            backup_name = change.get("backup", "")
            backup = safe_real_child_path(backup_root, backup_name) if backup_name else ""
            try:
                if action == "add":
                    if current_hash != change.get("after_hash", ""):
                        skipped.append(relative_path)
                        continue
                    os.remove(target)
                elif action == "modify":
                    if current_hash != change.get("after_hash", "") or not os.path.isfile(backup):
                        skipped.append(relative_path)
                        continue
                    atomic_copy_file(backup, target)
                elif action == "delete":
                    if current_hash or not os.path.isfile(backup):
                        skipped.append(relative_path)
                        continue
                    atomic_copy_file(backup, target)
                else:
                    skipped.append(relative_path)
                    continue
                restored.append(relative_path)
            except OSError:
                skipped.append(relative_path)

        previous_manifest = transaction.get("previous_manifest", {})
        if isinstance(previous_manifest, dict):
            previous_files = previous_manifest.get("files", {})
            if isinstance(previous_files, dict):
                for relative_path in skipped:
                    previous_files.pop(relative_path, None)
            if transaction.get("had_manifest"):
                atomic_write_json(state_paths["manifest"], previous_manifest)
            elif os.path.exists(state_paths["manifest"]):
                os.remove(state_paths["manifest"])

        transaction["undone_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        transaction["undo_skipped"] = skipped
        atomic_write_json(transaction_path, transaction)
        if os.path.exists(state_paths["last_transaction"]):
            os.remove(state_paths["last_transaction"])
        return {
            "ok": True,
            "restored_count": len(restored),
            "skipped_count": len(skipped),
            "skipped": skipped,
        }
