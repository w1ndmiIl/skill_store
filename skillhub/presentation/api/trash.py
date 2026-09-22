"""Persistent recovery list and token-bound removal of deleted skills."""
import hashlib
import json
import os
import re
import shutil
from skillhub.domain.global_targets import SKILL_LIBRARY_STATE_DIR
from skillhub.infrastructure.filesystem import safe_real_child_path, load_json_file, is_path_reparse_point
from skillhub.infrastructure.json_store import file_lock

class TrashApiMixin:
    def list_deleted_skills(self):
        root = safe_real_child_path(self.skills_dir, os.path.join(SKILL_LIBRARY_STATE_DIR, "trash"))
        result = []
        if not root or not os.path.isdir(root):
            return result
        for token in os.listdir(root):
            if not re.fullmatch(r"[0-9a-f]{32}", token):
                continue
            path = safe_real_child_path(root, token)
            if not path or is_path_reparse_point(path):
                continue
            meta = load_json_file(os.path.join(path, "metadata.json"), {})
            filename = meta.get("filename", "") if isinstance(meta, dict) else ""
            if filename:
                target = safe_real_child_path(self.skills_dir, filename)
                result.append({"token": token, "filename": filename,
                    "deleted_at": meta.get("deleted_at", ""), "source": "SkillHub",
                    "conflict": not target or os.path.exists(target)})
        return sorted(result, key=lambda item: item["deleted_at"], reverse=True)
    def preview_purge_trash(self, tokens):
        items = [i for i in self.list_deleted_skills() if i["token"] in tokens]
        digest = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()
        return {"items": items, "token": digest}
    def purge_trash(self, tokens, preview_token):
        with file_lock(self.skills_dir):
            plan = self.preview_purge_trash(tokens)
            if not preview_token or preview_token != plan["token"]:
                return {"error": "回收站内容已变化，请重新确认 / Trash changed; review again"}
            removed, errors = [], []
            root = safe_real_child_path(self.skills_dir, os.path.join(SKILL_LIBRARY_STATE_DIR, "trash"))
            if not root:
                return {"error": "Unsafe trash root"}
            for item in plan["items"]:
                path = safe_real_child_path(root, item["token"])
                try:
                    if not path or is_path_reparse_point(path):
                        raise OSError("Unsafe trash path")
                    shutil.rmtree(path)
                    removed.append(item["filename"])
                except OSError as error:
                    errors.append({"filename": item["filename"], "error": str(error)})
            return {"ok": not errors, "removed": removed, "errors": errors}
