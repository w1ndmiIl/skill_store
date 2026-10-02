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

from .import_commit import ImportCommitApiMixin


class ImportsApiMixin(ImportCommitApiMixin):
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
                    and not os.path.isfile(os.path.join(stale, "rollback-metadata", "recovery.json"))
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
                "adapted_hash": get_tree_sha256(result["adapted_path"]),
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
