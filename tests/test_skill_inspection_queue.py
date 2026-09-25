"""Inspection acknowledgements persist only for the version the user saw."""

import tempfile
import unittest
from pathlib import Path

from skillhub.presentation.api.collections import CollectionsApiMixin


class InspectionApi(CollectionsApiMixin):
    def __init__(self, skills_dir):
        self.skills_dir = str(skills_dir)


class SkillInspectionQueueTests(unittest.TestCase):
    def test_acknowledged_version_stays_out_of_queue_until_file_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skill = root / "lab1031-server.md"
            skill.write_text("original", encoding="utf-8")
            api = InspectionApi(root)
            self.assertEqual(api.scan_unregistered_skills()["skills"], [])

            skill.write_text("edited outside SkillHub", encoding="utf-8")
            pending = api.scan_unregistered_skills()["skills"]
            self.assertEqual([item["filename"] for item in pending], [skill.name])
            inspected_hash = pending[0]["hash"]

            self.assertTrue(api.acknowledge_unregistered_skill(skill.name, inspected_hash)["ok"])
            self.assertEqual(api.scan_unregistered_skills()["skills"], [])
            self.assertEqual(skill.read_text(encoding="utf-8"), "edited outside SkillHub")

            skill.write_text("edited again", encoding="utf-8")
            self.assertIn("error", api.acknowledge_unregistered_skill(skill.name, inspected_hash))
            self.assertEqual(len(api.scan_unregistered_skills()["skills"]), 1)


if __name__ == "__main__":
    unittest.main()
