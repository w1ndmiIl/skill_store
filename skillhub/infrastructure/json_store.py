"""Strict JSON persistence with shared transactions and explicit recovery."""
import json
import os
import threading
import uuid
from contextlib import contextmanager
from .filesystem import atomic_write_bytes, atomic_write_json

_guard = threading.Lock()
_locks = {}

def file_lock(path):
    key = os.path.normcase(os.path.realpath(path))
    with _guard:
        return _locks.setdefault(key, threading.RLock())

def read_json(path, default, validate=lambda value: True):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        return default
    except (OSError, ValueError) as error:
        raise OSError("Saved data cannot be read; original preserved. Restore a backup before saving.") from error
    if not validate(value):
        raise OSError("Saved data has invalid fields; original preserved.")
    return value

def write_json(path, value, validate=lambda value: True):
    with file_lock(path):
        if not validate(value):
            raise ValueError("Invalid data")
        if os.path.exists(path):
            read_json(path, None, validate)
            with open(path, "rb") as handle:
                atomic_write_bytes(path + ".bak", handle.read())
        atomic_write_json(path, value)

def recover_json(path, validate):
    with file_lock(path):
        backup = path + ".bak"
        if not os.path.isfile(backup):
            raise OSError("No valid backup available; original data has been preserved.")
        value = read_json(backup, None, validate)
        if not validate(value):
            raise OSError("Backup is missing or invalid")
        if os.path.isfile(path):
            with open(path, "rb") as handle:
                atomic_write_bytes(path + ".damaged-" + uuid.uuid4().hex, handle.read())
        atomic_write_json(path, value)
        return {"ok": True}
