import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendCollectionDisplayTests(unittest.TestCase):
    def test_skill_rows_do_not_schedule_redundant_stagger_timers(self):
        source = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("hasRenderedSkillCards", source)
        self.assertNotIn("card.style.transitionDelay", source)

    def test_collection_card_does_not_inherit_first_child_display_metadata(self):
        source = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        helper = source.split(
            "// COLLECTION_DISPLAY_METADATA_HELPER_START",
            1,
        )[1].split(
            "// COLLECTION_DISPLAY_METADATA_HELPER_END",
            1,
        )[0]
        script = helper + r"""
const localized = resolveCollectionDisplayMetadata({
  title: 'defuddle',
  description: 'Extract web content.',
  display_title: '网页正文提取（Defuddle）',
  display_description: '提取网页正文。',
  collection: {
    title: 'Obsidian Skills',
    display_title: 'Obsidian 技能集',
    display_description: '用于处理 Obsidian 内容的技能集合。',
    is_controller: false
  }
}, 'obsidian-skills', 5, 'zh');

const imported = resolveCollectionDisplayMetadata({
  title: 'First Child',
  description: 'First child description.',
  display_title: '第一个子技能',
  display_description: '第一个子技能说明。',
  collection: {
    title: 'Imported Toolkit',
    is_controller: false
  }
}, 'imported-toolkit', 3, 'zh');

const controlled = resolveCollectionDisplayMetadata({
  title: 'Controller',
  description: 'Controls the complete toolkit.',
  collection: {
    title: 'Controlled Toolkit',
    is_controller: true
  }
}, 'controlled-toolkit', 2, 'en');

process.stdout.write(JSON.stringify({ localized, imported, controlled }));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        cases = json.loads(completed.stdout)

        self.assertEqual(cases["localized"], {
            "title": "Obsidian 技能集",
            "description": "用于处理 Obsidian 内容的技能集合。",
            "display_title": "Obsidian 技能集",
            "display_description": "用于处理 Obsidian 内容的技能集合。",
        })
        self.assertEqual(cases["imported"], {
            "title": "Imported Toolkit",
            "description": "包含 3 个子技能的技能集合。",
            "display_title": "Imported Toolkit",
            "display_description": "包含 3 个子技能的技能集合。",
        })
        self.assertEqual(cases["controlled"], {
            "title": "Controlled Toolkit",
            "description": "Controls the complete toolkit.",
            "display_title": "Controlled Toolkit",
            "display_description": "Controls the complete toolkit.",
        })

    def test_collection_project_state_tracks_manifest_ownership(self):
        source = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        helper = source.split(
            "// COLLECTION_PROJECT_STATE_HELPER_START",
            1,
        )[1].split(
            "// COLLECTION_PROJECT_STATE_HELPER_END",
            1,
        )[0]
        script = helper + r"""
const members = [
  { filename: 'one.md', collection: { effective_enabled: false } },
  { filename: 'two.md', collection: { effective_enabled: false } }
];
const state = resolveCollectionProjectState(
  members,
  { 'one.md': 'synced', 'two.md': 'unloaded' },
  new Set(),
  new Set(['one.md']),
  new Set(['two.md'])
);
process.stdout.write(JSON.stringify(state));
"""
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        state = json.loads(completed.stdout)

        self.assertEqual(state["physicalStatus"], "out_of_sync")
        self.assertTrue(state["isManaged"])
        self.assertTrue(state["isDetached"])
        self.assertFalse(state["isLocallyEnabled"])


if __name__ == "__main__":
    unittest.main()
