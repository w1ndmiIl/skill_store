"""Portable naming rules for SkillHub and Agent Skill identifiers."""

import hashlib
import re


AGENT_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_relative_path(path: str) -> str:
    """Normalize a relative path for portable manifests and Markdown links."""
    return path.replace("\\", "/").lstrip("/")


def normalize_skill_filename(filename: str, ensure_md: bool = False) -> str:
    """Return a safe single-file skill name while preserving readable characters."""
    name = (filename or "").strip().replace("\\", "_").replace("/", "_")
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "", name).strip(" .")
    if ensure_md and name and not name.lower().endswith(".md"):
        name += ".md"
    return name


def normalize_agent_skill_name(value: str, fallback: str = "skill") -> str:
    """Return a portable Agent Skill identifier without changing source metadata."""
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    normalized = re.sub(r"-+", "-", normalized)[:64].strip("-")
    if AGENT_SKILL_NAME_RE.fullmatch(normalized or ""):
        return normalized
    fallback_name = re.sub(
        r"[^a-z0-9]+", "-", str(fallback or "skill").casefold()
    ).strip("-")[:64].strip("-")
    if AGENT_SKILL_NAME_RE.fullmatch(fallback_name or ""):
        return fallback_name
    seed = f"{value}\0{fallback}".encode("utf-8", errors="replace")
    return f"skill-{hashlib.sha256(seed).hexdigest()[:8]}"


def is_project_rules_document(value):
    text = str(value or "").replace("\\", "/")
    return text.rsplit("/", 1)[-1].casefold() == "agents.md" or text.casefold().startswith("@project-rules:")
