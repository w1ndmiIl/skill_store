import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from main import Api


ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class ProjectSyncOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temp_dir.name)
        self.skills_dir = self.root / "global-skills"
        self.project_dir = self.root / "project"
        self.skills_dir.mkdir()
        self.project_dir.mkdir()

        self.api = Api()
        self.api.skills_dir = str(self.skills_dir)
        self.api.projects = [{"name": "project", "path": str(self.project_dir)}]
        self.api.language = "en"

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_standard_skill(self, project_skill_content=None):
        skill_content = (
            "---\n"
            "name: canonical-report-writing\n"
            "description: Write evidence-backed reports.\n"
            "---\n\n"
            "# Canonical Report Writing\n"
        )
        yaml_content = (
            "interface:\n"
            "  display_name: Canonical Report Writing\n"
            "  short_description: Write evidence-backed reports.\n"
        )
        global_root = self.skills_dir / "canonical-report-writing"
        project_root = (
            self.project_dir / ".agent" / "skills" / "canonical-report-writing"
        )
        write_text(global_root / "SKILL.md", skill_content)
        write_text(global_root / "agents" / "openai.yaml", yaml_content)
        write_text(
            project_root / "SKILL.md",
            skill_content if project_skill_content is None else project_skill_content,
        )
        write_text(project_root / "agents" / "openai.yaml", yaml_content)
        return global_root, project_root

    def manifest(self):
        path = self.project_dir / ".agent" / ".skill-hub" / "manifest.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_unmanaged_matching_copy_is_previewed_removed_and_restorable(self):
        _global_root, project_root = self.create_standard_skill()

        preview = self.api.preview_sync(str(self.project_dir), [])
        removals = [
            item
            for item in preview["changes"]
            if item["owner"] == "canonical-report-writing"
        ]

        self.assertEqual(len(removals), 2)
        self.assertTrue(all(item["action"] == "delete" for item in removals))
        self.assertTrue(all(not item["conflict"] for item in removals))
        self.assertTrue(all(
            item["reason_code"] == "unmanaged_matching_copy"
            for item in removals
        ))

        result = self.api.sync_skills(
            str(self.project_dir),
            [],
            preview_token=preview["plan_token"],
        )
        self.assertTrue(result["ok"])
        self.assertFalse((project_root / "SKILL.md").exists())
        self.assertFalse((project_root / "agents" / "openai.yaml").exists())

        restored = self.api.undo_last_sync(str(self.project_dir))
        self.assertTrue(restored["ok"])
        self.assertTrue((project_root / "SKILL.md").is_file())
        self.assertTrue((project_root / "agents" / "openai.yaml").is_file())

    def test_unmanaged_modified_copy_requires_explicit_confirmation(self):
        _global_root, project_root = self.create_standard_skill(
            "# Project-specific report workflow\n"
        )

        preview = self.api.preview_sync(str(self.project_dir), [])
        modified = next(
            item
            for item in preview["changes"]
            if item["path"].endswith("canonical-report-writing/SKILL.md")
        )
        self.assertEqual(modified["action"], "delete")
        self.assertTrue(modified["conflict"])
        self.assertEqual(modified["reason_code"], "unmanaged_modified_copy")

        blocked = self.api.sync_skills(str(self.project_dir), [])
        self.assertTrue(blocked["requires_confirmation"])
        self.assertTrue((project_root / "SKILL.md").is_file())

        applied = self.api.sync_skills(
            str(self.project_dir),
            [],
            allow_conflicts=True,
            preview_token=preview["plan_token"],
        )
        self.assertTrue(applied["ok"])
        self.assertFalse((project_root / "SKILL.md").exists())

    def test_matching_enabled_copy_is_adopted_without_rewrite(self):
        _global_root, project_root = self.create_standard_skill()
        skill_path = project_root / "SKILL.md"
        old_timestamp = 1_700_000_000
        os.utime(skill_path, (old_timestamp, old_timestamp))
        original_mtime = skill_path.stat().st_mtime_ns

        preview = self.api.preview_sync(
            str(self.project_dir), ["canonical-report-writing"]
        )
        adopted = [
            item
            for item in preview["changes"]
            if item["owner"] == "canonical-report-writing"
        ]
        self.assertEqual(len(adopted), 2)
        self.assertTrue(all(item["action"] == "adopt" for item in adopted))

        result = self.api.sync_skills(
            str(self.project_dir),
            ["canonical-report-writing"],
            preview_token=preview["plan_token"],
        )
        self.assertTrue(result["ok"])
        self.assertEqual(skill_path.stat().st_mtime_ns, original_mtime)
        self.assertIn(
            "canonical-report-writing",
            self.api.get_projects()[0]["managed_skills"],
        )
        owners = {
            item["owner"]
            for item in self.manifest()["files"].values()
        }
        self.assertIn("canonical-report-writing", owners)

    def test_modified_managed_copy_is_detached_once_and_not_reprompted(self):
        write_text(self.skills_dir / "alpha.md", "# Alpha\n")
        installed = self.api.sync_skills(str(self.project_dir), ["alpha.md"])
        self.assertTrue(installed["ok"])
        target = self.project_dir / ".agent" / "skills" / "alpha.md"
        write_text(target, "# Project customization\n")

        preview = self.api.preview_sync(str(self.project_dir), [])
        self.assertEqual(preview["summary"]["preserve"], 1)
        detached = self.api.sync_skills(
            str(self.project_dir),
            [],
            preview_token=preview["plan_token"],
        )
        self.assertTrue(detached["ok"])
        self.assertEqual(target.read_text(encoding="utf-8"), "# Project customization\n")
        self.assertIn("alpha.md", self.api.get_projects()[0]["detached_skills"])

        next_preview = self.api.preview_sync(str(self.project_dir), [])
        self.assertEqual(next_preview["summary"]["delete"], 0)
        self.assertEqual(next_preview["summary"]["preserve"], 0)

    def test_project_status_skips_unneeded_global_target_inspection(self):
        write_text(self.skills_dir / "alpha.md", "# Alpha\n")

        with mock.patch.object(
            self.api,
            "_codex_global_skill_state",
            side_effect=AssertionError("global state should not be inspected"),
        ):
            projects = self.api.get_projects()

        self.assertEqual(projects[0]["skills_status"]["alpha.md"], "unloaded")


if __name__ == "__main__":
    unittest.main()
