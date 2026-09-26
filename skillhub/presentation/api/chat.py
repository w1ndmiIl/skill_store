"""Chat session bridge endpoints."""

from skillhub.application.chat_sessions import ChatSessionService
from skillhub.infrastructure.session_repository import ChatSessionRepository
from skillhub.settings import CHAT_SESSIONS_PATH


class ChatApiMixin:
    """Delegate session persistence to the chat application service."""

    @property
    def _sessions_path(self):
        return CHAT_SESSIONS_PATH

    def _session_repository(self) -> ChatSessionRepository:
        return ChatSessionRepository(self._sessions_path)

    def _chat_session_service(self) -> ChatSessionService:
        return ChatSessionService(
            self._session_repository(),
            language=self.language,
        )

    def _load_sessions(self):
        return self._session_repository().load()

    def _save_sessions(self, sessions):
        return self._session_repository().save(sessions)

    def chat_recover_sessions(self):
        try:
            return self._session_repository().recover()
        except OSError as error:
            return {"error": str(error)}

    def chat_list_sessions(self):
        """Return session list without full messages (just id/title/time)."""
        return self._chat_session_service().list_sessions()

    def chat_load_session(self, session_id):
        """Load a single session with full messages."""
        return self._chat_session_service().load_session(session_id)

    def chat_save_session(self, session_id, title, messages):
        """Create or update a session."""
        return self._chat_session_service().save_session(
            session_id,
            title,
            messages,
        )

    def chat_delete_session(self, session_id):
        """Delete a session by id."""
        return self._chat_session_service().delete_session(session_id)
