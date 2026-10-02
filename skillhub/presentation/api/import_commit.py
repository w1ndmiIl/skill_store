"""Apply reviewed imports as one library asset and metadata transaction."""
import os
import re
import shutil
import time
from skillhub.infrastructure.filesystem import (
    atomic_copy_file, atomic_write_json, get_tree_sha256,
    is_path_reparse_point, load_json_file, safe_real_child_path,
)
from skillhub.infrastructure.json_store import file_lock
from skillhub.infrastructure.transactions import restore_files, persist_snapshot


def remove_asset(path):
    if os.path.isdir(path) and not is_path_reparse_point(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.unlink(path)


class ImportCommitApiMixin:
    def discard_skill_import(self, token):
        if not re.fullmatch(r"[a-f0-9]{32}", token or ""):
            return {"error": "Invalid import token"}
        with file_lock(self.skills_dir):
            path = safe_real_child_path(self._skill_import_paths().get("pending", ""), token)
            if path and os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
        return {"ok": True}

    def apply_skill_import(self, token, accept_ai_changes=False,
                           accept_high_risk=False, accept_collection_conflicts=False):
        with file_lock(self.skills_dir):
            try:
                return self._apply_reviewed_import(token, accept_ai_changes,
                                                   accept_high_risk, accept_collection_conflicts)
            except (OSError, ValueError) as error:
                return {"error": str(error)}

    def _apply_reviewed_import(self, token, accept_ai_changes, accept_high_risk, accept_collection_conflicts):
        if not re.fullmatch(r"[a-f0-9]{32}", token or ""):
            return {"error": "Invalid import token"}
        paths = self._skill_import_paths()
        pending = safe_real_child_path(paths.get("pending", ""), token)
        if not pending or not os.path.isdir(pending):
            return {"error": "Import preview expired or does not exist"}
        manifest = load_json_file(os.path.join(pending, "manifest.json"), {})
        if not isinstance(manifest, dict) or manifest.get("token") != token:
            return {"error": "Invalid import manifest"}
        recovery = os.path.join(pending, "rollback-metadata")
        if os.path.isfile(os.path.join(recovery, "recovery.json")):
            return {"error": "An earlier failed import needs recovery", "recovery_path": recovery}
        staged = safe_real_child_path(pending, manifest.get("adapted_relative", ""))
        if not staged or not os.path.exists(staged) or is_path_reparse_point(staged):
            return {"error": "Import staging data is invalid"}
        if os.path.isdir(staged):
            self._validate_import_tree(staged)
        if not manifest.get("adapted_hash") or get_tree_sha256(staged) != manifest["adapted_hash"]:
            return {"requires_repreview": True, "error": "Import content changed after preview; review again"}
        if manifest.get("has_high_risk") and not accept_high_risk:
            return {"requires_high_risk_confirmation": True,
                    "high_risk_findings": [f for f in manifest.get("findings", []) if f.get("severity") == "high"]}
        if manifest.get("ai_used") and not accept_ai_changes:
            return {"requires_ai_confirmation": True, "ai_diff": manifest.get("ai_diff", ""),
                    "collection_diffs": [{"source_name": i.get("source_name", ""), "ai_diff": i.get("ai_diff", "")}
                                         for i in manifest.get("collection_items", []) if i.get("ai_used")]}
        if manifest.get("conflict_count") and not accept_collection_conflicts:
            return {"requires_collection_confirmation": True,
                    "conflicts": [{"source_name": i.get("source_name", ""), "active_name": i.get("active_name", "")}
                                  for i in manifest.get("collection_items", []) if i.get("action") == "conflict"]}
        collection = manifest.get("kind") == "collection"
        if not collection and manifest.get("duplicate_of"):
            return {"error": f"Duplicate of {manifest['duplicate_of']}"}
        items = manifest.get("collection_items", []) if collection else [{
            **manifest, "action": "update" if manifest.get("replace_existing") else "install",
        }]
        prepared, duplicates = [], []
        for item in items:
            if item.get("action") == "duplicate":
                duplicate = safe_real_child_path(self.skills_dir, item.get("duplicate_of", ""))
                if not duplicate or not os.path.exists(duplicate):
                    return {"requires_repreview": True, "error": "Duplicate Skill changed after preview"}
                duplicates.append(item["duplicate_of"])
                continue
            adapted = safe_real_child_path(pending, item.get("adapted_relative", ""))
            target = safe_real_child_path(self.skills_dir, item.get("active_name", ""))
            if not adapted or not target or not os.path.exists(adapted):
                return {"error": "Import staging data is invalid"}
            exists = os.path.exists(target)
            replacing = item.get("action") in ("update", "conflict")
            if (replacing and (not exists or get_tree_sha256(target) != item.get("existing_hash"))) or (not replacing and exists):
                return {"requires_repreview": True, "error": "Skill library changed after preview"}
            prepared.append((item, adapted, target, replacing))
        if not prepared:
            return {"error": "Every skill in this collection is already installed"}
        return self._commit_reviewed_import(pending, manifest, paths, prepared, duplicates)

    def _commit_reviewed_import(self, pending, manifest, paths, prepared, duplicates):
        snapshot = self._library_metadata_snapshot()
        upstream = os.path.join(paths["upstream"], manifest["token"])
        applied = []
        try:
            persist_snapshot(snapshot, os.path.join(pending, "rollback-metadata"))
            os.makedirs(paths["upstream"], exist_ok=True)
            if not os.path.exists(upstream):
                shutil.copytree(os.path.join(pending, "original"), upstream)
            for item, adapted, target, replacing in prepared:
                backup = f"{target}.import-backup-{manifest['token']}" if replacing else ""
                if backup and os.path.lexists(backup):
                    raise OSError("An earlier import backup needs recovery before retrying")
                if replacing:
                    os.replace(target, backup)
                applied.append((target, backup))
                if backup:
                    archived = os.path.join(upstream, "_replaced", item["active_name"])
                    if not os.path.exists(archived):
                        if os.path.isdir(backup):
                            shutil.copytree(backup, archived)
                        else:
                            atomic_copy_file(backup, archived)
                if os.path.isdir(adapted):
                    shutil.copytree(adapted, target)
                else:
                    atomic_copy_file(adapted, target)
            names = [item["active_name"] for item, *_ in prepared]
            self._persist_display_localizations({i["active_name"]: i["display_localization"]
                                               for i, *_ in prepared if i.get("display_localization")})
            catalog = load_json_file(paths["catalog"], {"version": 1, "imports": []})
            if not isinstance(catalog, dict) or not isinstance(catalog.get("imports"), list):
                raise ValueError("Import catalog is invalid; original data preserved")
            catalog["imports"].append({
                **{k: manifest.get(k) for k in (
                    "token", "source_name", "source_hash", "active_name", "kind", "changes", "findings",
                    "ai_requested", "ai_used", "ai_error", "display_translation_requested",
                    "display_translation_used", "display_translation_error")},
                "imported_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "active_names": names, "skipped_duplicates": duplicates,
                "updated": [i["active_name"] for i, *_ in prepared if i.get("action") in ("update", "conflict")],
            })
            atomic_write_json(paths["catalog"], catalog)
            for name in names:
                self._register_library_entry(name, source="collection-import" if manifest["kind"] == "collection"
                                             else "direct-optimized" if manifest.get("replace_existing") else "imported")
            collection = self._upsert_skill_collection(manifest.get("source_name", ""), [*names, *duplicates]) if manifest["kind"] == "collection" else None
        except Exception as error:
            rollback_errors = []
            for target, backup in reversed(applied):
                try:
                    if os.path.lexists(target):
                        remove_asset(target)
                    if backup and os.path.exists(backup):
                        os.replace(backup, target)
                except OSError as rollback_error:
                    rollback_errors.append(str(rollback_error))
            rollback_errors.extend(restore_files(snapshot))
            if not rollback_errors:
                shutil.rmtree(os.path.join(pending, "rollback-metadata"), ignore_errors=True)
            return {"error": str(error), "rolled_back": not rollback_errors,
                    "rollback_errors": rollback_errors, "recovery_path": pending if rollback_errors else ""}
        for _target, backup in applied:
            if backup and os.path.exists(backup):
                try:
                    remove_asset(backup)
                except OSError:
                    pass  # The upstream archive already preserves the replaced asset.
        shutil.rmtree(pending, ignore_errors=True)
        return {"ok": True, "filename": names[0], "filenames": names, "kind": manifest["kind"],
                "findings": manifest.get("findings", []), "ai_used": bool(manifest.get("ai_used")),
                "skipped_duplicates": duplicates, "collection_id": collection["id"] if collection else "",
                "replaced_existing": bool(manifest.get("replace_existing"))}
