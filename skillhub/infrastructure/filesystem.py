"""Filesystem safety, hashing, and atomic persistence primitives."""

import hashlib
import json
import os
import shutil
import stat
import uuid
import threading

from skillhub.domain.naming import normalize_relative_path


def get_file_md5(file_path: str, cache: dict = None) -> str:
    if not os.path.exists(file_path) or os.path.isdir(file_path):
        return ""
    if isinstance(cache, FileHashCache):
        return cache.md5(file_path)
    cache_key = os.path.normcase(os.path.abspath(file_path))
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    digest = hashlib.md5()
    with open(file_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    if cache is not None:
        cache[cache_key] = value
    return value


class FileHashCache:
    """Status-query cache; writes and reviewed sync plans always hash afresh."""
    def __init__(self):
        self.entries = {}
        self.lock = threading.RLock()

    def md5(self, path):
        key = os.path.normcase(os.path.abspath(path))
        with self.lock:
            before = os.stat(path)
            signature = (before.st_mtime_ns, before.st_ctime_ns, before.st_size, before.st_ino)
            old = self.entries.get(key)
            if old and old[0] == signature:
                return old[1]
            digest = get_file_md5(path)
            after = os.stat(path)
            if signature == (after.st_mtime_ns, after.st_ctime_ns, after.st_size, after.st_ino):
                if len(self.entries) >= 20000:
                    self.entries.clear()
                self.entries[key] = (signature, digest)
            return digest


def get_bytes_md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def atomic_write_bytes(path: str, data: bytes):
    """Write bytes beside the destination and atomically replace it."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temp_path = f"{path}.tmp-{uuid.uuid4().hex}"
    try:
        with open(temp_path, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def atomic_write_text(path: str, content: str):
    atomic_write_bytes(path, content.encode("utf-8"))


def atomic_write_json(path: str, value):
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    atomic_write_text(path, content)


def atomic_copy_file(source: str, destination: str):
    os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
    temp_path = f"{destination}.tmp-{uuid.uuid4().hex}"
    try:
        shutil.copy2(source, temp_path)
        os.replace(temp_path, destination)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def load_json_file(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def safe_child_path(root: str, child: str) -> str:
    """Resolve child under root and reject path traversal or absolute paths."""
    if not child or os.path.isabs(child):
        return ""
    root_abs = os.path.abspath(root)
    target = os.path.abspath(os.path.join(root_abs, child))
    try:
        if os.path.commonpath([root_abs, target]) != root_abs:
            return ""
    except ValueError:
        return ""
    return target


def safe_real_child_path(root: str, relative_path: str) -> str:
    """Resolve a relative path while rejecting traversal and symlink escapes."""
    target = safe_child_path(root, relative_path)
    if not target:
        return ""
    root_real = os.path.normcase(os.path.realpath(root))
    target_real = os.path.normcase(os.path.realpath(target))
    try:
        if os.path.commonpath([root_real, target_real]) != root_real:
            return ""
    except ValueError:
        return ""
    return target


def paths_overlap(first: str, second: str) -> bool:
    """Return whether either resolved path contains the other."""
    first_real = os.path.normcase(os.path.realpath(os.path.abspath(first)))
    second_real = os.path.normcase(os.path.realpath(os.path.abspath(second)))
    try:
        common = os.path.commonpath([first_real, second_real])
    except ValueError:
        return False
    return common in (first_real, second_real)


def is_path_reparse_point(path: str) -> bool:
    """Detect symlinks and Windows junction/reparse-point entries."""
    if os.path.islink(path):
        return True
    is_junction = getattr(os.path, "isjunction", None)
    if is_junction and is_junction(path):
        return True
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def get_tree_sha256(path: str) -> str:
    digest = hashlib.sha256()
    if os.path.isfile(path):
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(item for item in dirs if item != "__MACOSX")
        for filename in sorted(files):
            full_path = os.path.join(root, filename)
            relative = normalize_relative_path(os.path.relpath(full_path, path))
            digest.update(relative.encode("utf-8"))
            with open(full_path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
    return digest.hexdigest()
