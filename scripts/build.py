"""Build locally and record the exact source and executable fingerprints."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()
def main():
    files = [ROOT / name for name in ("main.py", "agent_runtime.py", "SkillHub.spec", "requirements.txt", "app.ico")]
    for directory in ("skillhub", "static"):
        files.extend(p for p in (ROOT / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    source = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files)}
    result = subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--workpath", str(ROOT / ".local" / "builds" / "current"), "SkillHub.spec"], cwd=ROOT)
    if result.returncode:
        return result.returncode
    exe = ROOT / "dist" / "SkillHub.exe"
    digest = sha(exe)
    (exe.parent / "SHA256SUMS.txt").write_text(digest + "  SkillHub.exe\n", encoding="utf-8")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    metadata = {"git_head": revision, "source_fingerprint": hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest(), "source_files": source, "executable_sha256": digest}
    (exe.parent / "BUILD_INFO.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Built " + str(exe) + " SHA-256 " + digest)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
