"""Snapshots used by library mutations under the shared library lock."""
import os
from .filesystem import atomic_write_bytes, atomic_write_json


def capture_files(paths):
    result = {}
    for path in dict.fromkeys(paths):
        if os.path.isfile(path):
            with open(path, "rb") as handle:
                result[path] = handle.read()
        else:
            result[path] = None
    return result


def restore_files(snapshot):
    errors = []
    for path, content in snapshot.items():
        try:
            if content is None:
                if os.path.isfile(path):
                    os.remove(path)
            else:
                atomic_write_bytes(path, content)
        except OSError as error:
            errors.append(f"{path}: {error}")
    return errors


def persist_snapshot(snapshot, directory):
    """Keep recovery metadata on disk before an asset can be moved or replaced."""
    records = []
    for index, (path, data) in enumerate(snapshot.items()):
        backup = f"{index:04d}.bak" if data is not None else ""
        if backup:
            atomic_write_bytes(os.path.join(directory, backup), data)
        records.append({"path": path, "existed": data is not None, "backup": backup})
    atomic_write_json(os.path.join(directory, "recovery.json"), {"files": records})
