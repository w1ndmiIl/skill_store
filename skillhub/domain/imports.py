"""Skill import normalization, bounded diffs, and deterministic safety scans."""

import difflib
import re

from skillhub.domain.frontmatter import (
    preserve_frontmatter_with_missing_fields,
    split_markdown_frontmatter_source,
)
from skillhub.domain.metadata import infer_skill_metadata


SKILL_IMPORT_MAX_FILE_BYTES = 10 * 1024 * 1024
SKILL_IMPORT_MAX_TOTAL_BYTES = 50 * 1024 * 1024
SKILL_IMPORT_MAX_ENTRIES = 2000
SKILL_IMPORT_AI_COLLECTION_MAX_ITEMS = 8
SKILL_IMPORT_DIFF_MAX_CHARS = 24000
def build_import_diff(before: str, after: str, filename: str) -> str:
    """Return a complete bounded diff or reject it as unsafe to approve."""
    diff = "".join(difflib.unified_diff(
        (before or "").splitlines(keepends=True),
        (after or "").splitlines(keepends=True),
        fromfile=f"{filename} (local)",
        tofile=f"{filename} (AI)",
    ))
    if len(diff) > SKILL_IMPORT_DIFF_MAX_CHARS:
        raise ValueError("AI diff is too large to review without truncation")
    return diff

def normalize_skillhub_markdown(content: str, filename: str, language: str = "zh") -> tuple:
    """Normalize a flat SkillHub Markdown skill and return content plus change notes."""
    metadata = infer_skill_metadata(content, filename, language)
    fields = [
        ("title", metadata["title"]),
        ("emoji", metadata["emoji"]),
        ("category", metadata["category"]),
        ("tags", ", ".join(metadata["tags"])),
        ("description", metadata["description"]),
    ]
    changes = []
    _raw, _body, has_frontmatter = split_markdown_frontmatter_source(content)
    normalized, missing = preserve_frontmatter_with_missing_fields(content, fields)
    if not has_frontmatter:
        changes.append("added_frontmatter")
    elif missing:
        changes.append("completed_frontmatter")
    if normalized.replace("\r\n", "\n") != (content or "").replace("\r\n", "\n"):
        changes.append("normalized_metadata")
    return normalized, list(dict.fromkeys(changes)), metadata

def scan_skill_text(content: str, relative_path: str = "") -> list:
    """Return deterministic, non-blocking findings for a skill source."""
    checks = [
        (
            "warning",
            "absolute_path",
            r"(?i)(?:[a-z]:\\(?:users|devapps|projects)\\|/(?:users|home)/[\w.-]+/)",
            "Contains an environment-specific absolute path.",
            "包含与本机环境绑定的绝对路径。",
        ),
        (
            "high",
            "sensitive_logging",
            r"(?is)(?:记录|日志|\blog(?:ged|ging)?\b|\bcaptur(?:e|ed|es|ing)\b).{0,80}(?:authorization|cookie|session id|完整.{0,8}(?:header|body|入参))",
            "May instruct agents to record credentials or complete request/session data.",
            "可能要求记录凭据、完整请求或会话数据。",
        ),
        (
            "warning",
            "destructive_command",
            r"(?i)(?:git\s+reset\s+--hard|rm\s+-rf|remove-item[^\n]{0,80}-recurse[^\n]{0,80}-force)",
            "Contains a potentially destructive command; require explicit scope and approval.",
            "包含潜在破坏性命令，应明确作用域并要求确认。",
        ),
        (
            "warning",
            "tool_specific",
            r"\b(?:grep_search|list_dir|read_file|write_file)\b",
            "References tool-specific command names that may not exist in other agents.",
            "引用了其他 Agent 未必具备的特定工具名。",
        ),
        (
            "warning",
            "pip_freeze_overwrite",
            r"(?i)pip\s+freeze\s*>\s*requirements\.txt",
            "Overwrites requirements.txt with an environment snapshot.",
            "会用环境快照覆盖 requirements.txt。",
        ),
        (
            "warning",
            "stale_cache_action",
            r"actions/cache@v[1-3]\b",
            "Uses an old GitHub cache action example; verify the supported major version.",
            "使用较旧的 GitHub cache action 示例，应核对当前主版本。",
        ),
    ]
    findings = []
    for severity, code, pattern, message_en, message_zh in checks:
        matched = False
        for match in re.finditer(pattern, content or ""):
            if code == "sensitive_logging":
                prefix = (content or "")[
                    max(0, match.start() - 24):match.start()
                ].lower()
                if re.search(
                    r"(?:不|禁止|不得|切勿|避免|never|do\s+not|don't|must\s+not)\s*$",
                    prefix,
                ):
                    continue
                sentence_start = max(
                    (content or "").rfind(separator, 0, match.start())
                    for separator in ("\n", "。", ".", "!", "！", "?", "？")
                )
                context = (content or "")[sentence_start + 1:match.end()].lower()
                if re.search(
                    r"(?:不|禁止|不得|切勿|避免|never|do\s+not|don't|must\s+not)"
                    r"[^。.!！?？\n]{0,24}"
                    r"(?:读取|导出|记录|保存|捕获|回显|暴露|read|export|log|capture|store|save)"
                    r"[^。.!！?？\n]{0,80}"
                    r"(?:authorization|cookie|session id|session 文件|完整.{0,8}(?:header|body|入参))",
                    context,
                ):
                    continue
            matched = True
            break
        if matched:
            findings.append({
                "severity": severity,
                "code": code,
                "path": relative_path,
                "message_en": message_en,
                "message_zh": message_zh,
            })
    return findings
