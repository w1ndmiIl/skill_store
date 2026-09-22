"""Windows single-instance process guard."""

import atexit
import ctypes
import os
import hashlib
from skillhub.settings import USER_DATA_DIR


SINGLE_INSTANCE_MUTEX_NAME = r"Local\SkillHub.Desktop.SingleInstance." + hashlib.sha256(os.path.normcase(os.path.realpath(USER_DATA_DIR)).encode()).hexdigest()[:16]
ERROR_ALREADY_EXISTS = 183
_single_instance_guard = None
class SingleInstanceGuard:
    """Hold a Windows named mutex for the lifetime of one SkillHub process."""

    def __init__(self, kernel32, get_last_error):
        self.kernel32 = kernel32
        self.get_last_error = get_last_error
        self.handle = None

    def acquire(self, name: str) -> bool:
        create_mutex = self.kernel32.CreateMutexW
        close_handle = self.kernel32.CloseHandle
        try:
            create_mutex.argtypes = [
                ctypes.c_void_p,
                ctypes.c_bool,
                ctypes.c_wchar_p,
            ]
            create_mutex.restype = ctypes.c_void_p
            close_handle.argtypes = [ctypes.c_void_p]
            close_handle.restype = ctypes.c_bool
        except (AttributeError, TypeError):
            # Lightweight fakes used by tests do not expose ctypes attributes.
            pass
        try:
            ctypes.set_last_error(0)
        except (AttributeError, OSError):
            pass
        handle = create_mutex(None, False, name)
        last_error = self.get_last_error()
        if not handle:
            return False
        if last_error == ERROR_ALREADY_EXISTS:
            close_handle(handle)
            return False
        self.handle = handle
        return True

    def release(self) -> None:
        if not self.handle:
            return
        self.kernel32.CloseHandle(self.handle)
        self.handle = None

def acquire_skillhub_single_instance() -> bool:
    """Acquire the per-user-session SkillHub mutex before creating any UI."""
    global _single_instance_guard
    if os.name != "nt":
        return True
    guard = SingleInstanceGuard(
        ctypes.WinDLL("kernel32", use_last_error=True),
        ctypes.get_last_error,
    )
    if not guard.acquire(SINGLE_INSTANCE_MUTEX_NAME):
        return False
    _single_instance_guard = guard
    atexit.register(guard.release)
    return True

def focus_existing_skillhub_window() -> None:
    """Bring the existing window forward while the duplicate process exits."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "SkillHub")
        if hwnd:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
