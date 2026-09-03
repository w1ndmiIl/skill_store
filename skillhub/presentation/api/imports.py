"""Skill import preview, normalization, localization, and apply endpoints."""

import os
import re
import shutil
import time
import uuid

import webview

from skillhub.domain.imports import (
    SKILL_IMPORT_AI_COLLECTION_MAX_ITEMS,
    SKILL_IMPORT_MAX_TOTAL_BYTES,
)
from skillhub.domain.naming import normalize_relative_path
from skillhub.infrastructure.filesystem import (
    atomic_copy_file,
    atomic_write_json,
    get_tree_sha256,
    is_path_reparse_point,
    load_json_file,
    paths_overlap,
    safe_real_child_path,
)

class ImportsApiMixin:
    """Provide hash-bound import previews and transactional apply operations."""

    def preview_skill_import(self, source_path: str, replace_active_name="") -> dict:
        """Stage and analyze locally, then optionally apply configured AI optimization."""
        source_path = os.path.abspath(source_path or "")
        if not os.path.exists(source_path):
            return {"error": "Import source does not exist"}
        if is_path_reparse_point(source_path):
            return {"error": "Import source cannot be a symbolic link or reparse point"}
        paths = self._skill_import_paths()
        if not paths:
            return {"error": "Invalid skill library path"}
        direct_source = ""
        if replace_active_name:
            direct_source = safe_real_child_path(
                self.skills_dir,
                replace_active_name,
            )
        is_direct_adoption = bool(
            direct_source
            and os.path.normcase(os.path.realpath(source_path))
            == os.path.normcase(os.path.realpath(direct_source))
        )
        if paths_overlap(source_path, self.skills_dir) and not is_direct_adoption:
            return {"error": "Import source cannot overlap the skill library"}
        if paths_overlap(source_path, paths["pending"]):
            return {"error": "Import source cannot overlap the staging directory"}
        if os.path.isdir(paths["pending"]):
            cutoff = time.time() - (24 * 60 * 60)
            for item in os.listdir(paths["pending"]):
                stale = safe_real_child_path(paths["pending"], item)
                if (
                    stale
                    and os.path.isdir(stale)
                    and os.path.getmtime(stale) < cutoff
                ):
                    shutil.rmtree(stale, ignore_errors=True)
        token = uuid.uuid4().hex
        pending_root = os.path.join(paths["pending"], token)
        original_root = os.path.join(pending_root, "original")
        adapted_root = os.path.join(pending_root, "adapted")
        os.makedirs(original_root, exist_ok=True)
        os.makedirs(adapted_root, exist_ok=True)

        try:
            source_name = os.path.basename(source_path.rstrip("\\/"))
            staged_original = os.path.join(original_root, source_name)
            if os.path.isdir(source_path):
                self._copy_import_tree(source_path, staged_original)
                candidate = staged_original
            elif source_path.lower().endswith(".zip"):
                if os.path.getsize(source_path) > SKILL_IMPORT_MAX_TOTAL_BYTES:
                    raise ValueError("Skill archive is too large")
                atomic_copy_file(source_path, staged_original)
                extracted_root = os.path.join(pending_root, "extracted")
                self._safe_extract_skill_zip(staged_original, extracted_root)
                visible = [
                    item for item in os.listdir(extracted_root)
                    if item != "__MACOSX"
                ]
                candidate = (
                    os.path.join(extracted_root, visible[0])
                    if len(visible) == 1
                    and os.path.isdir(os.path.join(extracted_root, visible[0]))
                    else extracted_root
                )
            elif source_path.lower().endswith(".md"):
                atomic_copy_file(source_path, staged_original)
                candidate = staged_original
            else:
                raise ValueError("Only Markdown files, skill folders, and ZIP archives are supported")

            result = self._prepare_import_candidate(
                candidate,
                adapted_root,
                source_name,
                preferred_name=replace_active_name,
                allow_existing=bool(replace_active_name),
            )
            ai_requested = bool(self.ai_import_optimization)
            ai_used = False
            ai_error = ""
            if ai_requested:
                if (
                    result["kind"] == "collection"
                    and len(result["collection_items"])
                    > SKILL_IMPORT_AI_COLLECTION_MAX_ITEMS
                ):
                    ai_error = (
                        "Skipped for a large collection "
                        f"({len(result['collection_items'])} members; "
                        f"limit {SKILL_IMPORT_AI_COLLECTION_MAX_ITEMS})")
                elif result["kind"] == "collection":
                    ai_errors = []
                    for collection_item in result["collection_items"]:
                        collection_item["ai_used"] = False
                        if collection_item.get("duplicate_of"):
                            continue
                        ai_result = self._ai_optimize_import_entry(
                            collection_item["adapted_path"],
                            "standard",
                            collection_item["active_name"],
                        )
                        if ai_result.get("ok"):
                            ai_used = True
                            collection_item["ai_used"] = True
                            collection_item["ai_diff"] = ai_result.get(
                                "diff",
                                "",
                            )
                            collection_item["changes"].append("ai_optimized")
                        else:
                            ai_errors.append(
                                f"{collection_item['source_name']}: "
                                f"{ai_result.get('error', 'AI optimization failed')}"
                            )
                    if ai_used:
                        result["changes"].append("ai_optimized")
                    ai_error = "; ".join(ai_errors)
                else:
                    ai_result = self._ai_optimize_import_entry(
                        result["adapted_path"],
                        result["kind"],
                        result["active_name"],
                    )
                    if ai_result.get("ok"):
                        ai_used = True
                        result["ai_diff"] = ai_result.get("diff", "")
                        result["changes"].append("ai_optimized")
                    else:
                        ai_error = ai_result.get(
                            "error",
                            "AI optimization failed",
                        )

            if result["kind"] == "collection":
                collection_findings = []
                for collection_item in result["collection_items"]:
                    collection_item["findings"] = self._scan_adapted_import(
                        collection_item["adapted_path"]
                    )
                    collection_item["compatibility"] = (
                        self._inspect_import_compatibility(
                            collection_item["adapted_path"],
                            "standard",
                            collection_item["active_name"],
                        )
                    )
                    collection_item["findings"].extend(
                        collection_item["compatibility"].get("findings", [])
                    )
                    collection_item.update(self._classify_collection_candidate(
                        collection_item["adapted_path"],
                        collection_item.get("existing_name", ""),
                    ))
                    for finding in collection_item["findings"]:
                        prefixed = dict(finding)
                        relative = finding.get("path", "")
                        prefixed["path"] = normalize_relative_path(os.path.join(
                            "skills",
                            collection_item["source_name"],
                            relative,
                        ))
                        collection_findings.append(prefixed)
                result["findings"] = collection_findings
                installable_items = [
                    item for item in result["collection_items"]
                    if item.get("action") != "duplicate"
                ]
                result["active_names"] = [
                    item["active_name"] for item in installable_items
                ]
                result["collection_count"] = len(result["collection_items"])
                result["installable_count"] = len(installable_items)
                result["duplicate_count"] = sum(
                    item.get("action") == "duplicate"
                    for item in result["collection_items"]
                )
                result["update_count"] = sum(
                    item.get("action") == "update"
                    for item in result["collection_items"]
                )
                result["conflict_count"] = sum(
                    item.get("action") == "conflict"
                    for item in result["collection_items"]
                )
                result["duplicate_of"] = ""
            else:
                structural_findings = [
                    finding for finding in result["findings"]
                    if finding.get("code", "").startswith("bundle")
                ]
                result["findings"] = self._scan_adapted_import(
                    result["adapted_path"],
                    structural_findings,
                )
                result["compatibility"] = self._inspect_import_compatibility(
                    result["adapted_path"],
                    result["kind"],
                    result["active_name"],
                )
                result["findings"].extend(
                    result["compatibility"].get("findings", [])
                )
                result["duplicate_of"] = self._find_import_duplicate(
                    result["adapted_path"],
                    exclude_name=replace_active_name,
                )

            display_translation_requested = bool(
                getattr(self, "ai_display_translation", False)
            )
            display_translation_used = False
            display_translation_errors = []
            if display_translation_requested:
                if (
                    result["kind"] == "collection"
                    and len(result["collection_items"])
                    > SKILL_IMPORT_AI_COLLECTION_MAX_ITEMS
                ):
                    display_translation_errors.append(
                        "Skipped for a large collection "
                        f"({len(result['collection_items'])} members; "
                        f"limit {SKILL_IMPORT_AI_COLLECTION_MAX_ITEMS})")
                elif result["kind"] == "collection":
                    for collection_item in result["collection_items"]:
                        if collection_item.get("action") == "duplicate":
                            continue
                        translation = self._translate_import_display_metadata(
                            collection_item["adapted_path"],
                            "standard",
                        )
                        if translation.get("ok"):
                            display_translation_used = True
                            collection_item["display_localization"] = (
                                translation["localization"]
                            )
                            collection_item["display_title"] = translation[
                                "display_title"
                            ]
                            collection_item["display_description"] = translation[
                                "display_description"
                            ]
                            collection_item["display_language"] = translation[
                                "target_language"
                            ]
                        else:
                            display_translation_errors.append(
                                f"{collection_item['source_name']}: "
                                f"{translation.get('error', 'Display translation failed')}"
                            )
                else:
                    translation = self._translate_import_display_metadata(
                        result["adapted_path"],
                        result["kind"],
                    )
                    if translation.get("ok"):
                        display_translation_used = True
                        result["display_localization"] = translation["localization"]
                        result["display_title"] = translation["display_title"]
                        result["display_description"] = translation[
                            "display_description"
                        ]
                        result["display_language"] = translation["target_language"]
                    else:
                        display_translation_errors.append(
                            translation.get(
                                "error",
                                "Display translation failed",
                            )
                        )
            display_translation_error = "; ".join(display_translation_errors)
            if ai_requested and ai_error:
                result["findings"].append({
                    "severity": "warning",
                    "code": "ai_optimization_fallback",
                    "path": "",
                    "message_en": (
                        f"AI optimization was skipped or failed; local validation remains active. {ai_error}"
                    ),
                    "message_zh": (
                        f"AI 优化未执行或失败，已保留本地规则体检结果。{ai_error}"
                    ),
                })
            if display_translation_requested and display_translation_error:
                result["findings"].append({
                    "severity": "warning",
                    "code": "display_translation_fallback",
                    "path": "",
                    "message_en": (
                        "Bilingual display metadata was not generated; "
                        f"the original title and description remain visible. "
                        f"{display_translation_error}"
                    ),
                    "message_zh": (
                        "未生成双语界面说明，界面将继续显示原始标题和说明。"
                        f"{display_translation_error}"
                    ),
                })
            relative_adapted = normalize_relative_path(
                os.path.relpath(result["adapted_path"], pending_root)
            )
            manifest = {
                "token": token,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "source_name": source_name,
                "source_hash": get_tree_sha256(staged_original),
                "active_name": result["active_name"],
                "kind": result["kind"],
                "adapted_relative": relative_adapted,
                "changes": result["changes"],
                "findings": result["findings"],
                "compatibility": result.get("compatibility", {}),
                "duplicate_of": result["duplicate_of"],
                "ai_required": False,
                "ai_requested": ai_requested,
                "ai_used": ai_used,
                "ai_diff": result.get("ai_diff", ""),
                "ai_error": ai_error,
                "display_translation_requested": display_translation_requested,
                "display_translation_used": display_translation_used,
                "display_translation_error": display_translation_error,
                "display_localization": result.get("display_localization", {}),
                "display_title": result.get("display_title", ""),
                "display_description": result.get("display_description", ""),
                "display_language": result.get("display_language", ""),
                "replace_existing": replace_active_name,
                "has_high_risk": any(
                    finding.get("severity") == "high"
                    for finding in result["findings"]
                ),
                "existing_hash": (
                    get_tree_sha256(source_path)
                    if replace_active_name
                    else ""
                ),
            }
            if result["kind"] == "collection":
                manifest.update({
                    "collection_count": result["collection_count"],
                    "installable_count": result["installable_count"],
                    "duplicate_count": result["duplicate_count"],
                    "update_count": result["update_count"],
                    "conflict_count": result["conflict_count"],
                    "active_names": result["active_names"],
                    "collection_items": [
                        {
                            "source_name": item["source_name"],
                            "active_name": item["active_name"],
                            "adapted_relative": normalize_relative_path(
                                os.path.relpath(
                                    item["adapted_path"],
                                    pending_root,
                                )
                            ),
                            "changes": item["changes"],
                            "findings": item["findings"],
                            "compatibility": item.get("compatibility", {}),
                            "action": item["action"],
                            "existing_hash": item["existing_hash"],
                            "duplicate_of": item["duplicate_of"],
                            "ai_used": bool(item.get("ai_used")),
                            "ai_diff": item.get("ai_diff", ""),
                            "display_localization": item.get(
                                "display_localization",
                                {},
                            ),
                            "display_title": item.get("display_title", ""),
                            "display_description": item.get(
                                "display_description",
                                "",
                            ),
                            "display_language": item.get(
                                "display_language",
                                "",
                            ),
                        }
                        for item in result["collection_items"]
                    ],
                })
            atomic_write_json(os.path.join(pending_root, "manifest.json"), manifest)
            return {
                "ok": True,
                **manifest,
                "can_import": (
                    result["installable_count"] > 0
                    if result["kind"] == "collection"
                    else not bool(result["duplicate_of"])
                ),
            }
        except Exception as error:
            shutil.rmtree(pending_root, ignore_errors=True)
            return {"error": str(error)}

    def preview_unregistered_skill(self, filename: str) -> dict:
        """Preview in-place adoption of a skill copied directly into skills_dir."""
        if not filename or filename.startswith("."):
            return {"error": "Invalid skill filename"}
        source = safe_real_child_path(self.skills_dir, filename)
        if not source or not os.path.exists(source):
            return {"error": "Skill does not exist"}
        scan = self.scan_unregistered_skills()
        unknown_names = {
            item.get("filename") for item in scan.get("skills", [])
        }
        if filename not in unknown_names:
            return {"error": "Skill is already registered"}
        return self.preview_skill_import(
            source,
            replace_active_name=filename,
        )

    def preview_skill_import_via_dialog(self, import_kind="file"):
        """Select and preview a Markdown/ZIP file or a skill folder."""
        if not self._window:
            return {"error": "Window is not ready"}
        try:
            if import_kind == "folder":
                selected = self._window.create_file_dialog(
                    webview.FOLDER_DIALOG,
                    directory=self.default_scan_dir if os.path.isdir(self.default_scan_dir) else None,
                )
            else:
                selected = self._window.create_file_dialog(
                    webview.OPEN_DIALOG,
                    allow_multiple=False,
                    file_types=(
                        "Skill files (*.md;*.zip)",
                        "Markdown files (*.md)",
                        "ZIP archives (*.zip)",
                    ),
                )
        except Exception as error:
            return {"error": str(error)}
        if not selected:
            return None
        source = selected[0] if isinstance(selected, (list, tuple)) else selected
        return self.preview_skill_import(source)

    def _apply_skill_collection_import(
        self,
        pending_root: str,
        manifest: dict,
        paths: dict,
    ) -> dict:
        installable = [
            item for item in manifest.get("collection_items", [])
            if item.get("action") != "duplicate"
        ]
        if not installable:
            return {"error": "Every skill in this collection is already installed"}

        prepared = []
        for item in installable:
            adapted = safe_real_child_path(
                pending_root,
                item.get("adapted_relative", ""),
            )
            destination = safe_real_child_path(
                self.skills_dir,
                item.get("active_name", ""),
            )
            if (
                not adapted
                or not destination
                or not os.path.isdir(adapted)
            ):
                return {"error": "Collection staging data is invalid"}
            action = item.get("action", "install")
            exists = os.path.exists(destination)
            if action == "install" and exists:
                return {
                    "requires_repreview": True,
                    "error": "Skill library changed after preview",
                }
            if action in ("update", "conflict") and (
                not exists
                or get_tree_sha256(destination) != item.get("existing_hash", "")
            ):
                return {
                    "requires_repreview": True,
                    "error": "Existing collection skill changed after preview",
                }
            prepared.append((item, adapted, destination, action))

        original = os.path.join(pending_root, "original")
        upstream = os.path.join(paths["upstream"], manifest["token"])
        applied = []
        try:
            os.makedirs(paths["upstream"], exist_ok=True)
            if not os.path.exists(upstream):
                shutil.copytree(original, upstream)

            for item, adapted, destination, action in prepared:
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                backup = ""
                if action in ("update", "conflict"):
                    backup = f"{destination}.import-backup-{manifest['token']}"
                    os.replace(destination, backup)
                    applied.append((destination, backup))
                    archived = os.path.join(
                        upstream,
                        "_replaced",
                        item["active_name"],
                    )
                    os.makedirs(os.path.dirname(archived), exist_ok=True)
                    shutil.copytree(backup, archived)
                else:
                    applied.append((destination, backup))
                shutil.copytree(adapted, destination)

            filenames = [
                item["active_name"]
                for item, _adapted, _destination, _action in prepared
            ]
            skipped_duplicates = list(dict.fromkeys(
                item["duplicate_of"]
                for item in manifest.get("collection_items", [])
                if item.get("duplicate_of")
            ))
            self._persist_display_localizations({
                item["active_name"]: item.get("display_localization", {})
                for item in installable
                if item.get("display_localization")
            })
            catalog = load_json_file(
                paths["catalog"],
                {"version": 1, "imports": []},
            )
            if not isinstance(catalog, dict):
                catalog = {"version": 1, "imports": []}
            catalog.setdefault("imports", []).append({
                "token": manifest["token"],
                "imported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "source_name": manifest.get("source_name", ""),
                "source_hash": manifest.get("source_hash", ""),
                "active_name": manifest.get("active_name", ""),
                "active_names": filenames,
                "kind": "collection",
                "changes": manifest.get("changes", []),
                "findings": manifest.get("findings", []),
                "ai_requested": bool(manifest.get("ai_requested")),
                "ai_used": bool(manifest.get("ai_used")),
                "ai_error": manifest.get("ai_error", ""),
                "display_translation_requested": bool(
                    manifest.get("display_translation_requested")
                ),
                "display_translation_used": bool(
                    manifest.get("display_translation_used")
                ),
                "display_translation_error": manifest.get(
                    "display_translation_error",
                    "",
                ),
                "skipped_duplicates": skipped_duplicates,
                "updated": [
                    item["active_name"]
                    for item in installable
                    if item.get("action") in ("update", "conflict")
                ],
            })
            atomic_write_json(paths["catalog"], catalog)
            for filename in filenames:
                self._register_library_entry(
                    filename,
                    source="collection-import",
                )
            collection = self._upsert_skill_collection(
                manifest.get("source_name", ""),
                [*filenames, *skipped_duplicates],
            )
            for _destination, backup in applied:
                if backup and os.path.isdir(backup):
                    shutil.rmtree(backup, ignore_errors=True)
            shutil.rmtree(pending_root, ignore_errors=True)
            return {
                "ok": True,
                "filename": filenames[0],
                "filenames": filenames,
                "kind": "collection",
                "findings": manifest.get("findings", []),
                "ai_used": bool(manifest.get("ai_used")),
                "skipped_duplicates": skipped_duplicates,
                "collection_id": collection["id"],
                "replaced_existing": False,
            }
        except Exception as error:
            for destination, backup in reversed(applied):
                if os.path.isdir(destination):
                    shutil.rmtree(destination, ignore_errors=True)
                if backup and os.path.isdir(backup):
                    os.replace(backup, destination)
            return {"error": str(error)}

    def apply_skill_import(
        self,
        token: str,
        accept_ai_changes: bool = False,
        accept_high_risk: bool = False,
        accept_collection_conflicts: bool = False,
    ) -> dict:
        """Apply a previously previewed local import and preserve its upstream source."""
        if not re.fullmatch(r"[a-f0-9]{32}", token or ""):
            return {"error": "Invalid import token"}
        paths = self._skill_import_paths()
        pending_root = safe_real_child_path(paths.get("pending", ""), token)
        if not pending_root or not os.path.isdir(pending_root):
            return {"error": "Import preview expired or does not exist"}
        manifest_path = os.path.join(pending_root, "manifest.json")
        manifest = load_json_file(manifest_path, {})
        if manifest.get("token") != token:
            return {"error": "Invalid import manifest"}
        if manifest.get("has_high_risk") and not accept_high_risk:
            return {
                "requires_high_risk_confirmation": True,
                "high_risk_findings": [
                    finding
                    for finding in manifest.get("findings", [])
                    if finding.get("severity") == "high"
                ],
            }
        if manifest.get("ai_used") and not accept_ai_changes:
            return {
                "requires_ai_confirmation": True,
                "ai_diff": manifest.get("ai_diff", ""),
                "collection_diffs": [
                    {
                        "source_name": item.get("source_name", ""),
                        "ai_diff": item.get("ai_diff", ""),
                    }
                    for item in manifest.get("collection_items", [])
                    if item.get("ai_used")
                ],
            }
        if (
            manifest.get("kind") == "collection"
            and manifest.get("conflict_count", 0)
            and not accept_collection_conflicts
        ):
            return {
                "requires_collection_confirmation": True,
                "conflicts": [
                    {
                        "source_name": item.get("source_name", ""),
                        "active_name": item.get("active_name", ""),
                    }
                    for item in manifest.get("collection_items", [])
                    if item.get("action") == "conflict"
                ],
            }
        if manifest.get("kind") == "collection":
            return self._apply_skill_collection_import(
                pending_root,
                manifest,
                paths,
            )
        if manifest.get("duplicate_of"):
            return {"error": f"Duplicate of {manifest['duplicate_of']}"}

        adapted = safe_real_child_path(
            pending_root, manifest.get("adapted_relative", "")
        )
        destination = safe_real_child_path(
            self.skills_dir, manifest.get("active_name", "")
        )
        original = os.path.join(pending_root, "original")
        upstream = os.path.join(paths["upstream"], token)
        if not adapted or not destination or not os.path.exists(adapted):
            return {"error": "Import staging data is invalid"}
        replace_existing = manifest.get("replace_existing", "")
        if replace_existing:
            if (
                not os.path.exists(destination)
                or get_tree_sha256(destination) != manifest.get("existing_hash", "")
            ):
                return {
                    "requires_repreview": True,
                    "error": "Directly copied skill changed after preview",
                }
        elif os.path.exists(destination):
            return {
                "requires_repreview": True,
                "error": "Skill library changed after preview",
            }

        backup_destination = ""
        try:
            os.makedirs(paths["upstream"], exist_ok=True)
            if not os.path.exists(upstream):
                shutil.copytree(original, upstream)

            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if os.path.isdir(adapted):
                if replace_existing:
                    backup_destination = (
                        f"{destination}.import-backup-{token}"
                    )
                    os.replace(destination, backup_destination)
                shutil.copytree(adapted, destination)
            else:
                atomic_copy_file(adapted, destination)

            display_localization = manifest.get("display_localization", {})
            if display_localization:
                self._persist_display_localizations({
                    manifest.get("active_name", ""): display_localization,
                })
            catalog = load_json_file(paths["catalog"], {"version": 1, "imports": []})
            if not isinstance(catalog, dict):
                catalog = {"version": 1, "imports": []}
            imports = catalog.setdefault("imports", [])
            imports.append({
                "token": token,
                "imported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "source_name": manifest.get("source_name", ""),
                "source_hash": manifest.get("source_hash", ""),
                "active_name": manifest.get("active_name", ""),
                "kind": manifest.get("kind", ""),
                "changes": manifest.get("changes", []),
                "findings": manifest.get("findings", []),
                "ai_requested": bool(manifest.get("ai_requested")),
                "ai_used": bool(manifest.get("ai_used")),
                "ai_error": manifest.get("ai_error", ""),
                "display_translation_requested": bool(
                    manifest.get("display_translation_requested")
                ),
                "display_translation_used": bool(
                    manifest.get("display_translation_used")
                ),
                "display_translation_error": manifest.get(
                    "display_translation_error",
                    "",
                ),
            })
            atomic_write_json(paths["catalog"], catalog)
            self._register_library_entry(
                manifest.get("active_name", ""),
                source="direct-optimized" if replace_existing else "imported",
            )
            if backup_destination and os.path.isdir(backup_destination):
                shutil.rmtree(backup_destination, ignore_errors=True)
            shutil.rmtree(pending_root, ignore_errors=True)
            return {
                "ok": True,
                "filename": manifest.get("active_name"),
                "kind": manifest.get("kind"),
                "findings": manifest.get("findings", []),
                "ai_used": bool(manifest.get("ai_used")),
                "replaced_existing": bool(replace_existing),
            }
        except Exception as error:
            if backup_destination and os.path.isdir(backup_destination):
                if os.path.isdir(destination):
                    shutil.rmtree(destination, ignore_errors=True)
                os.replace(backup_destination, destination)
            elif not replace_existing:
                if os.path.isdir(destination):
                    shutil.rmtree(destination, ignore_errors=True)
                elif os.path.isfile(destination):
                    try:
                        os.remove(destination)
                    except OSError:
                        pass
            return {"error": str(error)}

    def discard_skill_import(self, token: str) -> dict:
        """Discard a staged preview without touching the active skill library."""
        if not re.fullmatch(r"[a-f0-9]{32}", token or ""):
            return {"error": "Invalid import token"}
        paths = self._skill_import_paths()
        pending_root = safe_real_child_path(paths.get("pending", ""), token)
        if pending_root and os.path.isdir(pending_root):
            shutil.rmtree(pending_root, ignore_errors=True)
        return {"ok": True}
