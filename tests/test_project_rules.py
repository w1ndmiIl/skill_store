"""Project-root rules stay outside the shared Skill library and sync selection."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from main import Api

ROOT=Path(__file__).resolve().parents[1]
class ProjectRulesTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.library=self.root/'library';self.library.mkdir()
        self.project=self.root/'project';self.project.mkdir()
        self.other=self.root/'other';self.other.mkdir()
        self.api=Api.__new__(Api);self.api.language='zh';self.api.skills_dir=str(self.library)
        self.api.projects=[{'name':'Project','path':str(self.project)},{'name':'Other','path':str(self.other)}]
        self.api._load_skill_collections=lambda:{'collections':[]}
        self.api._load_display_localizations=lambda:{}
        self.api._codex_global_skill_state=lambda *args,**kwargs:{}
    def test_rules_are_project_metadata_not_global_or_enabled_skills(self):
        (self.project/'AGENTS.md').write_text('# Project rules',encoding='utf-8')
        entry=self.api.get_project(str(self.project));rules=entry['project_rules']
        self.assertEqual(rules['title'],'AGENTS.md');self.assertTrue(rules['available'])
        self.assertEqual(rules['description'],'当前项目的固定开发规约')
        self.assertEqual(self.api.get_skills(),[])
        self.assertNotIn(rules['filename'],entry['skills_status'])
        self.assertNotIn(rules['filename'],entry.get('enabled_skills') or [])
        self.assertEqual(self.api.get_project_rules_content(str(self.project))['content'],'# Project rules')
    def test_missing_rules_show_a_placeholder_without_creating_a_file(self):
        entry=self.api.get_project(str(self.project));self.assertFalse(entry['project_rules']['available'])
        result=self.api.get_project_rules_content(str(self.project));self.assertTrue(result['missing'])
        self.assertIn('尚未创建',result['content']);self.assertFalse((self.project/'AGENTS.md').exists())
    def test_rules_are_scoped_to_the_selected_registered_project(self):
        (self.project/'AGENTS.md').write_text('Project A',encoding='utf-8')
        (self.other/'AGENTS.md').write_text('Project B',encoding='utf-8')
        nested=self.project/'.agent'/'skills';nested.mkdir(parents=True)
        (nested/'AGENTS.md').write_text('Nested skill',encoding='utf-8')
        self.assertEqual(self.api.get_project_rules_content(str(self.project))['content'],'Project A')
        self.assertEqual(self.api.get_project_rules_content(str(self.other))['content'],'Project B')
        self.assertIn('error',self.api.get_project_rules_content(str(self.root)))
    def test_rules_reader_does_not_scan_the_library(self):
        (self.project/'AGENTS.md').write_text('Rules',encoding='utf-8')
        with mock.patch.object(self.api,'_collect_skills',side_effect=AssertionError('Unneeded scan')):
            self.assertEqual(self.api.get_project_rules_content(str(self.project))['content'],'Rules')
    def test_rules_cannot_follow_a_link_outside_the_project(self):
        outside=self.root/'outside.md';outside.write_text('private',encoding='utf-8')
        try:os.symlink(outside,self.project/'AGENTS.md')
        except OSError:self.skipTest('Symlinks unavailable')
        self.assertIn('error',self.api.get_project_rules_content(str(self.project)))
