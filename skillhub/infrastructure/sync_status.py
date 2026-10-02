"""Read-only project synchronization status evaluation."""

import os
from .skill_resources import walk_skill_resources

from skillhub.infrastructure.filesystem import (
    get_file_md5,
    normalize_relative_path,
)


SYNC_STATE_DIR = os.path.join(".agent", ".skill-hub")
SYNC_MANIFEST_NAME = "manifest.json"
SYNC_LAST_TRANSACTION_NAME = "last-transaction.json"

def check_dir_sync_status(
    src_dir: str,
    dst_root: str,
    skills_dir: str = None,
    md5_cache: dict = None,
    standard_skill: bool = False,
    ignored_relative_paths: set = None,
) -> str:
    """
    Check the synchronization status of a folder skill in a project.
    When skills_dir is provided, a destination file that doesn't match the folder's
    bundled copy is also checked against the standalone global skill file — if it
    matches the standalone version, it is counted as matched because standalone
    file skills take precedence over folder-bundled copies during sync.
    Returns:
      "synced": all files in src_dir exist in dst_root and have matching MD5s.
      "out_of_sync": at least one file exists in dst_root but has mismatched MD5 or some files are missing.
      "unloaded": none of the files in src_dir exist in dst_root.
    """
    total_files = 0
    matched_files = 0
    missing_files = 0
    mismatched_files = 0

    destination_root = (
        os.path.join(dst_root, ".agent", "skills", os.path.basename(src_dir))
        if standard_skill
        else dst_root
    )
    ignored = {
        normalize_relative_path(path).lower()
        for path in (ignored_relative_paths or set())
    }
    for root, dirs, files in walk_skill_resources(src_dir):
        for f in files:
            src_file = os.path.join(root, f)
            rel_path = os.path.relpath(src_file, src_dir)
            if normalize_relative_path(rel_path).lower() in ignored:
                continue

            # Skip checking root README.md and AGENTS.md to avoid constant out-of-sync status
            if not standard_skill and rel_path.lower() in ("readme.md", "agents.md"):
                continue

            total_files += 1
            dst_file = os.path.join(destination_root, rel_path)

            if os.path.exists(dst_file):
                if get_file_md5(src_file, md5_cache) == get_file_md5(dst_file, md5_cache):
                    matched_files += 1
                elif (
                    not standard_skill
                    and skills_dir
                    and _matches_standalone_skill(skills_dir, f, dst_file, md5_cache)
                ):
                    # The project file matches the standalone global skill version
                    # (which takes precedence over the folder-bundled copy during sync).
                    matched_files += 1
                else:
                    mismatched_files += 1
            else:
                missing_files += 1

    if total_files == 0:
        return "unloaded"
    if matched_files == total_files:
        return "synced"
    if matched_files > 0 or mismatched_files > 0:
        return "out_of_sync"
    return "unloaded"

def _matches_standalone_skill(skills_dir: str, filename: str, dst_file: str, md5_cache: dict = None) -> bool:
    """Return True if dst_file's MD5 matches the standalone file skills_dir/filename."""
    standalone = os.path.join(skills_dir, filename)
    if not os.path.isfile(standalone):
        return False
    return get_file_md5(standalone, md5_cache) == get_file_md5(dst_file, md5_cache)
