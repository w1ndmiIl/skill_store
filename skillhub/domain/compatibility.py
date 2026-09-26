"""Cross-client Agent Skill compatibility evaluation."""

import yaml

from skillhub.domain.frontmatter import (
    build_agent_skill_view,
    split_markdown_frontmatter_source,
)
from skillhub.domain.global_targets import (
    ANTIGRAVITY_FRONTMATTER_KEYS,
    CLINE_FRONTMATTER_KEYS,
    CLAUDE_CODE_FRONTMATTER_KEYS,
    CLAUDE_UPLOAD_FRONTMATTER_KEYS,
    CODEX_FRONTMATTER_KEYS,
    CURSOR_FRONTMATTER_KEYS,
    GEMINI_FRONTMATTER_KEYS,
    OPENCODE_FRONTMATTER_KEYS,
    WINDSURF_FRONTMATTER_KEYS,
)
from skillhub.domain.naming import AGENT_SKILL_NAME_RE, normalize_agent_skill_name


def build_codex_skill_view(
    content: str,
    fallback_name: str,
    fallback_description: str,
) -> tuple:
    return build_agent_skill_view(
        content,
        fallback_name,
        fallback_description,
        CODEX_FRONTMATTER_KEYS,
    )

def inspect_agent_skill_compatibility(
    content: str,
    entry_name: str,
    package_bytes: int = 0,
    *,
    layout: str = "standard",
) -> dict:
    """Return deterministic per-client compatibility without mutating the Skill."""
    raw_frontmatter, _body, has_frontmatter = split_markdown_frontmatter_source(
        content
    )
    findings = []
    if layout == "markdown":
        findings.append({
            "severity": "warning",
            "code": "nonstandard_skill_layout",
            "path": entry_name,
            "message_en": "A portable Skill uses <name>/SKILL.md; this single Markdown file remains usable through SkillHub compatibility support.",
            "message_zh": "可移植 Skill 应采用 <名称>/SKILL.md；此单文件仍可通过 SkillHub 兼容支持使用。",
        })
    parsed = {}
    if not has_frontmatter:
        findings.append({
            "severity": "high",
            "code": "invalid_skill_frontmatter",
            "path": "SKILL.md",
            "message_en": "SKILL.md must start with YAML frontmatter.",
            "message_zh": "SKILL.md 必须从 YAML frontmatter 开始。",
        })
    else:
        try:
            parsed = yaml.safe_load(raw_frontmatter) or {}
            if not isinstance(parsed, dict):
                raise ValueError("frontmatter is not a mapping")
        except (yaml.YAMLError, ValueError) as error:
            findings.append({
                "severity": "high",
                "code": "invalid_skill_frontmatter",
                "path": "SKILL.md",
                "message_en": f"Invalid YAML frontmatter: {error}",
                "message_zh": f"YAML frontmatter 无效：{error}",
            })
            parsed = {}

    raw_name = parsed.get("name", "")
    raw_description = parsed.get("description", "")
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    description = (
        raw_description.strip() if isinstance(raw_description, str) else ""
    )
    portable_name = normalize_agent_skill_name(name or entry_name, entry_name)
    valid_name = bool(
        name
        and len(name) <= 64
        and AGENT_SKILL_NAME_RE.fullmatch(name)
    )
    valid_description = bool(
        description
        and len(description) <= 1024
        and "<" not in description
        and ">" not in description
    )
    if layout == "standard" and name and name != entry_name:
        findings.append({
            "severity": "warning",
            "code": "skill_name_folder_mismatch",
            "path": "SKILL.md",
            "message_en": f"Skill name '{name}' does not match its folder '{entry_name}'. Check internal references before renaming either one.",
            "message_zh": f"Skill 名称“{name}”与文件夹“{entry_name}”不一致；改名之前请检查包内引用。",
        })
    top_level_keys = set(parsed) if isinstance(parsed, dict) else set()

    targets = {
        "codex": {
            "label": "Codex",
            "status": (
                "ready" if valid_name and valid_description
                and top_level_keys <= CODEX_FRONTMATTER_KEYS else "adapted"
            ),
            "detail_zh": "Codex 专用视图会保留正文与受支持语义字段。",
            "detail_en": "The Codex view preserves the body and supported semantic fields.",
            "target_name": portable_name,
        },
        "claude_code": {
            "label": "Claude Code",
            "status": (
                "ready" if valid_name and valid_description
                and top_level_keys <= CLAUDE_CODE_FRONTMATTER_KEYS else "adapted"
            ),
            "detail_zh": "保留 Claude Code 调用控制和工具权限字段。",
            "detail_en": "Preserves Claude Code invocation controls and tool permission fields.",
            "target_name": entry_name,
        },
        "cursor": {
            "label": "Cursor",
            "status": (
                "ready" if valid_name and name == entry_name
                and valid_description
                and top_level_keys <= CURSOR_FRONTMATTER_KEYS else "adapted"
            ),
            "detail_zh": "Cursor 视图保留路径范围和手动调用控制，并保证目录名与 name 一致。",
            "detail_en": (
                "Preserves path scoping and manual invocation controls while "
                "matching the folder name to name."
            ),
            "target_name": portable_name,
        },
        "cline": {
            "label": "Cline",
            "status": (
                "ready" if valid_name and name == entry_name
                and valid_description
                and top_level_keys <= CLINE_FRONTMATTER_KEYS else "adapted"
            ),
            "detail_zh": "Cline 视图仅保留必需的 name、description、正文与资源。",
            "detail_en": (
                "Keeps only the required name, description, body, and resources."
            ),
            "target_name": portable_name,
        },
        "opencode": {
            "label": "OpenCode",
            "status": (
                "ready" if valid_name and name == entry_name
                and valid_description
                and top_level_keys <= OPENCODE_FRONTMATTER_KEYS else "adapted"
            ),
            "detail_zh": "OpenCode 视图保留标准许可、兼容性和 metadata 字段。",
            "detail_en": (
                "Preserves the supported license, compatibility, and metadata fields."
            ),
            "target_name": portable_name,
        },
        "windsurf": {
            "label": "Windsurf",
            "status": (
                "ready" if valid_name and name == entry_name
                and valid_description
                and top_level_keys <= WINDSURF_FRONTMATTER_KEYS else "adapted"
            ),
            "detail_zh": "Windsurf 视图仅保留发现所需字段，正文与配套资源保持不变。",
            "detail_en": (
                "Keeps discovery fields only while preserving the body and resources."
            ),
            "target_name": portable_name,
        },
        "antigravity": {
            "label": "Antigravity",
            "status": (
                "ready" if valid_name and valid_description
                and top_level_keys <= ANTIGRAVITY_FRONTMATTER_KEYS else "adapted"
            ),
            "detail_zh": "全局目录使用 ~/.gemini/config/skills。",
            "detail_en": "Uses ~/.gemini/config/skills for user-level Skills.",
            "target_name": entry_name,
        },
        "gemini_cli": {
            "label": "Gemini CLI",
            "status": (
                "ready" if valid_name and valid_description
                and top_level_keys <= GEMINI_FRONTMATTER_KEYS else "adapted"
            ),
            "detail_zh": "发布为 ~/.gemini/skills/<name>/SKILL.md。",
            "detail_en": "Publishes to ~/.gemini/skills/<name>/SKILL.md.",
            "target_name": portable_name,
        },
        "vscode": {
            "label": "VS Code / Copilot",
            "status": (
                "ready" if valid_name and name == entry_name and valid_description
                else "adapted"
            ),
            "detail_zh": "VS Code 视图保证目录名与 name 完全一致。",
            "detail_en": "The VS Code view makes the folder name exactly match name.",
            "target_name": portable_name,
        },
        "claude_desktop": {
            "label": "Claude Desktop",
            "status": (
                "error" if package_bytes > 30 * 1024 * 1024
                or portable_name in {"anthropic", "claude"}
                else "ready" if valid_name and valid_description
                and top_level_keys <= CLAUDE_UPLOAD_FRONTMATTER_KEYS
                else "adapted"
            ),
            "detail_zh": "上传包仅发布 name、description、正文与资源。",
            "detail_en": "The upload package contains only name, description, body, and resources.",
            "target_name": portable_name,
        },
    }

    allowed_tools = parsed.get("allowed-tools") if isinstance(parsed, dict) else None
    if allowed_tools:
        if isinstance(allowed_tools, list):
            evidence = ", ".join(str(item) for item in allowed_tools[:12])
        else:
            evidence = str(allowed_tools)[:300]
        targets["claude_code"]["status"] = "warning"
        targets["claude_code"]["detail_zh"] = (
            f"调用时可能临时免确认授权工具：{evidence}"
        )
        targets["claude_code"]["detail_en"] = (
            f"May pre-approve tools for the invocation turn: {evidence}"
        )
        findings.append({
            "severity": "warning",
            "code": "claude_allowed_tools",
            "path": "SKILL.md",
            "message_en": (
                "Claude Code allowed-tools may pre-approve tools for the invocation "
                f"turn: {evidence}"
            ),
            "message_zh": (
                "Claude Code 的 allowed-tools 可能在调用轮次临时免确认授权工具："
                f"{evidence}"
            ),
        })

    for target_id, target in targets.items():
        if target["status"] in ("adapted", "error"):
            severity = "warning" if target["status"] == "error" else "info"
            findings.append({
                "severity": severity,
                "code": f"{target_id}_compatibility",
                "path": "SKILL.md",
                "message_en": (
                    f'{target["label"]}: {target["status"]}; {target["detail_en"]}'
                ),
                "message_zh": (
                    f'{target["label"]}：{target["status"]}；{target["detail_zh"]}'
                ),
            })
    return {
        "valid_frontmatter": has_frontmatter and bool(parsed),
        "source_name": name,
        "portable_name": portable_name,
        "targets": targets,
        "findings": findings,
    }
