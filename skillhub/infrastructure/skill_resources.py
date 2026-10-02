"""One resource traversal contract shared by sync planning and status checks."""
import os
from .filesystem import is_path_reparse_point


def walk_skill_resources(root):
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs
                         if not name.startswith(".git")
                         and name not in ("__pycache__", "__MACOSX")
                         and not is_path_reparse_point(os.path.join(directory, name)))
        yield directory, dirs, sorted(name for name in files
                                      if not name.endswith(".pyc")
                                      and not is_path_reparse_point(os.path.join(directory, name)))
