"""Approval-bound remote GitHub Skill installation tools."""

import hashlib
import os
import re
import shutil
import time
import uuid
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import requests

from skillhub.domain.frontmatter import split_markdown_frontmatter
from skillhub.domain.global_targets import SKILL_LIBRARY_STATE_DIR
from skillhub.domain.imports import scan_skill_text
from skillhub.infrastructure.filesystem import (
    atomic_copy_file,
    atomic_write_bytes,
    atomic_write_json,
    get_tree_sha256,
    load_json_file,
    safe_real_child_path,
)
from skillhub.settings import AGENT_REMOTE_COLLECTIONS_DIR


REMOTE_COLLECTION_ARCHIVE_MAX_BYTES = 100 * 1024 * 1024
REMOTE_COLLECTION_DOWNLOAD_ATTEMPTS = 3


class AgentRemoteApiMixin:
    """Preview and apply remote Skill packages without trusting mutable state."""

    def _agent_remote_import_root(self):
        return safe_real_child_path(
            self.skills_dir,
            os.path.join(SKILL_LIBRARY_STATE_DIR, "agent-remote-imports"),
        )

    def _agent_remote_collection_root(self):
        configured = getattr(self, "_agent_remote_download_root", "")
        if configured:
            return os.path.abspath(configured)
        return AGENT_REMOTE_COLLECTIONS_DIR

    @staticmethod
    def _validated_agent_github_source(repository, reference=""):
        requested = str(repository or "").strip()
        parsed = urlsplit(requested)
        parts = [part for part in parsed.path.split("/") if part]
        tree_reference = ""
        if (
            parsed.scheme.lower() != "https"
            or parsed.netloc.lower() != "github.com"
            or parsed.query
            or parsed.fragment
            or len(parts) not in (2, 4)
            or (len(parts) == 4 and parts[2].lower() != "tree")
        ):
            raise ValueError(
                "Only public GitHub repository or /tree/<ref> URLs are supported"
            )
        owner = parts[0]
        repository_name = parts[1]
        if repository_name.lower().endswith(".git"):
            repository_name = repository_name[:-4]
        if len(parts) == 4:
            tree_reference = parts[3]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(
            r"[A-Za-z0-9_.-]+",
            repository_name,
        ):
            raise ValueError(
                "Only public GitHub repository or /tree/<ref> URLs are supported"
            )
        supplied_reference = str(reference or "").strip()
        if (
            tree_reference
            and supplied_reference not in ("", "main", tree_reference)
        ):
            raise ValueError("GitHub URL reference conflicts with the ref argument")
        reference = tree_reference or supplied_reference or "main"
        if (
            not re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", reference)
            or ".." in reference
        ):
            raise ValueError("Invalid Git reference")
        repository = f"https://github.com/{owner}/{repository_name}"
        return repository, owner, repository_name, reference

    def _tool_preview_remote_skill_install(self, arguments):
        try:
            repository, owner, repository_name, reference = (
                self._validated_agent_github_source(
                    arguments["repository"],
                    arguments.get("ref", ""),
                )
            )
        except ValueError as error:
            return {"error": str(error)}
        skill_path = PurePosixPath(arguments["skill_path"])
        if (
            skill_path.is_absolute()
            or ".." in skill_path.parts
            or len(skill_path.parts) < 3
            or skill_path.parts[0] != "skills"
            or skill_path.name != "SKILL.md"
        ):
            return {"error": "Skill path must be skills/<name>/SKILL.md"}
        install_name = arguments["install_name"].strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", install_name):
            return {"error": "Invalid install name"}

        source_url = (
            f"https://raw.githubusercontent.com/{owner}/{repository_name}/"
            f"{reference}/{skill_path.as_posix()}"
        )
        try:
            response = requests.get(
                source_url,
                headers={"User-Agent": "SkillHub-SkillOps-Agent/1.0"},
                timeout=30,
            )
        except requests.exceptions.RequestException as error:
            return {
                "ok": False,
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }
        if response.status_code != 200:
            return {"error": f"GitHub raw source returned HTTP {response.status_code}"}
        source_bytes = response.content
        if not source_bytes or len(source_bytes) > 500_000:
            return {"error": "Remote SKILL.md is empty or exceeds 500 KB"}
        try:
            content = source_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return {"error": "Remote SKILL.md is not valid UTF-8"}
        frontmatter, _body = split_markdown_frontmatter(content)
        source_name = str(
            frontmatter.get("name") or frontmatter.get("title") or ""
        ).strip()
        if source_name != install_name:
            return {
                "error": (
                    f"Frontmatter name '{source_name}' does not match "
                    f"requested install name '{install_name}'"
                )
            }

        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        staging_root = self._agent_remote_import_root()
        if not staging_root:
            return {"error": "Unsafe remote import staging directory"}
        token = uuid.uuid4().hex
        preview_root = safe_real_child_path(staging_root, token)
        if not preview_root:
            return {"error": "Unsafe remote import preview path"}
        os.makedirs(preview_root, exist_ok=False)
        atomic_write_bytes(
            os.path.join(preview_root, "SKILL.md"),
            source_bytes,
        )
        target = safe_real_child_path(self.skills_dir, install_name)
        if not target:
            shutil.rmtree(preview_root, ignore_errors=True)
            return {"error": "Unsafe Skill installation target"}
        manifest = {
            "version": 1,
            "token": token,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "repository": repository,
            "ref": reference,
            "skill_path": skill_path.as_posix(),
            "source_url": source_url,
            "install_name": install_name,
            "source_sha256": source_sha256,
            "source_bytes": len(source_bytes),
            "target_existed": os.path.exists(target),
            "target_hash": get_tree_sha256(target) if os.path.exists(target) else "",
        }
        atomic_write_json(os.path.join(preview_root, "manifest.json"), manifest)
        findings = scan_skill_text(content, skill_path.as_posix())
        return {
            "ok": True,
            "preview_token": token,
            "repository": repository,
            "ref": reference,
            "skill_path": skill_path.as_posix(),
            "source_url": source_url,
            "install_name": install_name,
            "frontmatter": {
                "name": source_name,
                "description": str(frontmatter.get("description") or "")[:500],
            },
            "source_sha256": source_sha256,
            "source_bytes": len(source_bytes),
            "target_exists": manifest["target_existed"],
            "target_hash": manifest["target_hash"],
            "findings": findings,
            "notice": "Preview only. The original UTF-8 bytes are staged; no Skill was installed.",
        }

    def _tool_preview_remote_skill_collection(self, arguments):
        """Preview immediate skills/*/SKILL.md children as one repository collection."""
        try:
            repository, owner, repository_name, reference = (
                self._validated_agent_github_source(
                    arguments["repository"],
                    arguments.get("ref", ""),
                )
            )
        except ValueError as error:
            return {"error": str(error)}

        archive_url = (
            f"https://codeload.github.com/{owner}/{repository_name}/zip/{reference}"
        )
        archive_bytes = b""
        last_error = None
        for _attempt in range(REMOTE_COLLECTION_DOWNLOAD_ATTEMPTS):
            response = None
            try:
                response = requests.get(
                    archive_url,
                    headers={"User-Agent": "SkillHub-SkillOps-Agent/1.0"},
                    timeout=(15, 120),
                    stream=True,
                )
                if response.status_code != 200:
                    return {
                        "error": (
                            f"GitHub repository archive returned HTTP "
                            f"{response.status_code}"
                        )
                    }
                headers = getattr(response, "headers", {})
                content_length = (
                    headers.get("Content-Length", "")
                    if hasattr(headers, "get")
                    else ""
                )
                if (
                    isinstance(content_length, (str, int))
                    and str(content_length).isdigit()
                    and int(content_length) > REMOTE_COLLECTION_ARCHIVE_MAX_BYTES
                ):
                    return {"error": "Repository archive exceeds 100 MB"}
                chunks = []
                total_bytes = 0
                if getattr(response.__class__, "iter_content", None):
                    iterator = response.iter_content(chunk_size=1024 * 1024)
                else:
                    iterator = (response.content,)
                for chunk in iterator:
                    if not chunk:
                        continue
                    total_bytes += len(chunk)
                    if total_bytes > REMOTE_COLLECTION_ARCHIVE_MAX_BYTES:
                        return {"error": "Repository archive exceeds 100 MB"}
                    chunks.append(chunk)
                archive_bytes = b"".join(chunks)
                if archive_bytes:
                    break
                last_error = ValueError("Repository archive is empty")
            except (requests.exceptions.RequestException, ValueError) as error:
                last_error = error
                archive_bytes = b""
            finally:
                close = (
                    getattr(response.__class__, "close", None)
                    if response is not None
                    else None
                )
                if close:
                    response.close()
        if not archive_bytes:
            return {
                "ok": False,
                "error": {
                    "type": type(last_error).__name__ if last_error else "DownloadError",
                    "message": str(last_error or "Repository archive is empty"),
                },
            }

        download_root = self._agent_remote_collection_root()
        if not download_root:
            return {"error": "Unsafe remote collection staging directory"}
        download_token = uuid.uuid4().hex
        staged_download = safe_real_child_path(download_root, download_token)
        if not staged_download:
            return {"error": "Unsafe remote collection preview path"}
        archive_path = os.path.join(staged_download, f"{repository_name}.zip")
        collection_path = os.path.join(staged_download, repository_name)
        os.makedirs(staged_download, exist_ok=False)
        try:
            atomic_write_bytes(archive_path, archive_bytes)
            self._safe_extract_repository_skill_collection_zip(
                archive_path,
                collection_path,
            )
            preview = self.preview_skill_import(collection_path)
        finally:
            shutil.rmtree(staged_download, ignore_errors=True)

        if not preview or preview.get("error"):
            return preview or {"error": "Remote collection preview failed"}
        if (
            preview.get("kind") != "collection"
            or preview.get("collection_count", 0) < 2
        ):
            self.discard_skill_import(preview.get("token", ""))
            return {
                "error": (
                    "Repository is not a SkillHub collection: expected at least "
                    "two immediate skills/*/SKILL.md children"
                )
            }

        token = preview["token"]
        paths = self._skill_import_paths()
        pending_root = safe_real_child_path(paths.get("pending", ""), token)
        manifest_path = (
            os.path.join(pending_root, "manifest.json") if pending_root else ""
        )
        manifest = load_json_file(manifest_path, {}) if manifest_path else {}
        if manifest.get("token") != token:
            self.discard_skill_import(token)
            return {"error": "Remote collection preview manifest is invalid"}

        archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
        collection_id = self._infer_collection_id(
            manifest.get("source_name", repository_name),
            manifest.get("active_names", []),
        )
        manifest["remote_source"] = {
            "repository": repository,
            "ref": reference,
            "archive_url": archive_url,
            "archive_sha256": archive_sha256,
            "collection_id": collection_id,
        }
        atomic_write_json(manifest_path, manifest)

        return {
            "ok": True,
            "kind": "collection",
            "repository": repository,
            "ref": reference,
            "archive_sha256": archive_sha256,
            "source_hash": manifest.get("source_hash", ""),
            "preview_token": token,
            "collection_id": collection_id,
            "collection_count": manifest.get("collection_count", 0),
            "installable_count": manifest.get("installable_count", 0),
            "duplicate_count": manifest.get("duplicate_count", 0),
            "update_count": manifest.get("update_count", 0),
            "conflict_count": manifest.get("conflict_count", 0),
            "has_high_risk": bool(manifest.get("has_high_risk")),
            "findings": manifest.get("findings", []),
            "children": [
                {
                    "folder": item.get("source_name", ""),
                    "install_name": item.get("active_name", ""),
                    "action": item.get("action", ""),
                    "duplicate_of": item.get("duplicate_of", ""),
                }
                for item in manifest.get("collection_items", [])
            ],
            "notice": (
                "Preview only. No child Skill was installed. Repository-level "
                "targets remain collections; use the single-Skill preview only "
                "when one install name was explicitly requested."
            ),
        }

    def _tool_apply_remote_skill_install(self, arguments):
        token = arguments["preview_token"]
        if not re.fullmatch(r"[a-f0-9]{32}", token or ""):
            return {"error": "Invalid remote import preview token"}
        staging_root = self._agent_remote_import_root()
        preview_root = (
            safe_real_child_path(staging_root, token) if staging_root else ""
        )
        if not preview_root or not os.path.isdir(preview_root):
            return {"error": "Remote import preview is missing or expired"}
        manifest = load_json_file(
            os.path.join(preview_root, "manifest.json"),
            {},
        )
        staged_skill = os.path.join(preview_root, "SKILL.md")
        if (
            manifest.get("token") != token
            or manifest.get("install_name") != arguments["install_name"]
            or manifest.get("source_sha256") != arguments["expected_sha256"]
            or not os.path.isfile(staged_skill)
        ):
            return {"error": "Remote import preview metadata does not match approval"}
        with open(staged_skill, "rb") as handle:
            current_source_hash = hashlib.sha256(handle.read()).hexdigest()
        if current_source_hash != manifest["source_sha256"]:
            return {"error": "Staged upstream SKILL.md changed after preview"}

        target = safe_real_child_path(
            self.skills_dir,
            manifest["install_name"],
        )
        if not target:
            return {"error": "Unsafe Skill installation target"}
        target_exists = os.path.exists(target)
        if target_exists and not arguments.get("replace_existing", False):
            return {
                "error": (
                    "Target already exists; create a fresh preview and explicitly "
                    "approve replace_existing"
                )
            }
        current_target_hash = get_tree_sha256(target) if target_exists else ""
        if current_target_hash != manifest.get("target_hash", ""):
            return {
                "error": "Skill target changed after preview; a fresh preview is required"
            }

        transaction_id = uuid.uuid4().hex
        state_root = safe_real_child_path(
            self.skills_dir,
            SKILL_LIBRARY_STATE_DIR,
        )
        if not state_root:
            return {"error": "Unsafe Skill library state directory"}
        backup = os.path.join(
            state_root,
            "agent-install-backups",
            transaction_id,
            manifest["install_name"],
        )
        temporary_target = os.path.join(
            state_root,
            "agent-install-staging",
            transaction_id,
            manifest["install_name"],
        )
        try:
            os.makedirs(temporary_target, exist_ok=False)
            atomic_copy_file(
                staged_skill,
                os.path.join(temporary_target, "SKILL.md"),
            )
            if target_exists:
                os.makedirs(os.path.dirname(backup), exist_ok=True)
                shutil.copytree(target, backup)
                if os.path.isdir(target):
                    shutil.rmtree(target)
                else:
                    os.remove(target)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            os.replace(temporary_target, target)
            self._register_library_entry(
                manifest["install_name"],
                source="agent-remote-install",
            )
            manifest["applied_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            manifest["transaction_id"] = transaction_id
            atomic_write_json(
                os.path.join(preview_root, "manifest.json"),
                manifest,
            )
            self._agent_memory.remember(
                "decision",
                (
                    f"已批准从 {manifest['repository']} 安装 "
                    f"{manifest['install_name']}，SHA-256 "
                    f"{manifest['source_sha256']}。"
                ),
                metadata={
                    "repository": manifest["repository"],
                    "skill_path": manifest["skill_path"],
                    "source_sha256": manifest["source_sha256"],
                    "transaction_id": transaction_id,
                },
                source="runtime",
            )
            return {
                "ok": True,
                "install_name": manifest["install_name"],
                "source_url": manifest["source_url"],
                "source_sha256": manifest["source_sha256"],
                "transaction_id": transaction_id,
                "backup_created": target_exists,
            }
        except Exception as error:
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
            elif os.path.isfile(target):
                try:
                    os.remove(target)
                except OSError:
                    pass
            if os.path.isdir(backup):
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copytree(backup, target)
            shutil.rmtree(
                os.path.join(state_root, "agent-install-staging", transaction_id),
                ignore_errors=True,
            )
            return {"error": str(error)}

    def _tool_apply_remote_skill_collection(self, arguments):
        token = arguments["preview_token"]
        if not re.fullmatch(r"[a-f0-9]{32}", token or ""):
            return {"error": "Invalid remote collection preview token"}
        paths = self._skill_import_paths()
        pending_root = safe_real_child_path(paths.get("pending", ""), token)
        manifest_path = (
            os.path.join(pending_root, "manifest.json") if pending_root else ""
        )
        manifest = load_json_file(manifest_path, {}) if manifest_path else {}
        remote_source = (
            manifest.get("remote_source", {})
            if isinstance(manifest.get("remote_source"), dict)
            else {}
        )
        if (
            manifest.get("token") != token
            or manifest.get("kind") != "collection"
            or remote_source.get("archive_sha256")
            != arguments["expected_archive_sha256"]
            or manifest.get("source_hash") != arguments["expected_source_hash"]
            or manifest.get("collection_count")
            != arguments["expected_collection_count"]
        ):
            return {
                "error": (
                    "Remote collection preview does not match the approved "
                    "archive, source tree, or child count"
                )
            }

        result = self.apply_skill_import(
            token,
            accept_ai_changes=False,
            accept_high_risk=arguments.get("accept_high_risk", False),
            accept_collection_conflicts=arguments.get(
                "accept_collection_conflicts",
                False,
            ),
        )
        if result.get("ok"):
            self._agent_memory.remember(
                "decision",
                (
                    f"已批准从 {remote_source.get('repository', '')} 安装集合 "
                    f"{result.get('collection_id', '')}，包含 "
                    f"{len(result.get('filenames', []))} 个新建或更新的 Skill。"
                ),
                metadata={
                    "repository": remote_source.get("repository", ""),
                    "ref": remote_source.get("ref", ""),
                    "archive_sha256": remote_source.get(
                        "archive_sha256",
                        "",
                    ),
                    "source_hash": manifest.get("source_hash", ""),
                    "collection_id": result.get("collection_id", ""),
                    "installed": result.get("filenames", []),
                },
                source="runtime",
            )
        return result
