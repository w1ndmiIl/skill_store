"""Project rules require manual saves or explicit one-shot AI drafting consent."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from main import Api

ROOT=Path(__file__).resolve().parents[1]
class ProjectRulesEditorTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.project=self.root/'project';self.project.mkdir();self.path=self.project/'AGENTS.md'
        self.api=Api.__new__(Api);self.api.projects=[{'path':str(self.project),'name':'project'}]
        self.api.skills_dir=str(self.project);self.api.language='zh';self.api.deepseek_api_key='fake-key';self.api.deepseek_model='fake-model';self.api.api_base='https://example.invalid/v1'
        self.patch=mock.patch('skillhub.presentation.api.project_rules_editor.USER_DATA_DIR',str(self.root/'data'));self.patch.start();self.addCleanup(self.patch.stop)
    def seed(self,content='# Original'):
        self.path.write_text(content,encoding='utf-8');return self.api.get_project_rules_editor_data(str(self.project))
    def authorize(self,before):
        return self.api.authorize_project_rules_ai(str(self.project),before['content'],'Change the heading',before['version'])['token']
    def response(self,content):
        r=mock.Mock(status_code=200);r.json.return_value={'choices':[{'message':{'content':content}}]};return r
    def test_manual_save_is_version_checked_and_preserves_a_backup(self):
        before=self.seed();result=self.api.save_project_rules(str(self.project),'# Manual',before['version'])
        self.assertTrue(result['ok']);self.assertEqual(self.path.read_text(),'# Manual')
        backup=list((self.root/'data'/'project-rules-backups').glob('*.md'));self.assertEqual(len(backup),1);self.assertEqual(backup[0].read_text(),'# Original')
    def test_manual_save_refuses_external_changes(self):
        before=self.seed();self.path.write_text('# External')
        r=self.api.save_project_rules(str(self.project),'# Draft',before['version'])
        self.assertTrue(r['conflict']);self.assertEqual(self.path.read_text(),'# External')
    def test_reading_missing_rules_does_not_create_but_manual_save_can(self):
        r=self.api.get_project_rules_editor_data(str(self.project));self.assertFalse(r['exists']);self.assertFalse(self.path.exists())
        self.assertTrue(self.api.save_project_rules(str(self.project),'# Created manually',r['version'])['ok'])
    def test_automatic_optimization_never_calls_the_model_for_agents(self):
        before=self.seed()
        with mock.patch('skillhub.presentation.api.import_candidates.requests.post') as post:
            r=self.api._ai_optimize_import_entry(str(self.path),'markdown','AGENTS.md')
        self.assertTrue(r['protected']);post.assert_not_called();self.assertEqual(self.path.read_bytes().decode('utf-8'),before['content'])
    def test_generic_ai_write_and_generation_paths_reject_agents(self):
        self.seed()
        self.assertIn('error',self.api._tool_draft_skill_change({'filename':'AGENTS.md'}))
        self.assertIn('error',self.api._tool_apply_skill_change({'filename':'agents.md'}))
        self.assertIn('error',self.api.ai_save_skill({'filename':'AGENTS.md','content':'changed'}))
        self.assertEqual(self.path.read_text(),'# Original')
    def test_ai_draft_requires_authorization_and_never_writes(self):
        before=self.seed()
        with mock.patch('skillhub.presentation.api.project_rules_editor.requests.post',return_value=self.response('# Suggested')) as post:
            self.assertIn('error',self.api.draft_project_rules_ai('invented'));post.assert_not_called()
            token=self.authorize(before);r=self.api.draft_project_rules_ai(token)
            self.assertEqual(r['content'],'# Suggested');self.assertTrue(r['requires_manual_save']);self.assertEqual(self.path.read_text(),'# Original')
            self.assertIn('error',self.api.draft_project_rules_ai(token));self.assertEqual(post.call_count,1)
    def test_stale_and_expired_authorizations_are_rejected_before_network(self):
        before=self.seed();token=self.authorize(before);self.path.write_text('# External')
        with mock.patch('skillhub.presentation.api.project_rules_editor.requests.post') as post:
            self.assertIn('error',self.api.draft_project_rules_ai(token));post.assert_not_called()
        before=self.api.get_project_rules_editor_data(str(self.project));token=self.authorize(before)
        self.api._rules_ai_grants[token]['created']-=601
        with mock.patch('skillhub.presentation.api.project_rules_editor.requests.post') as post:
            self.assertIn('error',self.api.draft_project_rules_ai(token));post.assert_not_called()
    def test_ai_cannot_change_the_managed_index(self):
        before=self.seed('# Rules\n<!-- AI_SKILL_HUB:START -->index<!-- AI_SKILL_HUB:END -->')
        with mock.patch('skillhub.presentation.api.project_rules_editor.requests.post',return_value=self.response('# Changed')):
            r=self.api.draft_project_rules_ai(self.authorize(before))
        self.assertIn('error',r);self.assertEqual(self.path.read_bytes().decode('utf-8'),before['content'])
    def test_editor_endpoints_are_not_available_as_autonomous_agent_tools(self):
        tools={t.name for t in self.api._agent_tools()}
        self.assertFalse(tools & {'save_project_rules','authorize_project_rules_ai','draft_project_rules_ai'})
