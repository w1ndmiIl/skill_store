"""Conversation overview persistence, privacy, and concurrent-update contracts."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from skillhub.application.chat_sessions import ChatSessionService
from skillhub.infrastructure.session_repository import ChatSessionRepository
from skillhub.domain.conversation import session_metadata
from skillhub.presentation.api.chat import ChatApiMixin

ROOT = Path(__file__).resolve().parents[1]


class ConversationWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "sessions.json"
        self.repository = ChatSessionRepository(str(self.path))
        self.service = ChatSessionService(self.repository)

    def test_legacy_url_title_and_multiline_title_get_readable_overviews_without_writes(self):
        messages = [{"role": "user", "content": "https://github.com/example/skills/tree/main"}]
        self.service.save_session("url", messages[0]["content"][:30], messages)
        first = self.service.list_sessions()[0]
        self.assertEqual(first["title"], "example/skills")
        self.assertNotIn("https://", first["summary"])
        legacy = [{"id": "old", "title": "AI 会话接力与状态恢复\n当前这个skill"[:30], "messages": [
            {"role": "user", "content": "AI 会话接力与状态恢复\n当前这个skill 我想每次 ai 恢复进度"},
            {"role": "assistant", "content": "已整理恢复步骤，等待确认。", "run_status": "completed"}]}]
        legacy[0]["title"] = legacy[0]["messages"][0]["content"][:30]
        self.path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
        before = self.path.read_bytes()
        metadata = self.service.list_sessions()[0]
        self.assertEqual(metadata["title"], "AI 会话接力与状态恢复")
        self.assertIn("进展：", metadata["summary"])
        self.assertEqual(metadata["last_status"], "completed")
        self.assertEqual(self.path.read_bytes(), before)

    def test_manual_title_survives_message_save_and_new_repository(self):
        self.service.save_session("one", "", [{"role": "user", "content": "请修改 python Skill 的检查流程"}])
        renamed = self.service.update_metadata("one", "Python 检查流程")
        self.assertTrue(renamed["ok"])
        self.service.save_session("one", "", [{"role": "user", "content": "新的需求"}])
        reopened = ChatSessionService(ChatSessionRepository(str(self.path)))
        self.assertEqual(reopened.list_sessions()[0]["title"], "Python 检查流程")

    def test_ai_summary_persists_but_new_messages_refresh_local_progress(self):
        messages = [{"role": "user", "content": "更新 Skill"}]
        self.service.save_session("one", "", messages)
        version = self.service.load_session("one")["version"]
        result = self.service.update_metadata("one", "Skill 更新", "已确定修改目标，尚待写入审批。", version, source="ai")
        self.assertEqual(result["metadata"]["summary_source"], "ai")
        self.assertEqual(ChatSessionService(ChatSessionRepository(str(self.path))).list_sessions()[0]["summary"], "已确定修改目标，尚待写入审批。")
        self.service.save_session("one", "", [*messages, {"role":"assistant", "content":"修改已保存。"}])
        metadata = self.service.list_sessions()[0]
        self.assertEqual(metadata["title"], "Skill 更新")
        self.assertEqual(metadata["summary_source"], "local")
        self.assertIn("修改已保存", metadata["summary"])

    def test_stale_summary_does_not_replace_new_messages_or_metadata(self):
        self.service.save_session("one", "", [{"role":"user", "content":"First"}])
        version = self.service.load_session("one")["version"]
        self.service.save_session("one", "", [{"role":"user", "content":"New message"}])
        before = self.path.read_bytes()
        result = self.service.update_metadata("one", "Old", "Old summary", version, source="ai")
        self.assertTrue(result["conflict"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_summary_view_redacts_credentials_but_does_not_rewrite_messages(self):
        messages = [{"role":"user", "content":"API key: sk-testcredential123456 请更新 Skill"}]
        self.service.save_session("one", "", messages)
        metadata = self.service.list_sessions()[0]
        self.assertNotIn("sk-testcredential", json.dumps(metadata))
        self.assertEqual(self.service.load_session("one")["session"]["messages"], messages)

    def api(self):
        api = ChatApiMixin()
        api._chat_session_service = lambda: self.service
        api.deepseek_api_key = "fake-test-key"
        api.deepseek_model = "deepseek-flash"
        api.api_base = "https://api.deepseek.com/v1"
        api.language = "zh"
        return api

    def test_ai_summary_uses_sanitized_context_and_only_changes_metadata(self):
        messages = [{"role":"user", "content":"API key: sk-testcredential123456 请更新 Skill"}, {"role":"assistant", "content":"等待批准。"}]
        self.service.save_session("one", "", messages)
        response = mock.Mock(status_code=200)
        response.json.return_value = {"choices":[{"finish_reason":"stop", "message":{"content":json.dumps({"title":"Skill 更新", "summary":"已生成草案，等待批准。"}, ensure_ascii=False)}}]}
        with mock.patch("skillhub.presentation.api.chat.requests.post", return_value=response) as post:
            result = self.api().chat_summarize_session("one")
        self.assertTrue(result["ok"])
        self.assertNotIn("sk-testcredential", json.dumps(post.call_args.kwargs["json"]))
        self.assertEqual(post.call_args.kwargs["json"]["thinking"], {"type":"disabled"})
        self.assertEqual(self.service.load_session("one")["session"]["messages"], messages)

    def test_failed_ai_summary_preserves_record(self):
        self.service.save_session("one", "", [{"role":"user", "content":"修改 Skill"}])
        before = self.path.read_bytes()
        response = mock.Mock(status_code=200)
        response.json.return_value = {"choices":[{"message":{"content":"not JSON"}}]}
        with mock.patch("skillhub.presentation.api.chat.requests.post", return_value=response):
            self.assertIn("error", self.api().chat_summarize_session("one"))
        self.assertEqual(self.path.read_bytes(), before)

    def test_ai_summary_race_with_rename_is_rejected(self):
        self.service.save_session("one", "", [{"role":"user", "content":"修改 Skill"}])
        def request(*args, **kwargs):
            self.service.update_metadata("one", "用户指定的标题")
            response = mock.Mock(status_code=200)
            response.json.return_value = {"choices":[{"message":{"content":"{\"title\":\"AI 标题\",\"summary\":\"等待批准\"}"}}]}
            return response
        with mock.patch("skillhub.presentation.api.chat.requests.post", side_effect=request):
            self.assertTrue(self.api().chat_summarize_session("one")["conflict"])
        self.assertEqual(self.service.list_sessions()[0]["title"], "用户指定的标题")
