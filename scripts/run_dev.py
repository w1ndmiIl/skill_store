"""Launch the desktop with isolated data and skills in this checkout."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
def main():
    data = ROOT / ".local" / "runtime"
    library = ROOT / ".local" / "skills"
    data.mkdir(parents=True, exist_ok=True)
    library.mkdir(parents=True, exist_ok=True)
    config = data / "config.json"
    if not config.exists():
        config.write_text(json.dumps({"skills_dir": str(library), "projects": [], "language": "zh", "theme": "light"}), encoding="utf-8")
    env = dict(os.environ, SKILLHUB_DATA_DIR=str(data), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    return subprocess.call([sys.executable, "-B", str(ROOT / "main.py")], cwd=ROOT, env=env)
if __name__ == "__main__":
    raise SystemExit(main())
