"""October audit regressions using disposable D-drive libraries and fake HTTP."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from main import Api
from agent_runtime import AgentMemoryStore, AgentRuntime, AgentTaskStore, OpenAICompatibleModel, RunRecorder, ToolDefinition, ModelCallError
from skillhub.infrastructure.config_repository import ConfigRepository
from skillhub.infrastructure.filesystem import FileHashCache, get_file_md5
from skillhub.presentation.api import library, project_sync

ROOT = Path(__file__).resolve().parents[1]


class AuditFixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.skills = self.root / "skills"
        self.project = self.root / "project"
        self.skills.mkdir()
        self.project.mkdir()
        self.api = Api.__new__(Api)
        self.api.skills_dir = str(self.skills)
        self.api.language = "zh"
        self.api.ai_import_optimization = False
        self.api.ai_display_translation = False
        self.api.projects = [{"name": "project", "path": str(self.project)}]
        self.api._remember_sync_result = lambda *args: None
        self.api._agent_memory = AgentMemoryStore(str(self.root / "memory.json"))
        backups = mock.patch("skillhub.presentation.api.agent_changes.AGENT_BACKUPS_DIR", str(self.root / "backups"))
        backups.start()
        self.addCleanup(backups.stop)
        self.api._codex_global_skill_state = lambda *args: {"global_target_states": []}
        self.api._global_target_state = lambda d, t, **kw: {"id": t, "enabled": False}

    def package(self, path, body="Original instructions"):
        path.mkdir(parents=True, exist_ok=True)
        (path / "SKILL.md").write_text(f"---\nname: {path.name}\ndescription: A demo Skill.\n---\n\n# Demo\n\n{body}\n", encoding="utf-8")

    def test_failed_delete_metadata_keeps_original(self):
        self.package(self.skills / "demo")
        with mock.patch.object(library, "atomic_write_json", side_effect=OSError("disk full")):
            result = self.api.delete_skill("demo")
        self.assertIn("error", result)
        self.assertTrue((self.skills / "demo" / "SKILL.md").exists())

    def test_failed_delete_rollback_retains_recoverable_trash(self):
        self.package(self.skills / "demo")
        real_move = library.shutil.move
        calls = []
        def move(a, b):
            calls.append((a, b))
            if len(calls) == 2:
                raise PermissionError("sharing violation")
            return real_move(a, b)
        with mock.patch.object(self.api, "_unregister_library_entry", side_effect=OSError("index failure")), \
             mock.patch.object(library.shutil, "move", side_effect=move):
            result = self.api.delete_skill("demo")
        self.assertFalse(result["rolled_back"])
        recovery = Path(result["recovery_path"])
        self.assertTrue((recovery / "demo" / "SKILL.md").exists())
        self.assertTrue((recovery / "metadata.json").exists())
        self.assertTrue((recovery / "rollback-metadata" / "recovery.json").exists())
        self.assertTrue(self.api.restore_deleted_skill(recovery.name)["ok"])

    def test_restore_failure_rolls_back_collection_metadata(self):
        self.package(self.skills / "alpha")
        self.package(self.skills / "beta")
        self.api._upsert_skill_collection("suite", ["alpha", "beta"])
        deleted = self.api.delete_skill("alpha")
        before = self.api._library_metadata_snapshot()
        with mock.patch.object(self.api, "_register_library_entry", side_effect=OSError("index failure")):
            result = self.api.restore_deleted_skill(deleted["trash_token"])
        self.assertTrue(result["rolled_back"])
        self.assertEqual(before, self.api._library_metadata_snapshot())
        self.assertFalse((self.skills / "alpha").exists())
        self.assertTrue(self.api.list_deleted_skills())

    def test_import_rejects_changed_staged_package_and_collection(self):
        for collection in (False, True):
            with self.subTest(collection=collection):
                source = self.root / ("collection" if collection else "single")
                if collection:
                    self.package(source / "skills" / "alpha")
                    self.package(source / "skills" / "beta")
                else:
                    self.package(source)
                preview = self.api.preview_skill_import(str(source))
                staged = Path(self.api._skill_import_paths()["pending"]) / preview["token"] / preview["adapted_relative"]
                entry = next(staged.rglob("SKILL.md"))
                entry.write_text("Changed after review", encoding="utf-8")
                result = self.api.apply_skill_import(preview["token"])
                self.assertTrue(result["requires_repreview"])
                self.assertFalse(any(p.name != ".skill-hub" for p in self.skills.iterdir()))

    def test_collection_failure_restores_all_metadata_and_assets(self):
        source = self.root / "source"
        self.package(source / "skills" / "alpha")
        self.package(source / "skills" / "beta")
        preview = self.api.preview_skill_import(str(source))
        before = self.api._library_metadata_snapshot()
        with mock.patch.object(self.api, "_upsert_skill_collection", side_effect=OSError("collection write failed")):
            result = self.api.apply_skill_import(preview["token"])
        self.assertTrue(result["rolled_back"])
        self.assertEqual(before, self.api._library_metadata_snapshot())
        self.assertFalse((self.skills / "alpha").exists())
        self.assertFalse((self.skills / "beta").exists())
        self.assertTrue(self.api.apply_skill_import(preview["token"])["ok"])

    def test_single_file_adoption_failure_preserves_exact_original(self):
        note = self.skills / "note.md"
        note.write_text("# Note\n\nOriginal\n", encoding="utf-8")
        preview = self.api.preview_skill_import(str(note), replace_active_name="note.md")
        before = note.read_bytes()
        with mock.patch.object(self.api, "_register_library_entry", side_effect=OSError("index failed")):
            result = self.api.apply_skill_import(preview["token"])
        self.assertTrue(result["rolled_back"])
        self.assertEqual(note.read_bytes(), before)

    def test_existing_import_target_change_requires_repreview(self):
        note = self.skills / "note.md"
        note.write_text("# Note\n", encoding="utf-8")
        preview = self.api.preview_skill_import(str(note), replace_active_name="note.md")
        note.write_text("External change", encoding="utf-8")
        self.assertTrue(self.api.apply_skill_import(preview["token"])["requires_repreview"])
        self.assertEqual(note.read_text(encoding="utf-8"), "External change")

    def apply_draft(self, name, content="Revised instructions"):
        draft = self.api._tool_draft_skill_change({"filename": name, "content": content, "summary": "Update Skill"})
        result = self.api._tool_apply_skill_change({"filename": draft["target_file"], "content": draft["content"],
            "expected_target_exists": draft["target_exists"], "expected_before_sha256": draft["before_sha256"],
            "expected_content_sha256": draft["content_sha256"], "reason": "Approved test change"})
        return draft, result

    def test_agent_updates_standard_package_without_flat_duplicate(self):
        self.package(self.skills / "demo")
        draft, result = self.apply_draft("demo")
        self.assertEqual(draft["change_type"], "modify")
        self.assertEqual(draft["target_file"], "demo")
        self.assertTrue(result["ok"])
        self.assertEqual((self.skills / "demo" / "SKILL.md").read_text(encoding="utf-8"), "Revised instructions")
        self.assertFalse((self.skills / "demo.md").exists())

    def test_agent_creates_standard_package_and_rejects_stale_review(self):
        draft, result = self.apply_draft("new-demo.md")
        self.assertTrue(result["ok"])
        self.assertEqual(draft["target_file"], "new-demo")
        self.assertIn("name: new-demo", (self.skills / "new-demo" / "SKILL.md").read_text(encoding="utf-8"))
        draft = self.api._tool_draft_skill_change({"filename": "new-demo", "content": "New edit", "summary": "edit"})
        target = self.skills / "new-demo" / "SKILL.md"
        target.write_text("External edit", encoding="utf-8")
        result = self.api._tool_apply_skill_change({"filename": draft["target_file"], "content": draft["content"],
            "expected_target_exists": True, "expected_before_sha256": draft["before_sha256"],
            "expected_content_sha256": draft["content_sha256"], "reason": "test"})
        self.assertIn("error", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "External edit")

    def test_standard_sync_status_uses_identical_resource_filters(self):
        self.package(self.skills / "demo")
        git = self.skills / "demo" / ".git"
        git.mkdir()
        (git / "config").write_text("Excluded", encoding="utf-8")
        preview = self.api.preview_sync(str(self.project), ["demo"])
        self.assertTrue(self.api.sync_skills(str(self.project), ["demo"], preview_token=preview["plan_token"])["ok"])
        self.assertEqual(self.api.get_project(str(self.project))["skills_status"]["demo"], "synced")

    def test_preview_does_not_hash_absent_disabled_packages(self):
        for i in range(30):
            self.package(self.skills / f"demo-{i}")
            (self.skills / f"demo-{i}" / "resource.md").write_text("resource", encoding="utf-8")
        with mock.patch.object(project_sync, "get_file_md5", wraps=project_sync.get_file_md5) as hash_file:
            self.api.preview_sync(str(self.project), ["demo-0"])
        self.assertEqual(hash_file.call_count, 2)
        self.assertTrue(all("demo-0" in call.args[0] for call in hash_file.call_args_list))

    def test_status_hash_and_metadata_cache_invalidate_on_edit(self):
        self.package(self.skills / "demo")
        entry = self.skills / "demo" / "SKILL.md"
        cache = FileHashCache()
        original = get_file_md5(str(entry), cache)
        self.api._collect_skills(include_global_state=False)
        with mock.patch.object(library, "parse_markdown_metadata", wraps=library.parse_markdown_metadata) as parse:
            self.api._collect_skills(include_global_state=False)
            self.assertEqual(parse.call_count, 0)
            entry.write_text("# Changed\n", encoding="utf-8")
            self.api._collect_skills(include_global_state=False)
            self.assertEqual(parse.call_count, 1)
        self.assertNotEqual(get_file_md5(str(entry), cache), original)

    def test_settings_directory_picker_can_stage_without_saving(self):
        self.api._window = mock.Mock()
        self.api._window.create_file_dialog.return_value = [str(self.root / "new-library")]
        with mock.patch.object(self.api, "save_settings") as save:
            result = self.api.change_skills_dir(False)
        save.assert_not_called()
        self.assertEqual(self.api.skills_dir, str(self.skills))
        self.assertEqual(result["skills_dir"], str(self.root / "new-library"))

    def test_connection_probe_uses_draft_without_committing_settings(self):
        self.api.deepseek_api_key = "fake-old-key"
        self.api.deepseek_model = "deepseek-flash"
        self.api.api_base = "https://api.deepseek.com/v1"
        response = mock.Mock(status_code=200)
        response.json.return_value = {"model": "draft-model", "choices": [{"message": {"tool_calls": [
            {"function": {"name": "connection_probe"}}]}}]}
        with mock.patch("skillhub.presentation.api.ai_provider.requests.post", return_value=response) as post, \
             mock.patch.object(self.api, "_commit_config") as commit:
            result = self.api.ai_test_connection({"api_key": "fake-draft-key", "model": "draft-model"})
        self.assertTrue(result["ok"])
        commit.assert_not_called()
        self.assertEqual(self.api.deepseek_model, "deepseek-flash")
        self.assertEqual(post.call_args.kwargs["json"]["thinking"], {"type": "disabled"})

    def test_official_model_migration_preserves_fields_and_backup(self):
        path = self.root / "config.json"
        before = {"skills_dir": str(self.skills), "deepseek_model": "deepseek-chat", "api_base": "https://api.deepseek.com/v1", "custom": "keep", "deepseek_api_key": "fake"}
        path.write_text(json.dumps(before), encoding="utf-8")
        repository = ConfigRepository(str(path), str(self.root), ("codex",))
        after = repository.load()
        self.assertEqual(after["deepseek_model"], "deepseek-flash")
        self.assertEqual(after["custom"], "keep")
        self.assertEqual(json.loads(Path(str(path) + ".bak").read_text(encoding="utf-8")), before)
        before["api_base"] = "https://gateway.example/v1"
        path.write_text(json.dumps(before), encoding="utf-8")
        self.assertEqual(repository.load()["deepseek_model"], "deepseek-chat")

    def runtime(self, request):
        model = OpenAICompatibleModel("fake", "deepseek-flash", "https://api.deepseek.com/v1", request_post=request, retry_delay=lambda s: None)
        tool = ToolDefinition("search_skills", "Search Skills", {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}, self.api._tool_search_skills)
        return AgentRuntime(model, [tool], AgentTaskStore(str(self.root / "tasks.json")), self.api._agent_memory, RunRecorder(str(self.root / "runs.jsonl")), max_steps=4)

    @staticmethod
    def response(message, finish="stop", status=200):
        result = mock.Mock(status_code=status)
        result.json.return_value = {"model": "deepseek-flash", "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}, "choices": [{"message": message, "finish_reason": finish}]}
        return result

    def test_deepseek_reasoning_survives_second_tool_request_and_restart(self):
        self.package(self.skills / "demo")
        requests = []
        reasoning = "Synthetic complete protocol field"
        def request(url, **kw):
            payload = kw["json"]
            requests.append(json.loads(json.dumps(payload)))
            self.assertEqual(payload["thinking"]["type"], "enabled")
            if len(requests) == 1:
                return self.response({"content": "", "reasoning_content": reasoning, "tool_calls": [{"id": "a", "function": {"name": "search_skills", "arguments": '{"query":"demo"}'}}]}, "tool_calls")
            self.assertEqual(next(m for m in payload["messages"] if m["role"] == "assistant")["reasoning_content"], reasoning)
            return self.response({"content": "Found demo", "reasoning_content": "Synthetic final field"})
        runtime = self.runtime(request)
        result = runtime.start("搜索 demo Skill")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["usage"]["total_tokens"], 26)
        saved = AgentTaskStore(str(self.root / "tasks.json")).load(result["run_id"])
        self.assertEqual(next(m for m in saved["messages"] if m["role"] == "assistant")["reasoning_content"], reasoning)
        self.assertNotIn(reasoning, json.dumps(result))
        self.assertNotIn(reasoning, (self.root / "runs.jsonl").read_text(encoding="utf-8"))

    def test_truncated_and_empty_model_responses_never_claim_completion(self):
        for finish, expected in (("length", "OutputTruncated"), ("stop", "EmptyModelResponse")):
            runtime = self.runtime(lambda *a, **kw: self.response({"content": "", "reasoning_content": "synthetic"}, finish))
            result = runtime.start("搜索 demo Skill")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error_type"], expected)

    def test_transient_model_failure_retries_but_generic_provider_gets_no_deepseek_parameters(self):
        failed = mock.Mock(status_code=429)
        request = mock.Mock(side_effect=[failed, self.response({"content": "OK"})])
        model = OpenAICompatibleModel("fake", "generic-model", "https://gateway.example/v1", request_post=request, retry_delay=lambda s: None)
        self.assertEqual(model.complete([], [])['content'], "OK")
        self.assertEqual(request.call_count, 2)
        self.assertNotIn("thinking", request.call_args.kwargs["json"])
        huge_tool = [{"description": "x" * 512000}]
        with self.assertRaises(ModelCallError):
            model.complete([], huge_tool)
        self.assertEqual(request.call_count, 2)
