"""Skill library query, editing, deletion, and restoration endpoints."""

import json
import os
import re
import shutil
import time
import uuid
import copy
from skillhub.infrastructure.json_store import file_lock
from skillhub.infrastructure.transactions import capture_files, restore_files, persist_snapshot

from skillhub.domain.catalog import parse_markdown_metadata
from skillhub.domain.collections import COLLECTION_DISPLAY_LOCALIZATIONS
from skillhub.domain.frontmatter import (
    frontmatter_top_level_keys,
    remove_markdown_frontmatter_field,
    split_markdown_frontmatter,
    split_markdown_frontmatter_source,
)
from skillhub.domain.global_targets import GLOBAL_SKILL_TARGETS, SKILL_LIBRARY_STATE_DIR
from skillhub.domain.naming import (
    is_project_rules_document,
    normalize_agent_skill_name,
    normalize_skill_filename,
)
from skillhub.infrastructure.filesystem import (
    atomic_write_json,
    atomic_write_text,
    load_json_file,
    safe_child_path,
    safe_real_child_path,
)


class LibraryApiMixin:
    """Manage the active local Skill library."""

    def _library_metadata_snapshot(self):
        return capture_files([
            self._library_index_path(), self._skill_collections_path(),
            self._display_localizations_path(), self._skill_import_paths()["catalog"],
        ])

    def _cached_skill_metadata(self, path):
        stat = os.stat(path)
        signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
        cache = getattr(self, "_skill_metadata_cache", {})
        old = cache.get(path)
        if not old or old[0] != signature:
            if len(cache) >= 20000:
                cache.clear()
            cache[path] = (signature, parse_markdown_metadata(path))
            self._skill_metadata_cache = cache
        return copy.deepcopy(cache[path][1])

    def get_skills(self):
        """Return list of all global skill metadata (files and directories)."""
        return self._collect_skills(include_global_state=True)

    def _collect_skills(self, *, include_global_state: bool):
        """Collect library metadata with optional publication-state inspection."""
        skills = []
        os.makedirs(self.skills_dir, exist_ok=True)
        if os.path.exists(self.skills_dir):
            for item in sorted(os.listdir(self.skills_dir)):
                if item.startswith("."):
                    continue
                fp = os.path.join(self.skills_dir, item)
                if os.path.isdir(fp):
                    skill_fp = os.path.join(fp, "SKILL.md")
                    readme_fp = os.path.join(fp, "README.md")
                    if os.path.isfile(skill_fp):
                        meta = self._cached_skill_metadata(skill_fp)
                        meta["folder_kind"] = "standard"
                    elif os.path.exists(readme_fp):
                        meta = self._cached_skill_metadata(readme_fp)
                        meta["folder_kind"] = "bundle"
                    else:
                        meta = {
                            "title": item,
                            "emoji": "📦",
                            "category": "工作流程" if self.language == "zh" else "Workflow",
                            "tags": ["主控", "模板", "项目级"] if self.language == "zh" else ["Master", "Template", "Project-Level"],
                            "description": "主控模板文件夹" if self.language == "zh" else "Master template folder",
                            "folder_kind": "bundle",
                        }
                    meta["filename"] = item
                    meta["is_dir"] = True
                    if include_global_state:
                        meta.update(self._codex_global_skill_state(item, fp))
                    skills.append(meta)
                elif os.path.isfile(fp) and item.lower().endswith(".md"):
                    meta = self._cached_skill_metadata(fp)
                    meta["is_dir"] = False
                    if include_global_state:
                        meta.update(self._codex_global_skill_state(item, fp))
                    skills.append(meta)
        collections = self._load_skill_collections().get("collections", [])
        for collection in collections:
            parent = collection.get("bundle_parent", "")
            for virtual_id, relative_path in collection.get(
                "member_sources",
                {},
            ).items():
                source = safe_real_child_path(
                    os.path.join(self.skills_dir, parent),
                    relative_path,
                )
                if not source or not os.path.isfile(source):
                    continue
                meta = self._cached_skill_metadata(source)
                meta.update({
                    "filename": virtual_id,
                    "display_filename": os.path.basename(relative_path),
                    "is_dir": False,
                    "is_virtual": True,
                    "virtual_parent": parent,
                    "virtual_source": relative_path,
                    "target_filename": os.path.basename(relative_path),
                })
                if include_global_state:
                    meta.update(self._codex_global_skill_state(virtual_id, source))
                skills.append(meta)

        display_localizations = self._load_display_localizations()
        for skill in skills:
            source = os.path.join(self.skills_dir, skill.get("virtual_parent", ""), skill.get("virtual_source", "")) if skill.get("is_virtual") else os.path.join(self.skills_dir, skill["filename"])
            if os.path.isdir(source):
                source = os.path.join(source, "SKILL.md" if skill.get("folder_kind") == "standard" else "README.md")
            try:
                skill["modified_at"] = os.stat(source).st_mtime
            except OSError:
                skill["modified_at"] = 0
            self._apply_display_localization(skill, display_localizations)

        skills_by_name = {
            skill["filename"]: skill for skill in skills
        }
        for collection in collections:
            collection_locale = (
                COLLECTION_DISPLAY_LOCALIZATIONS
                .get(collection.get("id", ""), {})
                .get(self.language, {})
            )
            members = [
                member for member in collection.get("members", [])
                if member in skills_by_name
            ]
            if len(members) < 2:
                continue
            enabled_members = set(collection.get("enabled_members", []))
            controller = self._collection_controller(collection)
            controller_enabled = not controller or controller in enabled_members
            for member in members:
                member_locale = collection_locale.get("members", {}).get(
                    member,
                    {},
                )
                if member_locale:
                    skills_by_name[member]["display_title"] = (
                        member_locale.get("title")
                        or skills_by_name[member]["title"]
                    )
                    skills_by_name[member]["display_description"] = (
                        member_locale.get("description")
                        or skills_by_name[member]["description"]
                    )
                skills_by_name[member]["collection"] = {
                    "id": collection["id"],
                    "title": collection.get("title", collection["id"]),
                    "category": str(collection.get("category", "")).strip(),
                    "display_title": collection_locale.get("title", ""),
                    "display_description": collection_locale.get(
                        "description",
                        "",
                    ),
                    "members": members,
                    "member_count": len(members),
                    "enabled": member in enabled_members,
                    "effective_enabled": (
                        member in enabled_members and controller_enabled
                    ),
                    "controller": controller,
                    "is_controller": member == controller,
                    "controller_enabled": controller_enabled,
                }
        return skills

    def get_skill_content(self, filename):
        """Return raw content of a skill file or the README.md inside a skill directory."""
        fp = safe_child_path(self.skills_dir, filename)
        if not fp:
            return {"error": "Invalid filename"}
        if not os.path.exists(fp):
            fp = self._resolve_virtual_skill(filename).get("path", "")
        if os.path.isdir(fp):
            skill_fp = os.path.join(fp, "SKILL.md")
            fp = skill_fp if os.path.isfile(skill_fp) else os.path.join(fp, "README.md")
        if not os.path.exists(fp):
            return {"error": "File not found"}
        try:
            with open(fp, "r", encoding="utf-8") as f:
                return {"content": f.read()}
        except Exception as e:
            return {"error": str(e)}

    def get_project_skill_content(self, project_path: str, relative_path: str):
        """Read a discovered project-only skill without adopting or modifying it."""
        requested_project = os.path.normcase(
            os.path.realpath(os.path.abspath(project_path or ""))
        )
        registered_project = next(
            (
                item.get("path", "")
                for item in self.projects
                if os.path.normcase(
                    os.path.realpath(os.path.abspath(item.get("path", "")))
                ) == requested_project
            ),
            "",
        )
        if not registered_project:
            return {"error": "Project is not registered"}

        project_entry = self.get_project(registered_project)
        allowed_paths = {
            item.get("project_relative_path", "")
            for item in project_entry.get("project_skills", [])
        }
        if relative_path not in allowed_paths:
            return {"error": "Project skill is not available"}

        skills_root = os.path.join(registered_project, ".agent", "skills")
        target = safe_real_child_path(skills_root, relative_path)
        if not target or not os.path.isfile(target):
            return {"error": "File not found"}
        try:
            with open(target, "r", encoding="utf-8") as handle:
                return {"content": handle.read()}
        except Exception as e:
            return {"error": str(e)}

    def save_skill(self, filename, content):
        """Save content to a global skill file or a skill directory's README.md."""
        fp = safe_child_path(self.skills_dir, filename)
        if not fp:
            return {"error": "Invalid filename"}
        if os.path.isdir(fp):
            skill_fp = os.path.join(fp, "SKILL.md")
            fp = skill_fp if os.path.isfile(skill_fp) else os.path.join(fp, "README.md")
        try:
            with open(fp, "w", encoding="utf-8") as f:
                f.write(content)
            self._register_library_entry(filename, source="edited")
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}

    def _editable_skill_source(self, filename: str) -> dict:
        """Resolve a global skill to the source file that owns its Frontmatter."""
        fp = safe_child_path(self.skills_dir, filename)
        owner = filename
        if fp and os.path.isdir(fp):
            skill_fp = os.path.join(fp, "SKILL.md")
            readme_fp = os.path.join(fp, "README.md")
            fp = skill_fp if os.path.isfile(skill_fp) else readme_fp
        elif not fp or not os.path.isfile(fp):
            virtual = self._resolve_virtual_skill(filename)
            fp = virtual.get("path", "")
            owner = virtual.get("parent", "")
        if not fp or not os.path.isfile(fp):
            return {}
        return {"path": fp, "owner": owner or filename}

    def _skill_category_sources(self, category: str) -> list:
        """Collect unique editable global source files using an exact category."""
        requested = str(category or "").strip()
        if not requested or requested in ("未分类", "Uncategorized"):
            return []
        sources = {}
        for skill in self.get_skills():
            if str(skill.get("category", "")).strip() != requested:
                continue
            resolved = self._editable_skill_source(skill.get("filename", ""))
            path = resolved.get("path", "")
            if not path:
                continue
            normalized_path = os.path.normcase(os.path.realpath(path))
            if normalized_path in sources:
                sources[normalized_path]["filenames"].append(skill.get("filename", ""))
                continue
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    content = handle.read()
            except OSError:
                continue
            metadata, _body = split_markdown_frontmatter(content)
            if str(metadata.get("category", "")).strip() != requested:
                continue
            raw_frontmatter, _body, has_frontmatter = split_markdown_frontmatter_source(content)
            if not has_frontmatter or "category" not in frontmatter_top_level_keys(raw_frontmatter):
                continue
            sources[normalized_path] = {
                "path": path,
                "owner": resolved.get("owner", skill.get("filename", "")),
                "content": content,
                "filenames": [skill.get("filename", "")],
                "title": skill.get("display_title") or skill.get("title") or skill.get("filename", ""),
            }
        return list(sources.values())

    def preview_delete_skill_category(self, category: str) -> dict:
        """Preview global source files that would become uncategorized."""
        requested = str(category or "").strip()
        if not requested or requested in ("未分类", "Uncategorized"):
            return {"error": "The default category cannot be deleted"}
        sources = self._skill_category_sources(requested)
        collections = [
            collection
            for collection in self._load_skill_collections().get("collections", [])
            if str(collection.get("category", "")).strip() == requested
        ]
        return {
            "ok": True,
            "category": requested,
            "affected_count": len(sources) + len(collections),
            "affected": [
                {
                    "filename": source["filenames"][0],
                    "title": source["title"],
                }
                for source in sources
            ] + [
                {
                    "filename": f"@collection:{collection['id']}",
                    "title": collection.get("title", collection["id"]),
                }
                for collection in collections
            ],
        }

    def delete_skill_category(self, category: str) -> dict:
        """Remove a category from global Skill Frontmatter with rollback on failure."""
        requested = str(category or "").strip()
        if not requested or requested in ("未分类", "Uncategorized"):
            return {"error": "The default category cannot be deleted"}
        sources = self._skill_category_sources(requested)
        collection_state = self._load_skill_collections()
        affected_collections = [
            collection
            for collection in collection_state.get("collections", [])
            if str(collection.get("category", "")).strip() == requested
        ]
        if not sources and not affected_collections:
            return {"error": "No editable global Skill uses this category"}

        written = []
        try:
            for source in sources:
                updated = remove_markdown_frontmatter_field(source["content"], "category")
                if updated == source["content"]:
                    raise ValueError(f"Category field not found: {source['path']}")
                atomic_write_text(source["path"], updated)
                written.append(source)
            for collection in affected_collections:
                collection.pop("category", None)
            if affected_collections:
                self._save_skill_collections(collection_state)
        except Exception as error:
            rollback_errors = []
            for source in reversed(written):
                try:
                    atomic_write_text(source["path"], source["content"])
                except Exception as rollback_error:
                    rollback_errors.append(str(rollback_error))
            if affected_collections:
                for collection in affected_collections:
                    collection["category"] = requested
                try:
                    self._save_skill_collections(collection_state)
                except Exception as rollback_error:
                    rollback_errors.append(str(rollback_error))
            message = str(error)
            if rollback_errors:
                message += "; rollback failed: " + "; ".join(rollback_errors)
            return {"error": message, "rolled_back": not rollback_errors}

        index_warnings = []
        for owner in dict.fromkeys(source["owner"] for source in sources):
            try:
                self._register_library_entry(owner, source="edited")
            except Exception as error:
                index_warnings.append(str(error))
        return {
            "ok": True,
            "category": requested,
            "affected_count": len(sources) + len(affected_collections),
            "affected": [
                *[source["filenames"][0] for source in sources],
                *[f"@collection:{item['id']}" for item in affected_collections],
            ],
            "warning": "; ".join(index_warnings),
        }

    def delete_skill(self, filename):
        with file_lock(self.skills_dir):
            return self._delete_skill(filename)

    def _delete_skill(self, filename):
        """Move a global skill into SkillHub trash so it can be restored."""
        fp = safe_child_path(self.skills_dir, filename)
        if not fp:
            return {"error": "Invalid filename"}
        trash_root = ""
        trash_item = ""
        collection_snapshot = None
        global_targets_were_enabled = []
        snapshot = self._library_metadata_snapshot()
        try:
            if os.path.exists(fp):
                descriptor = self._codex_global_skill_descriptor(filename, fp)
                global_states = [
                    self._global_target_state(descriptor, target_id)
                    for target_id in GLOBAL_SKILL_TARGETS
                ]
                enabled_states = [
                    state for state in global_states if state["enabled"]
                ]
                unmanaged = [
                    state for state in enabled_states if not state["managed"]
                ]
                if unmanaged:
                    return {
                        "error": (
                            "Remove the real global Skill directory before "
                            f'deleting: {unmanaged[0]["label"]}'
                        )
                    }
                for global_state in enabled_states:
                    disabled = self._set_global_skill_target(
                        filename,
                        False,
                        global_state["id"],
                        fp,
                        descriptor,
                    )
                    if disabled.get("error"):
                        for target_id in global_targets_were_enabled:
                            self._set_global_skill_target(
                                filename, True, target_id, fp, descriptor
                            )
                        return disabled
                    global_targets_were_enabled.append(global_state["id"])
                if (
                    descriptor.get("adapted")
                    and not self._codex_global_adapter_in_use(descriptor)
                    and os.path.isdir(descriptor["link_source"])
                ):
                    shutil.rmtree(descriptor["link_source"])
                collection_snapshot = self._load_skill_collections()
                trash_token = uuid.uuid4().hex
                trash_root = safe_real_child_path(
                    self.skills_dir,
                    os.path.join(SKILL_LIBRARY_STATE_DIR, "trash", trash_token),
                )
                if not trash_root:
                    return {"error": "Invalid trash path"}
                os.makedirs(trash_root, exist_ok=False)
                persist_snapshot(snapshot, os.path.join(trash_root, "rollback-metadata"))
                trash_item = safe_real_child_path(trash_root, filename)
                if not trash_item:
                    shutil.rmtree(trash_root, ignore_errors=True)
                    return {"error": "Invalid trash item path"}
                atomic_write_json(os.path.join(trash_root, "metadata.json"), {
                    "version": 1,
                    "filename": filename,
                    "deleted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "collections": collection_snapshot,
                    "global_targets_were_enabled": global_targets_were_enabled,
                    "codex_global_was_enabled": "codex" in global_targets_were_enabled,
                })
                shutil.move(fp, trash_item)
                self._unregister_library_entry(filename)
                state = self._load_skill_collections()
                changed = False
                retained = []
                for collection in state.get("collections", []):
                    if collection.get("bundle_parent") == filename:
                        changed = True
                        continue
                    members = [
                        member for member in collection.get("members", [])
                        if member != filename
                    ]
                    if members != collection.get("members", []):
                        changed = True
                    collection["members"] = members
                    collection["enabled_members"] = [
                        member
                        for member in collection.get("enabled_members", [])
                        if member != filename
                    ]
                    if len(members) >= 2:
                        retained.append(collection)
                if changed:
                    state["collections"] = retained
                    self._save_skill_collections(state)
                return {
                    "ok": True,
                    "filename": filename,
                    "trash_token": trash_token,
                }
            return {"error": "文件不存在" if self.language == "zh" else "File does not exist"}
        except Exception as e:
            rollback_errors = []
            if trash_item and os.path.exists(trash_item) and not os.path.exists(fp):
                try:
                    shutil.move(trash_item, fp)
                except OSError as error:
                    rollback_errors.append(str(error))
            rollback_errors.extend(restore_files(snapshot))
            if os.path.exists(fp):
                descriptor = self._codex_global_skill_descriptor(filename, fp)
                for target_id in global_targets_were_enabled:
                    restored = self._set_global_skill_target(filename, True, target_id, fp, descriptor)
                    if restored.get("error"):
                        rollback_errors.append(restored["error"])
            retained = bool(trash_item and os.path.exists(trash_item))
            if trash_root and not retained and not rollback_errors:
                shutil.rmtree(trash_root, ignore_errors=True)
            return {"error": str(e), "rolled_back": not rollback_errors,
                    "rollback_errors": rollback_errors,
                    "recovery_path": trash_root if retained or rollback_errors else ""}

    def restore_deleted_skill(self, trash_token: str):
        with file_lock(self.skills_dir):
            return self._restore_deleted_skill(trash_token)

    def _restore_deleted_skill(self, trash_token: str):
        """Restore one skill and its collection metadata from SkillHub trash."""
        if not re.fullmatch(r"[0-9a-f]{32}", trash_token or ""):
            return {"error": "Invalid trash token"}
        trash_root = safe_real_child_path(
            self.skills_dir,
            os.path.join(SKILL_LIBRARY_STATE_DIR, "trash", trash_token),
        )
        if not trash_root or not os.path.isdir(trash_root):
            return {"error": "Deleted skill is no longer available"}
        metadata = load_json_file(os.path.join(trash_root, "metadata.json"), {})
        filename = metadata.get("filename", "") if isinstance(metadata, dict) else ""
        source = safe_real_child_path(trash_root, filename)
        target = safe_child_path(self.skills_dir, filename)
        if not filename or not source or not os.path.exists(source) or not target:
            return {"error": "Deleted skill metadata is invalid"}
        if os.path.exists(target):
            return {"error": "A skill with the same name already exists"}
        snapshot = self._library_metadata_snapshot()
        try:
            persist_snapshot(snapshot, os.path.join(trash_root, "restore-metadata"))
            shutil.move(source, target)
            collections = metadata.get("collections")
            if isinstance(collections, dict):
                current = self._load_skill_collections()
                current_collections = current.setdefault("collections", [])
                for old in collections.get("collections", []):
                    if old.get("bundle_parent") != filename and filename not in old.get("members", []):
                        continue
                    existing = next((c for c in current_collections if c.get("id") == old.get("id")), None)
                    if existing is None:
                        current_collections.append(old)
                    else:
                        restored_members = old.get("members", []) if old.get("bundle_parent") == filename else [filename]
                        existing["members"] = list(dict.fromkeys([*existing.get("members", []), *restored_members]))
                        existing["enabled_members"] = list(dict.fromkeys([*existing.get("enabled_members", []), *[m for m in old.get("enabled_members", []) if m in restored_members]]))
                self._save_skill_collections(current)
            self._register_library_entry(filename, source="restored")
            warning = ""
            enabled_targets = metadata.get("global_targets_were_enabled", [])
            if not isinstance(enabled_targets, list):
                enabled_targets = []
            if metadata.get("codex_global_was_enabled") and "codex" not in enabled_targets:
                enabled_targets.append("codex")
            descriptor = self._codex_global_skill_descriptor(filename, target)
            restore_warnings = []
            for target_id in enabled_targets:
                global_result = self._set_global_skill_target(
                    filename, True, target_id, target, descriptor
                )
                if global_result.get("error"):
                    restore_warnings.append(global_result["error"])
            warning = "; ".join(restore_warnings)
            shutil.rmtree(trash_root, ignore_errors=True)
            return {"ok": True, "filename": filename, "warning": warning}
        except Exception as exc:
            rollback_errors = []
            if os.path.exists(target) and not os.path.exists(source):
                try:
                    shutil.move(target, source)
                except OSError as error:
                    rollback_errors.append(str(error))
            rollback_errors.extend(restore_files(snapshot))
            return {"error": str(exc), "rolled_back": not rollback_errors,
                    "rollback_errors": rollback_errors, "recovery_path": trash_root}

    def create_skill(self, filename):
        """Create a portable <name>/SKILL.md package with a bilingual template."""
        requested = normalize_skill_filename(filename)
        if requested.lower().endswith(".md"):
            requested = requested[:-3]
        if not requested or is_project_rules_document(filename):
            return {"error": "Invalid skill name"}
        skill_name = normalize_agent_skill_name(requested, requested)
        folder = safe_child_path(self.skills_dir, skill_name)
        if not folder:
            return {"error": "Invalid skill name"}
        if os.path.exists(folder) or os.path.exists(folder + ".md"):
            return {"error": "该文件已存在" if self.language == "zh" else "This file already exists"}

        title = requested.replace("_", " ").replace("-", " ").strip()
        if not title:
            title = "New Skill Guideline" if self.language == "en" else "新增技能指南"

        if self.language == "en":
            template = f"""---
name: {skill_name}
title: {json.dumps(title, ensure_ascii=False)}
emoji: 💡
tags: Rules, Basic
description: Define the purpose, usage triggers, and development constraints for {title}.
---

# 💡 {title}

Write down the specific development guidelines, design principles, and quality red lines for this skill here.

## 🎯 Core Rules & Details
- **Rule 1**: ...
- **Rule 2**: ...
"""
        else:
            template = f"""---
name: {skill_name}
title: {json.dumps(title, ensure_ascii=False)}
emoji: 💡
tags: 规范, 基础
description: 定义“{title}”的适用场景、触发条件与开发约束。
---

# 💡 {title}

在这里编写针对此项技能的具体开发指南、设计原则与质量红线规约。

## 🎯 核心规范细节
- **第一条**: ...
- **第二条**: ...
"""
        try:
            os.makedirs(self.skills_dir, exist_ok=True)
            os.mkdir(folder)
            atomic_write_text(os.path.join(folder, "SKILL.md"), template)
            self._register_library_entry(skill_name, source="created")
            return {"ok": True, "filename": skill_name}
        except Exception as e:
            return {"error": str(e)}
