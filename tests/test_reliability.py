"""Regressions for the September audit, using only isolated storage."""
import concurrent.futures
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from skillhub.application.chat_sessions import ChatSessionService
from skillhub.infrastructure.session_repository import ChatSessionRepository
from skillhub.infrastructure.config_repository import ConfigRepository
from skillhub.infrastructure.background_jobs import BackgroundJobs
from skillhub.presentation.api.configuration import ConfigurationApiMixin
from skillhub.presentation.api.skill_editor import SkillEditorApiMixin
from skillhub.presentation.api.library import LibraryApiMixin
from skillhub.presentation.api.trash import TrashApiMixin
from skillhub.presentation.api.background_agent import BackgroundAgentApiMixin
from agent_runtime import AgentRuntime, AgentTaskStore, AgentMemoryStore, RunRecorder, ToolDefinition

ROOT=Path(__file__).resolve().parents[1]
class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
    def repository(self): return ChatSessionRepository(str(self.root/'sessions.json'))
    def test_concurrent_sessions_are_all_preserved(self):
        def save(i):
            return ChatSessionService(self.repository()).save_session(str(i),str(i),[{'role':'user','content':str(i)}])
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(save,range(32)))
        self.assertTrue(all(r.get('ok') for r in results))
        self.assertEqual(len(self.repository().load()),32)
    def test_corrupt_history_is_not_overwritten_and_can_recover(self):
        repo=self.repository();service=ChatSessionService(repo)
        service.save_session('a','A',[{'role':'user','content':'first'}])
        service.save_session('b','B',[])
        Path(repo.path).write_text('[{"id":',encoding='utf-8')
        with self.assertRaises(OSError):service.list_sessions()
        self.assertIn('error',service.save_session('c','C',[]))
        self.assertEqual(Path(repo.path).read_text(),'[{"id":')
        repo.recover();self.assertEqual(repo.load()[0]['id'],'a')
        self.assertEqual(len(list(self.root.glob('sessions.json.damaged-*'))),1)
    def test_bad_history_schema_is_not_silently_replaced(self):
        path=Path(self.repository().path);path.write_text('[{"messages": []}]')
        self.assertFalse(self.repository().save([]))
        self.assertEqual(path.read_text(),'[{"messages": []}]')
    def config_api(self):
        class Config(ConfigurationApiMixin):
            def _configured_global_target_ids(self):return self.global_skill_targets
            def _global_skill_target_options(self):return []
            def _normalize_global_skill_targets(self,targets):return targets
        api=Config();api.skills_dir=str(self.root/'skills');api.projects=[];api.language='zh';api.theme='light'
        api.default_scan_dir=str(self.root);api.deepseek_api_key='fake-key';api.deepseek_model='model';api.api_base='https://example.invalid/v1'
        api.ai_import_optimization=False;api.ai_display_translation=False;api.global_skill_targets=['codex']
        repo=ConfigRepository(str(self.root/'config.json'),str(self.root),('codex',))
        api._config_repository=lambda:repo
        return api,repo
    def test_failed_config_write_leaves_memory_and_disk_unchanged(self):
        api,repo=self.config_api();self.assertTrue(api._save_config());old=Path(repo.config_path).read_bytes()
        with mock.patch.object(repo,'save',return_value=False):
            result=api.save_ai_config('new-key')
        self.assertIn('error',result);self.assertEqual(api.deepseek_api_key,'fake-key');self.assertEqual(Path(repo.config_path).read_bytes(),old)
    def test_rejected_settings_do_not_publish_partial_values(self):
        api,_=self.config_api();r=api.save_settings({'theme':'dark','global_skill_targets':[]})
        self.assertIn('error',r);self.assertEqual(api.theme,'light')
    def test_explicit_key_clear_is_persisted(self):
        api,repo=self.config_api();r=api.save_ai_config('',clear_key=True)
        self.assertTrue(r['ok']);self.assertEqual(repo.load()['deepseek_api_key'],'')
    def test_corrupt_configuration_blocks_save(self):
        api,repo=self.config_api();Path(repo.config_path).write_text('{')
        self.assertIn('error',api.save_settings({'theme':'dark'}));self.assertEqual(Path(repo.config_path).read_text(),'{')
    def editor(self):
        class Editor(SkillEditorApiMixin,LibraryApiMixin):
            def _resolve_virtual_skill(self,filename):return {}
            def _register_library_entry(self,*args,**kwargs):pass
        api=Editor();api.skills_dir=str(self.root);api.language='zh'
        package=self.root/'demo';package.mkdir();(package/'SKILL.md').write_text('---\nname: demo\ndescription: example\n---\nOriginal')
        return api,package
    def test_editor_rejects_external_content_change_and_keeps_both_versions(self):
        api,p=self.editor();loaded=api.get_skill_editor_data('demo');(p/'SKILL.md').write_text('External')
        r=api.save_skill_editor_data('demo',{'skill_content':'Draft','expected_version':loaded['version']})
        self.assertTrue(r['conflict']);self.assertEqual((p/'SKILL.md').read_text(),'External');self.assertEqual(r['current']['skill_content'],'External')
    def test_editor_rejects_new_metadata_file(self):
        api,p=self.editor();loaded=api.get_skill_editor_data('demo');(p/'agents').mkdir();(p/'agents'/'openai.yaml').write_text('interface: {}')
        r=api.save_skill_editor_data('demo',{'skill_content':'Draft','expected_version':loaded['version']})
        self.assertTrue(r['conflict']);self.assertIn('Original',(p/'SKILL.md').read_text())
    def test_editor_accepts_reviewed_current_version(self):
        api,p=self.editor();loaded=api.get_skill_editor_data('demo')
        r=api.save_skill_editor_data('demo',{'skill_content':'Draft','expected_version':loaded['version']})
        self.assertTrue(r['ok']);self.assertEqual((p/'SKILL.md').read_text(),'Draft')
    def test_task_store_concurrent_updates_are_preserved(self):
        path=str(self.root/'tasks.json')
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(lambda i:AgentTaskStore(path).save({'run_id':str(i)}),range(20)))
        self.assertEqual(len(AgentTaskStore(path).list_public()),20)
    def test_cancel_after_model_return_prevents_tool_execution(self):
        calls=[];event=threading.Event()
        class Model:
            def complete(self,messages,tools):
                event.set();return {'tool_calls':[{'id':'x','function':{'name':'search_skills','arguments':'{}'}}]}
        runtime=AgentRuntime(Model(),[ToolDefinition('search_skills','Search',{'type':'object'},lambda a:calls.append(a) or {'ok':True})],
            AgentTaskStore(str(self.root/'tasks.json')),AgentMemoryStore(str(self.root/'memory.json')),RunRecorder(str(self.root/'runs.jsonl')))
        runtime.cancel_requested=event.is_set
        result=runtime.start('Search skills',session_id='a')
        self.assertEqual(result['status'],'cancelled');self.assertEqual(result['session_id'],'a');self.assertEqual(calls,[])
    def test_duplicate_background_operation_is_rejected(self):
        jobs=BackgroundJobs();gate=threading.Event();entered=threading.Event()
        def task(cancel):entered.set();gate.wait(3)
        jobs.submit('a',task);self.assertTrue(entered.wait(1))
        self.assertIn('error',jobs.submit('a',task));jobs.cancel('a');self.assertTrue(jobs.status('a')['stop_requested'])
        gate.set();jobs.jobs['a']['thread'].join(3)
    def test_backend_completion_keeps_owning_chat_and_survives_stale_ui_save(self):
        repo=self.repository();service=ChatSessionService(repo);service.save_session('a','A',[{'role':'user','content':'A'}]);service.save_session('b','B',[])
        api=BackgroundAgentApiMixin();api._session_repository=lambda:repo;api._chat_session_service=lambda:service
        result={'session_id':'a','run_id':'run-a','final_answer':'Answer A'}
        api._finish_agent_result(result);api._finish_agent_result(result)
        service.save_session('a','A',[{'role':'user','content':'A'}])
        self.assertEqual(len(service.load_session('a')['session']['messages']),2)
        self.assertEqual(service.load_session('b')['session']['messages'],[])
    def test_trash_listing_survives_restart_and_purge_requires_current_preview(self):
        token='a'*32;path=self.root/'.skill-hub'/'trash'/token;path.mkdir(parents=True)
        (path/'metadata.json').write_text(json.dumps({'filename':'demo.md','deleted_at':'2026-09-12'}));(path/'demo.md').write_text('deleted')
        api=TrashApiMixin();api.skills_dir=str(self.root)
        self.assertEqual(api.list_deleted_skills()[0]['filename'],'demo.md')
        preview=api.preview_purge_trash([token]);(self.root/'demo.md').write_text('existing')
        self.assertIn('error',api.purge_trash([token],preview['token']));self.assertTrue(path.exists())
        fresh=api.preview_purge_trash([token]);self.assertTrue(api.purge_trash([token],fresh['token'])['ok']);self.assertEqual((self.root/'demo.md').read_text(),'existing')

    def test_summary_query_does_not_load_or_copy_all_message_bodies(self):
        repo=self.repository();service=ChatSessionService(repo)
        service.save_session('a','A',[{'role':'user','content':'long text'*1000}])
        with mock.patch.object(repo,'load',side_effect=AssertionError('full history loaded')):
            self.assertEqual(service.list_sessions()[0]['msg_count'],1)
            self.assertEqual(service.load_session('a')['session']['id'],'a')
    def test_corrupt_memory_is_preserved_and_mutations_are_blocked(self):
        path=self.root/'memory.json';path.write_text('{')
        store=AgentMemoryStore(str(path));self.assertTrue(store._load_error)
        with self.assertRaises(OSError):store.clear()
        self.assertEqual(path.read_text(),'{')
    def test_memory_updates_and_clear_share_a_transaction(self):
        path=str(self.root/'memory.json')
        def remember(i):return AgentMemoryStore(path).remember('preference','Preference '+str(i))
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:list(pool.map(remember,range(20)))
        self.assertEqual(len(AgentMemoryStore(path).public_view()['preferences']),20)

    def test_memory_failure_keeps_the_last_persisted_in_memory_state(self):
        store=AgentMemoryStore(str(self.root/'memory.json'));store.set_enabled(True)
        with mock.patch('agent_runtime.write_json',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):store.set_enabled(False)
        self.assertTrue(store.enabled)
    def test_window_close_waits_for_a_background_operation(self):
        api=BackgroundAgentApiMixin();api._background_jobs=BackgroundJobs();api._window=mock.Mock()
        entered=threading.Event();release=threading.Event()
        def task(cancel):entered.set();release.wait(3)
        api._background_jobs.submit('a',task);self.assertTrue(entered.wait(1))
        self.assertFalse(api.can_close_window());api._window.evaluate_js.assert_called_once()
        release.set();api._background_jobs.jobs['a']['thread'].join(3);self.assertTrue(api.can_close_window())

    def test_editor_draft_survives_new_api_and_is_scoped_to_library(self):
        from skillhub.presentation.api.workspace_state import WorkspaceStateApiMixin
        with mock.patch('skillhub.presentation.api.workspace_state.USER_DATA_DIR',str(self.root)):
            first=WorkspaceStateApiMixin();first.skills_dir=str(self.root/'a')
            draft={'snapshot':{'skillContent':'unsaved','openaiYaml':'','category':'','openaiForm':{}},'version':{},'at':1}
            self.assertTrue(first.save_editor_draft('demo',draft)['ok'])
            second=WorkspaceStateApiMixin();second.skills_dir=first.skills_dir
            self.assertEqual(second.load_editor_draft('demo')['draft']['snapshot']['skillContent'],'unsaved')
            second.skills_dir=str(self.root/'b');self.assertIsNone(second.load_editor_draft('demo')['draft'])
            first.clear_editor_draft('demo');self.assertIsNone(first.load_editor_draft('demo')['draft'])
    def test_sync_result_persists_a_bounded_text_diff(self):
        from skillhub.presentation.api.workspace_state import WorkspaceStateApiMixin
        backup=self.root/'backup';backup.mkdir();(backup/'old').write_text('before\n')
        project=self.root/'project';project.mkdir();(project/'demo.md').write_text('after\n')
        with mock.patch('skillhub.presentation.api.workspace_state.USER_DATA_DIR',str(self.root)):
            api=WorkspaceStateApiMixin()
            api._remember_sync_result(str(project),{'summary':{'modify':1},'changes':[{'path':'demo.md','action':'modify'}]}, {'id':'x','created_at':'now','changes':[{'path':'demo.md','backup':'old'}]},str(backup))
            report=WorkspaceStateApiMixin().get_last_sync_result()['report']
            self.assertIn('-before',report['changes'][0]['diff']);self.assertIn('+after',report['changes'][0]['diff'])
