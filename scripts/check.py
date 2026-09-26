"""Run the same offline checks locally and in CI using the active Python env."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main():
    node = shutil.which("node")
    git = shutil.which("git")
    if not node or not git:
        print("Node.js and Git must be available on PATH.", file=sys.stderr)
        return 1
    python = [sys.executable, "-B", "-X", "utf8"]
    steps = [
        *[("JavaScript syntax: " + path.name, [node, "--check", str(path)]) for path in (ROOT / "static").glob("*.js") if not path.name.endswith(".min.js")],
        ("Python regression tests", [*python, "-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("Frontend interaction tests", [node, "--test", *[str(path) for path in (ROOT / "tests").glob("*.test.js")]]),
        ("Agent security evaluations", [*python, "security_evals/run_security_evals.py"]),
        ("Diff whitespace", [git, "diff", "--check"]),
    ]
    with tempfile.TemporaryDirectory(prefix="skillhub-check-", dir=ROOT) as data_dir:
        environment = dict(os.environ, SKILLHUB_DATA_DIR=data_dir, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
        for label, command in steps:
            print(f"\n{label}", flush=True)
            result = subprocess.run(command, cwd=ROOT, env=environment)
            if result.returncode:
                return result.returncode
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
