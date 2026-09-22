"""Project registration and read-only status endpoints."""

import os
import webview

from skillhub.domain.catalog import parse_markdown_metadata
from skillhub.domain.naming import normalize_relative_path
from skillhub.infrastructure.filesystem import (
    get_file_md5,
    load_json_file,
    safe_real_child_path,
)
from skillhub.infrastructure.sync_status import (
    SYNC_LAST_TRANSACTION_NAME,
    SYNC_MANIFEST_NAME,
    SYNC_STATE_DIR,
    check_dir_sync_status,
)


class ProjectsApiMixin:
    """Manage registered projects and summarize their current state."""

    def get_projects(self):
        """Return projects list with per-skill sync status."""
        return self._collect_projects(self.projects)

    def get_project(self, project_path: str):
        """Inspect one registered project without scanning unrelated projects."""
        registered_path = self._registered_project_path(project_path)
        if not registered_path:
            return {"error": "Project is not registered"}
        project = next(
            proj for proj in self.projects
            if os.path.normcase(os.path.abspath(proj["path"]))
            == os.path.normcase(registered_path)
        )
        return self._collect_projects([project])[0]

    def _collect_projects(self, projects):
        if not projects:
            return []
        result = []
        md5_cache = {}
        global_skills = self._collect_skills(include_global_state=False)
        dir_skills = [skill for skill in global_skills if skill.get("is_dir", False)]
        file_skills = [skill for skill in global_skills if not skill.get("is_dir", False)]
        bundle_collections = {
            collection.get("bundle_parent"): collection
            for collection in self._load_skill_collections().get("collections", [])
            if collection.get("kind") == "bundle"
            and collection.get("bundle_parent")
        }
        for proj in projects:
            path = proj["path"]
            state_paths = self._sync_state_paths(path)
            sync_manifest = self._load_sync_manifest(path)
            preserved_files = sync_manifest.get("preserved_files", {})
            if not isinstance(preserved_files, dict):
                preserved_files = {}
            managed_skills = sorted({
                metadata.get("owner", "")
                for metadata in sync_manifest.get("files", {}).values()
                if metadata.get("owner")
                and metadata.get("owner") != "__agents_index__"
            })
            detached_skills = sorted({
                metadata.get("owner", "")
                for metadata in preserved_files.values()
                if metadata.get("owner")
                and metadata.get("owner") != "__agents_index__"
            })
            entry = {
                "name": proj["name"],
                "path": path,
                "skills_status": {},
                "project_skills": [],
                "can_undo_sync": os.path.isfile(state_paths["last_transaction"]),
                "managed_skills": managed_skills,
                "detached_skills": detached_skills,
                "enabled_skills": (
                    sync_manifest.get("enabled_skills", [])
                    if sync_manifest
                    else None
                ),
            }
            project_enabled = set(entry["enabled_skills"] or [])
            if not os.path.isdir(path):
                entry["error"] = "路径不存在" if self.language == "zh" else "Path does not exist"
                result.append(entry)
                continue

            entry["project_rules"] = self._project_rules_metadata(path)

            bundled_files = {}
            bundled_refs = set()

            # First, check folder skills and remember the files they provide.
            for skill in dir_skills:
                fname = skill["filename"]
                global_fp = os.path.join(self.skills_dir, fname)
                is_standard = skill.get("folder_kind") == "standard"
                ignored_relative_paths = set()
                bundle_collection = bundle_collections.get(fname, {})
                if entry["enabled_skills"] is not None:
                    ignored_relative_paths = {
                        relative
                        for virtual_id, relative in bundle_collection.get(
                            "member_sources",
                            {},
                        ).items()
                        if virtual_id not in project_enabled
                    }
                status = check_dir_sync_status(
                    global_fp,
                    path,
                    self.skills_dir,
                    md5_cache,
                    standard_skill=is_standard,
                    ignored_relative_paths=ignored_relative_paths,
                )
                if bundle_collection and not is_standard:
                    readme_path = os.path.join(global_fp, "README.md")
                    parent_target = os.path.join(
                        path,
                        ".agent",
                        "skills",
                        f"{fname}.md",
                    )
                    parent_exists = os.path.isfile(parent_target)
                    parent_matches = (
                        parent_exists
                        and os.path.isfile(readme_path)
                        and get_file_md5(
                            readme_path,
                            md5_cache,
                        ) == get_file_md5(parent_target, md5_cache)
                    )
                    if status == "synced" and not parent_matches:
                        status = "out_of_sync"
                    elif status == "unloaded" and parent_matches:
                        status = "synced"
                    elif status == "unloaded" and parent_exists:
                        status = "out_of_sync"
                entry["skills_status"][fname] = status

                if status != "unloaded" and not is_standard:
                    bundled_refs.add((fname + ".md").casefold())
                    sub_skills_dir = os.path.join(global_fp, ".agent", "skills")
                    if os.path.isdir(sub_skills_dir):
                        for item in os.listdir(sub_skills_dir):
                            if item.lower().endswith(".md"):
                                bundled_files[item.casefold()] = os.path.join(
                                    sub_skills_dir,
                                    item,
                                )

            # Then check file skills. If a file is supplied by a loaded folder skill,
            # do not treat that bundled copy as the standalone global skill being enabled.
            for skill in file_skills:
                fname = skill["filename"]
                if skill.get("is_virtual"):
                    global_fp = safe_real_child_path(
                        os.path.join(
                            self.skills_dir,
                            skill.get("virtual_parent", ""),
                        ),
                        skill.get("virtual_source", ""),
                    )
                    target_name = skill.get("target_filename", "")
                else:
                    global_fp = os.path.join(self.skills_dir, fname)
                    target_name = fname
                target_fp = os.path.join(path, ".agent", "skills", target_name)
                if os.path.exists(global_fp):
                    if os.path.exists(target_fp):
                        if get_file_md5(global_fp, md5_cache) == get_file_md5(target_fp, md5_cache):
                            entry["skills_status"][fname] = "synced"
                        elif fname.casefold() in bundled_files and get_file_md5(bundled_files[fname.casefold()], md5_cache) == get_file_md5(target_fp, md5_cache):
                            entry["skills_status"][fname] = "unloaded"
                        else:
                            entry["skills_status"][fname] = "out_of_sync"
                    else:
                        entry["skills_status"][fname] = "unloaded"
                else:
                    if os.path.exists(target_fp):
                        entry["skills_status"][fname] = "orphan"

            # Finally, expose project-only skills as read-only supplemental data.
            # They remain outside the global library, enabled-skill state, and sync plan.
            skills_dir = os.path.join(path, ".agent", "skills")
            if os.path.exists(skills_dir):
                managed_names = {
                    name.casefold()
                    for name in entry["skills_status"]
                }
                for item in os.listdir(skills_dir):
                    if item.lower().endswith(".md"):
                        if (
                            item.casefold() not in managed_names
                            and item.casefold() not in bundled_files
                            and item.casefold() not in bundled_refs
                        ):
                            entry["skills_status"][item] = "orphan"
                            source = safe_real_child_path(skills_dir, item)
                            if source and os.path.isfile(source):
                                metadata = parse_markdown_metadata(source)
                                metadata.update({
                                    "filename": f"@project:{item}",
                                    "display_filename": item,
                                    "project_relative_path": item,
                                    "is_dir": False,
                                    "project_only": True,
                                })
                                entry["project_skills"].append(metadata)
                        continue

                    skill_relative = normalize_relative_path(
                        os.path.join(item, "SKILL.md")
                    )
                    source = safe_real_child_path(skills_dir, skill_relative)
                    if (
                        item.casefold() not in managed_names
                        and source
                        and os.path.isfile(source)
                    ):
                        metadata = parse_markdown_metadata(source)
                        metadata.update({
                            "filename": f"@project:{skill_relative}",
                            "display_filename": item,
                            "project_relative_path": skill_relative,
                            "is_dir": True,
                            "folder_kind": "standard",
                            "project_only": True,
                        })
                        entry["project_skills"].append(metadata)

            result.append(entry)
        return result

    def _project_rules_metadata(self, project_path):
        target = safe_real_child_path(project_path, "AGENTS.md")
        return {
            "filename": "@project-rules:AGENTS.md",
            "title": "AGENTS.md", "display_filename": "AGENTS.md",
            "description": "当前项目的固定开发规约" if self.language == "zh" else "Fixed development rules for this project",
            "category": "Project rules", "tags": [], "emoji": "📌",
            "project_only": True, "project_rules": True, "is_dir": False,
            "project_path": project_path,
            "available": bool(target and os.path.isfile(target)),
        }

    def get_project_rules_content(self, project_path):
        """Read only the registered project's root AGENTS.md, never library data."""
        registered = self._registered_project_path(project_path)
        if not registered or not os.path.isdir(registered):
            return {"error": "Project is not registered or does not exist"}
        target = safe_real_child_path(registered, "AGENTS.md")
        if not target:
            return {"error": "AGENTS.md points outside this project"}
        if not os.path.exists(target):
            return {"missing": True, "content": "# AGENTS.md\n\n" + (
                "本项目尚未创建 `AGENTS.md`。可以在项目根目录维护固定开发规约。"
                if self.language == "zh" else "This project has no `AGENTS.md` yet. Maintain its fixed development rules in the project root."
            )}
        if not os.path.isfile(target):
            return {"error": "AGENTS.md is not a file"}
        try:
            with open(target, "r", encoding="utf-8-sig") as handle:
                return {"content": handle.read(), "missing": False}
        except (OSError, UnicodeError) as error:
            return {"error": str(error)}

    def add_project_via_dialog(self):
        """Open native folder picker and add as project."""
        # Determine starting folder
        start_dir = self.default_scan_dir if os.path.isdir(self.default_scan_dir) else "C:\\"
        if self.projects:
            last_path = self.projects[-1]["path"]
            parent = os.path.dirname(last_path)
            if os.path.isdir(parent):
                start_dir = parent

        try:
            result = self._window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=start_dir
            )
        except Exception:
            result = None
        if not result or len(result) == 0:
            return None
        path = os.path.normpath(result[0])
        name = os.path.basename(path) or ("未命名项目" if self.language == "zh" else "Unnamed Project")

        if any(p["path"].lower() == path.lower() for p in self.projects):
            return {"error": "该项目已关联"}
        saved = self._commit_config({"projects": [*self.projects, {"name": name, "path": path}]})
        if saved.get("error"):
            return saved
        return {"name": name, "path": path}

    def delete_project(self, path):
        """Remove project association (does NOT delete any files)."""
        return self._commit_config({"projects": [p for p in self.projects if p["path"].lower() != path.lower()]})

    def _registered_project_path(self, project_path: str) -> str:
        requested = os.path.normcase(os.path.abspath(project_path or ""))
        for project in self.projects:
            registered = os.path.abspath(project.get("path", ""))
            if os.path.normcase(registered) == requested:
                return registered
        return ""

    def _sync_state_paths(self, project_path: str) -> dict:
        state_dir = safe_real_child_path(project_path, SYNC_STATE_DIR)
        if not state_dir:
            return {
                "state_dir": "",
                "manifest": "",
                "last_transaction": "",
                "backups": "",
            }
        return {
            "state_dir": state_dir,
            "manifest": os.path.join(state_dir, SYNC_MANIFEST_NAME),
            "last_transaction": os.path.join(state_dir, SYNC_LAST_TRANSACTION_NAME),
            "backups": os.path.join(state_dir, "backups"),
        }

    def _load_sync_manifest(self, project_path: str) -> dict:
        path = self._sync_state_paths(project_path)["manifest"]
        manifest = load_json_file(path, {})
        if not isinstance(manifest, dict) or not isinstance(manifest.get("files", {}), dict):
            return {}
        return manifest

    def _skill_metadata_for_index(self, metadata: dict) -> dict:
        """Preserve source metadata; locale only changes the surrounding index UI."""
        return dict(metadata)

    def _project_global_scope_conflicts(self, enabled_skills: list) -> list:
        """Describe Skills that would be discoverable in both project and user scopes.

        Agent runtimes do not consistently merge same-name Skills across scopes.
        Keep both scopes independent, but make the ambiguity an explicit sync
        conflict instead of silently creating duplicate candidates.
        """
        conflicts = []
        for filename in enabled_skills or []:
            state = self._codex_global_skill_state(filename)
            active_targets = [
                {
                    "id": target["id"],
                    "label": target["label"],
                }
                for target in state.get("global_target_states", [])
                if target.get("enabled") and target.get("kind") == "link"
            ]
            if not active_targets:
                continue
            conflicts.append({
                "filename": filename,
                "global_targets": active_targets,
                "reason": (
                    "The same Skill is enabled in both project and user scopes; "
                    "same-name Skills may be discovered more than once and are not merged"
                ),
            })
        return conflicts
