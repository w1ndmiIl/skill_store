"""Bound scan cost while preserving sync and project read contracts."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from main import Api
from skillhub.presentation.api import library


ROOT = Path(__file__).resolve().parents[1]


class PerformanceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.skills = self.root / "skills"
        self.project = self.root / "project"
        self.other = self.root / "other"
        for directory in (self.skills, self.project, self.other):
            directory.mkdir()
        for index in range(20):
            (self.skills / f"skill-{index}.md").write_text(
                f"---\ntitle: Skill {index}\ndescription: Example {index}\n---\n# Example\n",
                encoding="utf-8",
            )
        # Avoid touching the user's configuration, library, or global targets.
        self.api = Api.__new__(Api)
        self.api.skills_dir = str(self.skills)
        self.api.language = "en"
        self.api.projects = [
            {"name": "project", "path": str(self.project)},
            {"name": "other", "path": str(self.other)},
        ]
        for name, value in (
            ("_load_skill_collections", {"collections": []}),
            ("_load_display_localizations", {}),
            ("_codex_global_skill_state", {}),
        ):
            patcher = mock.patch.object(self.api, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_preview_scans_metadata_once_and_checks_only_selected_global_state(self):
        with (
            mock.patch.object(self.api, "_collect_skills", wraps=self.api._collect_skills) as collect,
            mock.patch.object(library, "parse_markdown_metadata", wraps=library.parse_markdown_metadata) as parse,
        ):
            preview = self.api.preview_sync(str(self.project), ["skill-0.md"])
        self.assertTrue(preview["ok"])
        collect.assert_called_once_with(include_global_state=False)
        self.assertEqual(parse.call_count, 20)
        self.api._codex_global_skill_state.assert_called_once_with("skill-0.md")
        self.assertEqual(preview["summary"]["add"], 2)  # Skill plus AGENTS index

    def test_metadata_only_search_keeps_results_and_avoids_deployment_inspection(self):
        result = self.api._tool_search_skills({"query": "Example 19", "limit": 1})
        self.assertEqual([item["filename"] for item in result["results"]], ["skill-19.md"])
        self.api._codex_global_skill_state.assert_not_called()

    def test_source_edit_after_preview_requires_new_confirmation_without_writing(self):
        preview = self.api.preview_sync(str(self.project), ["skill-0.md"])
        (self.skills / "skill-0.md").write_text("# Changed source\n", encoding="utf-8")
        result = self.api.sync_skills(
            str(self.project), ["skill-0.md"], preview_token=preview["plan_token"]
        )
        self.assertTrue(result["plan_changed"])
        self.assertTrue(result["requires_confirmation"])
        self.assertFalse((self.project / "AGENTS.md").exists())
        self.assertFalse((self.project / ".agent").exists())

    def test_target_edit_after_preview_is_preserved(self):
        preview = self.api.preview_sync(str(self.project), ["skill-0.md"])
        target = self.project / ".agent" / "skills" / "skill-0.md"
        target.parent.mkdir(parents=True)
        target.write_text("# User edit\n", encoding="utf-8")
        result = self.api.sync_skills(
            str(self.project), ["skill-0.md"], preview_token=preview["plan_token"]
        )
        self.assertTrue(result["plan_changed"])
        self.assertEqual(target.read_text(encoding="utf-8"), "# User edit\n")

    def test_scope_conflicts_remain_in_preview(self):
        self.api._codex_global_skill_state.return_value = {
            "global_target_states": [{"id": "codex", "label": "Codex", "enabled": True, "kind": "link"}]
        }
        preview = self.api.preview_sync(str(self.project), ["skill-0.md"])
        self.assertEqual(preview["scope_conflict_count"], 1)
        self.assertTrue(preview["has_conflicts"])

    def test_single_project_query_matches_full_query_and_skips_other_manifests(self):
        expected = self.api.get_projects()[0]
        with mock.patch.object(self.api, "_load_sync_manifest", wraps=self.api._load_sync_manifest) as manifest:
            self.assertEqual(self.api.get_project(str(self.project)), expected)
        manifest.assert_called_once_with(str(self.project))

    def test_project_only_view_is_scoped_and_rejects_unavailable_paths(self):
        local = self.project / ".agent" / "skills" / "local.md"
        local.parent.mkdir(parents=True)
        local.write_text("# Local skill\n", encoding="utf-8")
        with (
            mock.patch.object(self.api, "get_projects", side_effect=AssertionError("Full project scan")),
            mock.patch.object(self.api, "_load_sync_manifest", wraps=self.api._load_sync_manifest) as manifest,
        ):
            result = self.api.get_project_skill_content(str(self.project), "local.md")
        self.assertEqual(result, {"content": "# Local skill\n"})
        manifest.assert_called_once_with(str(self.project))
        self.assertIn("error", self.api.get_project_skill_content(str(self.project), "../../secret.md"))
        self.assertIn("error", self.api.get_project(str(self.root)))

    def test_empty_project_list_does_not_scan_library(self):
        self.api.projects = []
        with mock.patch.object(self.api, "_collect_skills", side_effect=AssertionError("Unneeded scan")):
            self.assertEqual(self.api.get_projects(), [])


if __name__ == "__main__":
    unittest.main()
