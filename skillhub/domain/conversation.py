"""Readable conversation metadata without changing or sending message bodies."""
import hashlib
import json
import re
from urllib.parse import urlparse

PLACEHOLDERS = {"", "新会话", "未命名会话", "New Chat", "Untitled Chat"}
SECRET = re.compile(r"sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+|(?:api[_ -]?key|password|token|secret)\s*[:=]\s*[^\s,;]+", re.I)
STATUSES = {"completed", "failed", "cancelled", "refused", "rejected", "max_steps", "waiting_approval", "running"}


def plain_text(value, limit=240):
    value = SECRET.sub("[redacted]", str(value or "")[:12000])
    value = re.sub(r"```[\s\S]*?```", " ", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    def shorten_url(match):
        url = urlparse(match.group(0).rstrip(".,，。)"))
        parts = [part for part in url.path.split("/") if part]
        return "/".join(parts[:2]) if url.hostname == "github.com" and len(parts) >= 2 else (url.hostname or "链接")
    value = re.sub(r"https?://[^\s<>]+", shorten_url, value)
    value = re.sub(r"^[\s>#*\-]+", "", value)
    value = re.sub(r"[`*_#]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit].rstrip() + ("…" if len(value) > limit else "")


def local_title(messages, language="zh"):
    first = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    lines = [line.strip() for line in first.splitlines() if line.strip()]
    line = next((line for line in lines if not re.fullmatch(r"https?://\S+", line)), "")
    if not line and lines:
        return plain_text(lines[0], 40)
    title = plain_text(line, 40)
    title = re.sub(r"^(?:请帮我|帮我|请你|请)\s*", "", title)
    return title or ("新会话" if language == "zh" else "New Chat")


def session_metadata(session, language="zh"):
    messages = session.get("messages", [])
    first = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    old_title = session.get("title", "")
    source = session.get("title_source")
    if source not in ("auto", "manual", "ai"):
        source = "auto" if old_title in PLACEHOLDERS or old_title == first[:30] else "manual"
    title = local_title(messages, language) if source == "auto" else plain_text(old_title, 60)
    assistant = next((m for m in reversed(messages) if m.get("role") == "assistant" and m.get("content")), {})
    request = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    ai_current = session.get("summary_source") == "ai" and session.get("summary_message_count") == len(messages)
    if ai_current:
        summary = plain_text(session.get("summary", ""), 240)
    else:
        goal = plain_text(request, 100)
        progress = plain_text(assistant.get("content", ""), 130)
        summary = ("需求：" if language == "zh" else "Goal: ") + goal if goal else ""
        if progress:
            summary += (" · 进展：" if language == "zh" else " · Progress: ") + progress
        summary = summary[:240]
    status = assistant.get("run_status", "")
    return {"id": session["id"], "title": title, "title_source": source,
            "summary": summary, "summary_source": "ai" if ai_current else "local",
            "preview": plain_text(assistant.get("content") or request, 110),
            "created_at": session.get("created_at", ""),
            "updated_at": session.get("updated_at", session.get("created_at", "")),
            "msg_count": len(messages), "last_status": status if status in STATUSES else ""}


def session_version(session):
    data = {key: session.get(key) for key in ("id", "messages", "title", "title_source", "summary", "summary_source")}
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
