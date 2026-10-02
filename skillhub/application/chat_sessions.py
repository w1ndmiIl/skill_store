"""Chat-session use cases independent of the PyWebView bridge."""

import time
from contextlib import nullcontext
from collections.abc import Callable
from typing import Protocol
from skillhub.domain.conversation import session_metadata, session_version, PLACEHOLDERS


class SessionRepository(Protocol):
    """Persistence port required by the chat-session application service."""

    def load(self) -> list: ...

    def save(self, sessions: list) -> bool: ...


class ChatSessionService:
    """Create, query, and delete persisted chat sessions."""

    def __init__(
        self,
        repository: SessionRepository,
        language: str = "zh",
        clock: Callable[[], str] | None = None,
    ):
        self.repository = repository
        self.language = language
        self.clock = clock or (lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))

    def list_sessions(self) -> list:
        if hasattr(self.repository, "summaries"):
            return self.repository.summaries(self.language)
        sessions = sorted(
            self.repository.load(),
            key=lambda session: session.get(
                "updated_at",
                session.get("created_at", ""),
            ),
            reverse=True,
        )
        return [session_metadata(session, self.language) for session in sessions]

    def load_session(self, session_id: str) -> dict:
        if hasattr(self.repository, "session"):
            session = self.repository.session(session_id)
            return self._loaded_session(session) if session else {"error": "Session not found"}
        for session in self.repository.load():
            if session["id"] == session_id:
                return self._loaded_session(session)
        return {"error": "Session not found"}

    def _loaded_session(self, session):
        return {"session": session, "metadata": session_metadata(session, self.language), "version": session_version(session)}

    def save_session(self, session_id: str, title: str, messages: list) -> dict:
        transaction = getattr(self.repository, "transaction", nullcontext)
        try:
            with transaction():
                return self._save_session(session_id, title, messages)
        except (OSError, ValueError) as error:
            return {"error": str(error)}

    def _save_session(self, session_id: str, title: str, messages: list) -> dict:
        sessions = self.repository.load()
        now = self.clock()
        for session in sessions:
            if session["id"] == session_id:
                first = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
                if title and title not in PLACEHOLDERS and title != first[:30] and title != session.get("title"):
                    session.update(title=title, title_source="manual")
                # An ordinary message save must not undo a manual or AI title.
                if session_metadata(session, self.language)["title_source"] == "auto":
                    session["title_source"] = "auto"
                run_ids = {m.get("run_id") for m in messages if m.get("run_id")}
                completed = [m for m in session["messages"] if m.get("run_id") and m["run_id"] not in run_ids]
                session["messages"] = [*messages, *completed]
                session["updated_at"] = now
                break
        else:
            first = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
            session = {
                "id": session_id,
                "title": title or (
                    "新会话" if self.language == "zh" else "New Chat"
                ),
                "created_at": now,
                "updated_at": now,
                "messages": messages,
                "title_source": "auto" if title in PLACEHOLDERS or title == first[:30] else "manual",
            }
            sessions.append(session)
        metadata = session_metadata(session, self.language)
        session.update({key: metadata[key] for key in ("title", "title_source", "summary", "summary_source")})
        session["summary_message_count"] = len(session["messages"])
        if not self.repository.save(sessions):
            return {"error": "Failed to save chat session"}
        return {"ok": True, "id": session_id, "metadata": metadata}

    def update_metadata(self, session_id, title, summary=None, expected_version=None, source="manual"):
        if not isinstance(title, str) or not title.strip() or len(title) > 60:
            return {"error": "Title must contain 1–60 characters"}
        if summary is not None and (not isinstance(summary, str) or len(summary) > 240):
            return {"error": "Summary accepts at most 240 characters"}
        transaction = getattr(self.repository, "transaction", nullcontext)
        try:
            with transaction():
                sessions = self.repository.load()
                session = next((s for s in sessions if s["id"] == session_id), None)
                if session is None:
                    return {"error": "Session not found"}
                if expected_version is not None and session_version(session) != expected_version:
                    return {"error": "会话内容已变化，请重新生成摘要 / Conversation changed; regenerate the summary", "conflict": True}
                session.update(title=title.strip(), title_source=source)
                if summary is not None:
                    session.update(summary=summary, summary_source="ai", summary_message_count=len(session["messages"]))
                if not self.repository.save(sessions):
                    return {"error": "Failed to save conversation metadata"}
                return {"ok": True, "metadata": session_metadata(session, self.language)}
        except (OSError, ValueError) as error:
            return {"error": str(error)}

    def delete_session(self, session_id: str) -> dict:
        transaction = getattr(self.repository, "transaction", nullcontext)
        try:
            with transaction():
                return self._delete_session(session_id)
        except (OSError, ValueError) as error:
            return {"error": str(error)}

    def _delete_session(self, session_id: str) -> dict:
        sessions = [
            session
            for session in self.repository.load()
            if session["id"] != session_id
        ]
        if not self.repository.save(sessions):
            return {"error": "Failed to delete chat session"}
        return {"ok": True}
