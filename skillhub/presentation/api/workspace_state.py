"""User workspace state survives random WebView ports and application restarts."""
import difflib
import hashlib
import json
import os
from skillhub.settings import USER_DATA_DIR
from skillhub.infrastructure.filesystem import atomic_write_json, safe_real_child_path
from skillhub.infrastructure.json_store import file_lock, read_json, write_json

def valid_draft(v):
    if not isinstance(v, dict) or not isinstance(v.get("snapshot"), dict):
        return False
    s = v["snapshot"]
    return (all(isinstance(s.get(k, ""), str) for k in ("skillContent", "openaiYaml", "category"))
            and isinstance(s.get("openaiForm", {}), dict)
            and isinstance(v.get("at"), (int, float)))

class WorkspaceStateApiMixin:
    def _draft_path(self, filename):
        identity = os.path.normcase(os.path.realpath(self.skills_dir)) + "|" + str(filename)
        return os.path.join(USER_DATA_DIR, "editor-drafts", hashlib.sha256(identity.encode()).hexdigest() + ".json")
    def save_editor_draft(self, filename, draft):
        if not valid_draft(draft) or len(json.dumps(draft)) > 2_000_000:
            return {"error": "Invalid or oversized draft"}
        try:
            write_json(self._draft_path(filename), draft, valid_draft)
            return {"ok": True}
        except (OSError, ValueError) as error:
            return {"error": str(error)}
    def load_editor_draft(self, filename):
        try:
            return {"draft": read_json(self._draft_path(filename), None, valid_draft)}
        except OSError as error:
            return {"error": str(error)}
    def clear_editor_draft(self, filename):
        path = self._draft_path(filename)
        try:
            with file_lock(path):
                for candidate in (path, path + ".bak"):
                    if os.path.isfile(candidate):
                        os.remove(candidate)
            return {"ok": True}
        except OSError as error:
            return {"error": str(error)}
    def _remember_sync_result(self, project, preview, transaction, backup_root):
        applied = {item["path"]: item for item in transaction["changes"]}
        changes = []
        for item in preview["changes"]:
            row = dict(item)
            change = applied.get(item["path"])
            if change:
                backup = safe_real_child_path(backup_root, change.get("backup", ""))
                target = safe_real_child_path(project, item["path"])
                def text(path):
                    if not path or not os.path.isfile(path):
                        return ""
                    if os.path.getsize(path) > 256_000:
                        return "[Large file: content omitted]"
                    with open(path, "rb") as handle:
                        data = handle.read()
                    return "[Binary file]" if b"\0" in data else data.decode("utf-8", errors="replace")
                row["diff"] = "".join(difflib.unified_diff(text(backup).splitlines(True), text(target).splitlines(True), fromfile="Before", tofile="After"))[:20000]
            changes.append(row)
        atomic_write_json(os.path.join(USER_DATA_DIR, "latest-sync-result.json"), {
            "project": project, "at": transaction["created_at"], "summary": preview["summary"],
            "transaction_id": transaction["id"], "changes": changes,
        })
    def get_last_sync_result(self):
        try:
            return {"report": read_json(os.path.join(USER_DATA_DIR, "latest-sync-result.json"), None, lambda v: isinstance(v, dict) and isinstance(v.get("changes"), list))}
        except OSError as error:
            return {"error": str(error)}
