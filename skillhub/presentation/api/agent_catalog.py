"""Agent tools for local inspection and SkillHub catalog workflows."""

import hashlib
import os
import re
import shutil
import time
import uuid

import requests
from ddgs import DDGS

from skillhub.domain.catalog import parse_markdown_metadata
from skillhub.domain.compatibility import inspect_agent_skill_compatibility
from skillhub.domain.frontmatter import (
    frontmatter_top_level_keys,
    split_markdown_frontmatter,
    split_markdown_frontmatter_source,
)
from skillhub.domain.global_targets import SKILL_LIBRARY_STATE_DIR
from skillhub.domain.imports import SKILL_IMPORT_MAX_TOTAL_BYTES, scan_skill_text
from skillhub.infrastructure.filesystem import (
    atomic_write_bytes,
    atomic_write_json,
    get_tree_sha256,
    is_path_reparse_point,
    load_json_file,
    safe_real_child_path,
)
from skillhub.settings import (
    SKILLHUB_DOWNLOAD_URL,
    SKILLHUB_INSTALL_GUIDE_URL,
    SKILLHUB_SEARCH_URL,
)


class AgentCatalogApiMixin:
    """Implement local and SkillHub catalog Agent tools."""

    def _tool_search_skills(self, arguments):
        query = arguments["query"].strip().casefold()
        limit = arguments.get("limit", 10)
        results = []
        for skill in self._collect_skills(include_global_state=False):
            searchable = " ".join([
                str(skill.get("filename", "")),
                str(skill.get("title", "")),
                str(skill.get("description", "")),
                str(skill.get("category", "")),
                " ".join(str(tag) for tag in skill.get("tags", [])),
            ]).casefold()
            if query in searchable or all(
                term in searchable for term in query.split()
            ):
                results.append({
                    "filename": skill.get("filename", ""),
                    "title": skill.get("title", ""),
                    "description": skill.get("description", "")[:300],
                    "category": skill.get("category", ""),
                    "tags": skill.get("tags", [])[:8],
                    "is_directory": bool(skill.get("is_dir")),
                    "is_virtual": bool(skill.get("is_virtual")),
                })
            if len(results) >= limit:
                break
        return {"ok": True, "query": arguments["query"], "results": results}

    def _tool_inspect_skill(self, arguments):
        filename = arguments["filename"]
        source = self._editable_skill_source(filename)
        if not source:
            return {"error": "Skill not found or is outside the global library"}
        root = os.path.realpath(os.path.abspath(self.skills_dir))
        target = os.path.realpath(os.path.abspath(source["path"]))
        try:
            if os.path.commonpath([root, target]) != root:
                return {"error": "Skill path is outside the global library"}
        except ValueError:
            return {"error": "Skill path is outside the global library"}
        max_chars = arguments.get("max_chars", 8000)
        try:
            with open(target, "r", encoding="utf-8") as handle:
                content = handle.read(max_chars + 1)
        except Exception as error:
            return {"error": str(error)}
        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars]
        metadata = parse_markdown_metadata(target)
        return {
            "ok": True,
            "filename": filename,
            "entry_file": os.path.relpath(target, root).replace("\\", "/"),
            "metadata": {
                "title": metadata.get("title", ""),
                "description": metadata.get("description", ""),
                "category": metadata.get("category", ""),
                "tags": metadata.get("tags", [])[:12],
            },
            "content": content,
            "truncated": truncated,
            "notice": (
                f"Content truncated to {max_chars} characters"
                if truncated else ""
            ),
        }

    def _tool_audit_skill_library(self, arguments):
        severity_filter = arguments.get("minimum_severity", "info")
        severity_rank = {"info": 0, "warning": 1, "error": 2}
        findings = []
        skills = self.get_skills()
        title_owners = {}
        descriptions = []
        for skill in skills:
            filename = skill.get("filename", "")
            source = self._editable_skill_source(filename)
            if not source:
                continue
            metadata = parse_markdown_metadata(source["path"])
            try:
                with open(source["path"], "r", encoding="utf-8") as handle:
                    content = handle.read()
            except OSError as error:
                findings.append({
                    "severity": "error",
                    "code": "read_error",
                    "skill": filename,
                    "evidence": str(error),
                    "suggestion": "Check file availability and permissions.",
                })
                continue
            raw_frontmatter, _body, has_frontmatter = (
                split_markdown_frontmatter_source(content)
            )
            declared_fields = (
                frontmatter_top_level_keys(raw_frontmatter)
                if has_frontmatter else set()
            )
            is_standard_skill = os.path.basename(source["path"]) == "SKILL.md"
            required_fields = (
                ("name", "description")
                if is_standard_skill
                else ("title", "description", "category", "tags")
            )
            for field in required_fields:
                if field not in declared_fields:
                    findings.append({
                        "severity": "warning",
                        "code": "missing_metadata",
                        "skill": filename,
                        "evidence": f"Missing or empty metadata field: {field}",
                        "suggestion": f"Add a clear {field} value to the Skill frontmatter.",
                    })
            description = str(metadata.get("description", "")).strip()
            if description and len(description) < 20:
                findings.append({
                    "severity": "info",
                    "code": "vague_description",
                    "skill": filename,
                    "evidence": f"Description is only {len(description)} characters.",
                    "suggestion": "Describe when the Skill should and should not trigger.",
                })
            normalized_title = re.sub(
                r"\W+", "", str(metadata.get("title", "")).casefold()
            )
            if normalized_title:
                title_owners.setdefault(normalized_title, []).append(filename)
            terms = {
                term for term in re.findall(
                    r"[\w\u4e00-\u9fff]{2,}", description.casefold()
                )
                if len(term) > 1
            }
            if terms:
                descriptions.append((filename, terms))
            for issue in scan_skill_text(content, filename):
                findings.append({
                    "severity": (
                        "error" if issue.get("severity") in ("error", "high")
                        else "warning"
                    ),
                    "code": issue.get("code", "format_issue"),
                    "skill": filename,
                    "evidence": issue.get(
                        "message_zh" if self.language == "zh" else "message_en",
                        "Format issue",
                    ),
                    "suggestion": "Review the referenced content before using this Skill.",
                })
            source_parent = os.path.dirname(source["path"])
            is_top_level_file = self._same_real_path(
                source_parent, self.skills_dir
            )
            if is_top_level_file:
                compatibility_name = os.path.splitext(
                    os.path.basename(source["path"])
                )[0]
                package_size = os.path.getsize(source["path"])
            else:
                compatibility_name = os.path.basename(source_parent)
                package_size = sum(
                    os.path.getsize(os.path.join(root, name))
                    for root, dirs, files in os.walk(
                        source_parent, followlinks=False
                    )
                    for name in files
                    if not is_path_reparse_point(os.path.join(root, name))
                )
            compatibility = inspect_agent_skill_compatibility(
                content,
                compatibility_name,
                package_size,
                layout="markdown" if is_top_level_file else "standard",
            )
            for issue in compatibility["findings"]:
                findings.append({
                    "severity": (
                        "error" if issue["severity"] == "high"
                        else issue["severity"]
                    ),
                    "code": issue["code"],
                    "skill": filename,
                    "evidence": issue.get(
                        "message_zh" if self.language == "zh" else "message_en",
                        "Compatibility issue",
                    ),
                    "suggestion": (
                        "Use the client-specific SkillHub publishing view; "
                        "do not rewrite the source Skill semantics."
                    ),
                })
        for filenames in title_owners.values():
            if len(filenames) > 1:
                findings.append({
                    "severity": "warning",
                    "code": "duplicate_title",
                    "skill": ", ".join(filenames),
                    "evidence": "Multiple Skills use the same normalized title.",
                    "suggestion": "Merge them or make their trigger scopes distinct.",
                })
        for index, (first_name, first_terms) in enumerate(descriptions):
            for second_name, second_terms in descriptions[index + 1:]:
                union = first_terms | second_terms
                overlap = len(first_terms & second_terms) / len(union) if union else 0
                if overlap >= 0.72:
                    findings.append({
                        "severity": "warning",
                        "code": "overlapping_trigger_scope",
                        "skill": f"{first_name}, {second_name}",
                        "evidence": f"Description keyword overlap is {overlap:.0%}.",
                        "suggestion": "Clarify mutually exclusive trigger and non-trigger conditions.",
                    })
        findings = [
            finding for finding in findings
            if severity_rank[finding["severity"]] >= severity_rank[severity_filter]
        ][:100]
        counts = {
            level: sum(1 for item in findings if item["severity"] == level)
            for level in severity_rank
        }
        return {
            "ok": True,
            "skills_checked": len(skills),
            "summary": counts,
            "findings": findings,
        }

    def _tool_web_research(self, arguments):
        results = []
        try:
            with DDGS() as ddgs:
                for item in ddgs.text(
                    arguments["query"],
                    max_results=arguments.get("max_results", 5),
                ):
                    results.append({
                        "title": item.get("title", ""),
                        "summary": item.get("body", "")[:500],
                        "url": item.get("href", ""),
                    })
        except Exception as error:
            return {
                "ok": False,
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }
        return {"ok": True, "query": arguments["query"], "sources": results}

    def _tool_fetch_skillhub_install_guide(self, _arguments):
        """Read the fixed public SkillHub installation guide without arbitrary URL access."""
        try:
            response = requests.get(
                SKILLHUB_INSTALL_GUIDE_URL,
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
            return {
                "error": (
                    f"SkillHub install guide returned HTTP {response.status_code}"
                )
            }
        content = response.content
        if not content or len(content) > 100_000:
            return {"error": "SkillHub install guide is empty or too large"}
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return {"error": "SkillHub install guide is not valid UTF-8"}
        return {
            "ok": True,
            "url": SKILLHUB_INSTALL_GUIDE_URL,
            "sha256": hashlib.sha256(content).hexdigest(),
            "content": text,
        }

    @staticmethod
    def _skillhub_public_result(item):
        namespace = (
            item.get("namespace", {})
            if isinstance(item.get("namespace"), dict)
            else {}
        )
        labels = (
            item.get("labels", {})
            if isinstance(item.get("labels"), dict)
            else {}
        )
        return {
            "slug": str(item.get("slug") or ""),
            "name": str(item.get("name") or item.get("displayName") or ""),
            "description": str(
                item.get("description") or item.get("summary") or ""
            )[:1000],
            "description_zh": str(item.get("description_zh") or "")[:1000],
            "version": str(item.get("version") or ""),
            "source": str(item.get("source") or "skillhub"),
            "owner": str(
                item.get("owner_name")
                or namespace.get("handle")
                or ""
            ),
            "canonical_name": str(namespace.get("canonicalName") or ""),
            "requires_api_key": str(labels.get("requires_api_key") or "false"),
            "downloads": int(item.get("downloads") or 0),
            "installs": int(item.get("installs") or 0),
            "stars": int(item.get("stars") or 0),
        }

    def _skillhub_search(self, query, limit=10):
        response = requests.get(
            SKILLHUB_SEARCH_URL,
            params={"q": query, "limit": limit},
            headers={
                "User-Agent": "SkillHub-SkillOps-Agent/1.0",
                "Accept": "application/json",
            },
            timeout=30,
        )
        if response.status_code != 200:
            raise ValueError(
                f"SkillHub search returned HTTP {response.status_code}"
            )
        payload = response.json()
        results = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(results, list):
            raise ValueError("SkillHub search returned an invalid result list")
        return [
            self._skillhub_public_result(item)
            for item in results[:limit]
            if isinstance(item, dict)
        ]

    def _tool_search_skillhub_catalog(self, arguments):
        try:
            results = self._skillhub_search(
                arguments["query"],
                arguments.get("limit", 10),
            )
        except (
            requests.exceptions.RequestException,
            ValueError,
            TypeError,
        ) as error:
            return {
                "ok": False,
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }
        return {
            "ok": True,
            "query": arguments["query"],
            "results": results,
            "source": SKILLHUB_SEARCH_URL,
        }

    def _agent_skillhub_import_root(self):
        return safe_real_child_path(
            self.skills_dir,
            os.path.join(
                SKILL_LIBRARY_STATE_DIR,
                "agent-skillhub-imports",
            ),
        )

    def _tool_preview_skillhub_catalog_install(self, arguments):
        slug = str(arguments["slug"] or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", slug):
            return {"error": "Invalid SkillHub slug"}
        try:
            results = self._skillhub_search(slug, 20)
        except (
            requests.exceptions.RequestException,
            ValueError,
            TypeError,
        ) as error:
            return {
                "ok": False,
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            }
        exact = next(
            (
                item
                for item in results
                if item.get("slug", "").casefold() == slug.casefold()
            ),
            None,
        )
        if not exact:
            return {
                "error": (
                    f"SkillHub search returned no exact slug match for '{slug}'"
                ),
                "candidates": [item.get("slug", "") for item in results[:8]],
            }
        try:
            response = requests.get(
                SKILLHUB_DOWNLOAD_URL,
                params={"slug": slug},
                headers={
                    "User-Agent": "SkillHub-SkillOps-Agent/1.0",
                    "Accept": "application/zip,*/*",
                },
                timeout=45,
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
            return {
                "error": (
                    f"SkillHub download returned HTTP {response.status_code}"
                )
            }
        archive_bytes = response.content
        if not archive_bytes or len(archive_bytes) > SKILL_IMPORT_MAX_TOTAL_BYTES:
            return {"error": "SkillHub package is empty or too large"}

        staging_root = self._agent_skillhub_import_root()
        if not staging_root:
            return {"error": "Unsafe SkillHub import staging directory"}
        token = uuid.uuid4().hex
        preview_root = safe_real_child_path(staging_root, token)
        if not preview_root:
            return {"error": "Unsafe SkillHub preview path"}
        archive_path = os.path.join(preview_root, "package.zip")
        package_root = os.path.join(preview_root, "package")
        try:
            os.makedirs(preview_root, exist_ok=False)
            atomic_write_bytes(archive_path, archive_bytes)
            self._safe_extract_skill_zip(archive_path, package_root)
            skill_file = os.path.join(package_root, "SKILL.md")
            if not os.path.isfile(skill_file):
                raise ValueError(
                    "SkillHub package must contain a root SKILL.md"
                )
            with open(skill_file, "r", encoding="utf-8") as handle:
                skill_content = handle.read()
            package_sha256 = hashlib.sha256(archive_bytes).hexdigest()
            source_hash = get_tree_sha256(package_root)
            target = safe_real_child_path(self.skills_dir, slug)
            if not target:
                raise ValueError("Unsafe SkillHub installation target")
            target_exists = os.path.exists(target)
            target_hash = get_tree_sha256(target) if target_exists else ""
            manifest = {
                "version": 1,
                "kind": "skillhub-catalog",
                "token": token,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "slug": slug,
                "catalog": exact,
                "search_url": SKILLHUB_SEARCH_URL,
                "download_url": f"{SKILLHUB_DOWNLOAD_URL}?slug={slug}",
                "package_sha256": package_sha256,
                "source_hash": source_hash,
                "target_existed": target_exists,
                "target_hash": target_hash,
            }
            atomic_write_json(
                os.path.join(preview_root, "manifest.json"),
                manifest,
            )
        except Exception as error:
            shutil.rmtree(preview_root, ignore_errors=True)
            return {"error": str(error)}

        frontmatter, _body = split_markdown_frontmatter(skill_content)
        return {
            "ok": True,
            "kind": "skillhub-catalog",
            "preview_token": token,
            "slug": slug,
            "catalog": exact,
            "frontmatter": {
                "name": str(frontmatter.get("name") or ""),
                "description": str(frontmatter.get("description") or "")[:500],
            },
            "package_sha256": package_sha256,
            "source_hash": source_hash,
            "file_count": sum(
                len(files) for _root, _dirs, files in os.walk(package_root)
            ),
            "target_exists": target_exists,
            "target_hash": target_hash,
            "requires_user_choice": target_exists,
            "available_actions": (
                ["replace", "keep_both", "cancel"]
                if target_exists
                else ["install", "cancel"]
            ),
            "findings": scan_skill_text(skill_content, "SKILL.md"),
            "notice": (
                "Preview only. The exact public SkillHub package is hash-locked "
                "and staged; the global Skill library was not modified."
            ),
        }

    def _tool_apply_skillhub_catalog_install(self, arguments):
        token = arguments["preview_token"]
        slug = arguments["slug"]
        strategy = arguments["conflict_strategy"]
        if not re.fullmatch(r"[a-f0-9]{32}", token or ""):
            return {"error": "Invalid SkillHub preview token"}
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", slug or ""):
            return {"error": "Invalid SkillHub slug"}
        staging_root = self._agent_skillhub_import_root()
        preview_root = (
            safe_real_child_path(staging_root, token) if staging_root else ""
        )
        if not preview_root or not os.path.isdir(preview_root):
            return {"error": "SkillHub install preview is missing or expired"}
        manifest = load_json_file(
            os.path.join(preview_root, "manifest.json"),
            {},
        )
        package_root = os.path.join(preview_root, "package")
        archive_path = os.path.join(preview_root, "package.zip")
        if (
            manifest.get("token") != token
            or manifest.get("kind") != "skillhub-catalog"
            or manifest.get("slug") != slug
            or manifest.get("package_sha256")
            != arguments["expected_package_sha256"]
            or manifest.get("source_hash") != arguments["expected_source_hash"]
            or not os.path.isdir(package_root)
            or not os.path.isfile(archive_path)
        ):
            return {"error": "SkillHub preview metadata does not match approval"}
        if get_tree_sha256(package_root) != manifest["source_hash"]:
            return {"error": "Staged SkillHub package changed after preview"}
        if get_tree_sha256(archive_path) != manifest["package_sha256"]:
            return {"error": "Staged SkillHub archive changed after preview"}

        original_target = safe_real_child_path(self.skills_dir, slug)
        if not original_target:
            return {"error": "Unsafe SkillHub installation target"}
        target_exists = os.path.exists(original_target)
        current_target_hash = (
            get_tree_sha256(original_target) if target_exists else ""
        )
        if current_target_hash != manifest.get("target_hash", ""):
            return {
                "error": (
                    "Skill target changed after preview; a fresh preview is required"
                )
            }
        if target_exists and strategy == "install":
            return {
                "error": (
                    "Target already exists; choose replace, keep_both, or cancel"
                )
            }
        if not target_exists and strategy != "install":
            return {
                "error": (
                    "No target conflict exists; conflict_strategy must be install"
                )
            }
        target_name = (
            self._unique_import_name(slug, True)
            if target_exists and strategy == "keep_both"
            else slug
        )
        target = safe_real_child_path(self.skills_dir, target_name)
        if not target:
            return {"error": "Unsafe SkillHub installation target"}

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
            slug,
        )
        temporary_target = os.path.join(
            state_root,
            "agent-install-staging",
            transaction_id,
            target_name,
        )
        backup_created = False
        try:
            self._copy_import_tree(package_root, temporary_target)
            if target_exists and strategy == "replace":
                os.makedirs(os.path.dirname(backup), exist_ok=True)
                shutil.copytree(original_target, backup)
                backup_created = True
                shutil.rmtree(original_target)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            os.replace(temporary_target, target)
            self._register_library_entry(
                target_name,
                source="skillhub-catalog",
            )
            source_metadata = parse_markdown_metadata(
                os.path.join(target, "SKILL.md")
            )
            source_language = self._detect_display_metadata_language(
                source_metadata
            )
            catalog = (
                manifest.get("catalog", {})
                if isinstance(manifest.get("catalog"), dict)
                else {}
            )
            localized_description = ""
            if self.language == "zh" and source_language == "en":
                candidates = (
                    catalog.get("description_zh"),
                    catalog.get("description"),
                )
                for value in candidates:
                    candidate = str(value or "").strip()
                    if candidate and self._detect_display_metadata_language({
                        "title": "",
                        "description": candidate,
                    }) == "zh":
                        localized_description = candidate
                        break
            elif self.language == "en" and source_language == "zh":
                candidates = (
                    catalog.get("description_en"),
                    catalog.get("description"),
                )
                for value in candidates:
                    candidate = str(value or "").strip()
                    if candidate and self._detect_display_metadata_language({
                        "title": "",
                        "description": candidate,
                    }) == "en":
                        localized_description = candidate
                        break
            if localized_description:
                self._persist_display_localizations({
                    target_name: {
                        "source_signature": (
                            self._display_metadata_signature(source_metadata)
                        ),
                        "source_language": source_language,
                        "translations": {
                            self.language: {
                                "title": "",
                                "description": localized_description,
                            }
                        },
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    }
                })
            manifest["applied_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            manifest["transaction_id"] = transaction_id
            manifest["installed_name"] = target_name
            manifest["conflict_strategy"] = strategy
            atomic_write_json(
                os.path.join(preview_root, "manifest.json"),
                manifest,
            )
            self._agent_memory.remember(
                "decision",
                (
                    f"已批准从 SkillHub 安装 {slug} 为 {target_name}，"
                    f"包 SHA-256 {manifest['package_sha256']}。"
                ),
                metadata={
                    "slug": slug,
                    "installed_name": target_name,
                    "version": manifest.get("catalog", {}).get("version", ""),
                    "package_sha256": manifest["package_sha256"],
                    "transaction_id": transaction_id,
                },
                source="runtime",
            )
            return {
                "ok": True,
                "slug": slug,
                "installed_name": target_name,
                "version": manifest.get("catalog", {}).get("version", ""),
                "package_sha256": manifest["package_sha256"],
                "source_hash": manifest["source_hash"],
                "transaction_id": transaction_id,
                "backup_created": backup_created,
                "conflict_strategy": strategy,
            }
        except Exception as error:
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
            if backup_created and os.path.isdir(backup):
                os.makedirs(os.path.dirname(original_target), exist_ok=True)
                shutil.copytree(backup, original_target)
            shutil.rmtree(
                os.path.join(
                    state_root,
                    "agent-install-staging",
                    transaction_id,
                ),
                ignore_errors=True,
            )
            return {"error": str(error)}
