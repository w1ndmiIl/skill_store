"""Filesystem intake and structural preparation for Skill imports."""

import os
import shutil
import zipfile
from pathlib import PurePosixPath

from skillhub.domain.frontmatter import (
    preserve_frontmatter_with_missing_fields,
    split_markdown_frontmatter,
)
from skillhub.domain.imports import (
    SKILL_IMPORT_MAX_ENTRIES,
    SKILL_IMPORT_MAX_FILE_BYTES,
    SKILL_IMPORT_MAX_TOTAL_BYTES,
)
from skillhub.domain.metadata import (
    clean_frontmatter_value as _clean_frontmatter_value,
    markdown_title_and_description as _markdown_title_and_description,
)
from skillhub.domain.naming import normalize_skill_filename
from skillhub.infrastructure.filesystem import (
    atomic_write_text,
    get_tree_sha256,
    is_path_reparse_point,
    load_json_file,
    safe_real_child_path,
)


class ImportPreparationApiMixin:
    """Validate and normalize import sources before preview construction."""

    def _read_import_markdown(self, path: str) -> tuple:
        size = os.path.getsize(path)
        if size > SKILL_IMPORT_MAX_FILE_BYTES:
            raise ValueError("Skill Markdown file is too large")
        with open(path, "rb") as handle:
            data = handle.read()
        for encoding in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                return data.decode(encoding), encoding
            except UnicodeDecodeError:
                continue
        raise ValueError("Unsupported text encoding")

    def _validate_import_tree(self, source: str) -> None:
        entries = 0
        total_size = 0
        for root, dirs, files in os.walk(source):
            if is_path_reparse_point(root):
                raise ValueError("Directory reparse points are not allowed in imported skills")
            for item in [*dirs, *files]:
                if is_path_reparse_point(os.path.join(root, item)):
                    raise ValueError(
                        "Directory reparse points are not allowed in imported skills"
                    )
            dirs[:] = [
                item for item in dirs
                if item not in (".git", "__pycache__", "__MACOSX")
            ]
            for item in files:
                path = os.path.join(root, item)
                entries += 1
                total_size += os.path.getsize(path)
                if entries > SKILL_IMPORT_MAX_ENTRIES:
                    raise ValueError("Skill package contains too many files")
                if total_size > SKILL_IMPORT_MAX_TOTAL_BYTES:
                    raise ValueError("Skill package is too large")

    def _copy_import_tree(self, source: str, destination: str) -> None:
        self._validate_import_tree(source)
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns(
                ".git", "__pycache__", "__MACOSX", "*.pyc"
            ),
        )

    def _safe_extract_skill_zip(self, source: str, destination: str) -> None:
        if os.path.getsize(source) > SKILL_IMPORT_MAX_TOTAL_BYTES:
            raise ValueError("Skill archive is too large")
        os.makedirs(destination, exist_ok=True)
        total_size = 0
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            if len(entries) > SKILL_IMPORT_MAX_ENTRIES:
                raise ValueError("Skill archive contains too many entries")
            for info in entries:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Skill archive contains an unsafe path")
                unix_mode = (info.external_attr >> 16) & 0o170000
                if unix_mode == 0o120000:
                    raise ValueError("Symbolic links are not allowed in skill archives")
                total_size += info.file_size
                if total_size > SKILL_IMPORT_MAX_TOTAL_BYTES:
                    raise ValueError("Expanded skill archive is too large")
                relative = os.path.join(*path.parts) if path.parts else ""
                target = safe_real_child_path(destination, relative)
                if not target:
                    raise ValueError("Skill archive contains an unsafe path")
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with archive.open(info) as source_handle, open(target, "wb") as target_handle:
                    shutil.copyfileobj(source_handle, target_handle)

    def _unique_import_name(
        self,
        requested: str,
        is_dir: bool,
        reserved_names=None,
    ) -> str:
        name = normalize_skill_filename(requested, ensure_md=not is_dir)
        if is_dir:
            name = name.replace(" ", "-").strip(".-")
        if not name:
            name = "imported-skill" if is_dir else "imported-skill.md"
        reserved = {
            os.path.normcase(item)
            for item in (reserved_names or [])
        }
        stem, extension = os.path.splitext(name) if not is_dir else (name, "")
        candidate = name
        counter = 2
        while (
            os.path.exists(os.path.join(self.skills_dir, candidate))
            or os.path.normcase(candidate) in reserved
        ):
            candidate = f"{stem}-{counter}{extension}"
            counter += 1
        return candidate

    def _standard_skill_collection_children(self, candidate: str) -> list:
        """Return immediate standard-skill children from a repository-style collection."""
        possible_roots = [
            os.path.join(candidate, "skills"),
            candidate,
        ]
        for root in possible_roots:
            if not os.path.isdir(root):
                continue
            children = []
            for item in sorted(os.listdir(root)):
                child = os.path.join(root, item)
                if (
                    not item.startswith(".")
                    and os.path.isdir(child)
                    and os.path.isfile(os.path.join(child, "SKILL.md"))
                ):
                    children.append(child)
            if children:
                return children
        return []

    def _find_import_duplicate(self, adapted_path: str, exclude_name="") -> str:
        candidate_hash = get_tree_sha256(adapted_path)
        for item in os.listdir(self.skills_dir):
            if item.startswith("."):
                continue
            if exclude_name and os.path.normcase(item) == os.path.normcase(exclude_name):
                continue
            active = os.path.join(self.skills_dir, item)
            if os.path.isfile(active) and not item.lower().endswith(".md"):
                continue
            try:
                if get_tree_sha256(active) == candidate_hash:
                    return item
            except OSError:
                continue
        return ""

    def _existing_library_name(self, requested_name: str) -> str:
        requested_key = (requested_name or "").casefold()
        for item in os.listdir(self.skills_dir):
            if item.casefold() == requested_key:
                return item
        return ""

    def _classify_collection_candidate(
        self,
        adapted_path: str,
        existing_name: str,
    ) -> dict:
        candidate_hash = get_tree_sha256(adapted_path)
        if not existing_name:
            duplicate = self._find_import_duplicate(adapted_path)
            return {
                "action": "duplicate" if duplicate else "install",
                "duplicate_of": duplicate,
                "existing_hash": "",
            }

        existing_path = os.path.join(self.skills_dir, existing_name)
        existing_hash = get_tree_sha256(existing_path)
        if candidate_hash == existing_hash:
            return {
                "action": "duplicate",
                "duplicate_of": existing_name,
                "existing_hash": existing_hash,
            }

        index = load_json_file(self._library_index_path(), {})
        entries = index.get("entries", {}) if isinstance(index, dict) else {}
        registered = next(
            (
                metadata
                for name, metadata in entries.items()
                if name.casefold() == existing_name.casefold()
            ),
            {},
        )
        action = (
            "update"
            if registered.get("hash") == existing_hash
            else "conflict"
        )
        return {
            "action": action,
            "duplicate_of": "",
            "existing_hash": existing_hash,
        }

    def _normalize_standard_skill(self, skill_path: str, folder_name: str) -> list:
        content, _encoding = self._read_import_markdown(skill_path)
        frontmatter, body = split_markdown_frontmatter(content)
        name = frontmatter.get("name") or folder_name.lower().replace(" ", "-")
        _title, inferred_description = _markdown_title_and_description(
            body, folder_name, self.language
        )
        description = frontmatter.get("description") or inferred_description
        normalized, missing = preserve_frontmatter_with_missing_fields(
            content,
            [
                ("name", _clean_frontmatter_value(name, "imported-skill")),
                ("description", _clean_frontmatter_value(description)),
            ],
        )
        if not missing:
            return []
        atomic_write_text(skill_path, normalized)
        return ["completed_standard_skill_metadata"]
