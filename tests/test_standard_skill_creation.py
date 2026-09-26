"""New local Skills must remain portable while legacy files stay readable."""

import tempfile
import unittest
from pathlib import Path

import main


class StandardSkillCreationTests(unittest.TestCase):
    def make_api(self, root):
        api = main.Api.__new__(main.Api)
        api.skills_dir = str(root)
        api.language = "zh"
        return api

    def test_manual_creation_uses_named_skill_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            api = self.make_api(root)
            result = api.create_skill("code-safety.md")

            self.assertEqual(result, {"ok": True, "filename": "code-safety"})
            content = (root / "code-safety" / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("name: code-safety\n", content)
            self.assertIn("description:", content)
            self.assertFalse((root / "code-safety.md").exists())
            self.assertEqual(
                api._collect_skills(include_global_state=False)[0]["folder_kind"],
                "standard",
            )
            self.assertIn("error", api.create_skill("code-safety"))
            chinese = api.create_skill("代码安全规范")
            self.assertTrue(chinese["ok"])
            self.assertTrue(chinese["filename"].startswith("skill-"))
            self.assertIn(
                'title: "代码安全规范"',
                (root / chinese["filename"] / "SKILL.md").read_text(encoding="utf-8"),
            )

    def test_ai_save_uses_standard_folder_and_keeps_generated_body(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            api = self.make_api(root)
            generated = {
                "filename": "infra_workflow.md",
                "title": "基础设施工作流",
                "description": "按用户任务检查基础设施并记录结果。",
                "content": "# 基础设施工作流\n\n保留原始步骤。\n",
            }
            first = api.ai_save_skill(generated)
            second = api.ai_save_skill(generated)

            self.assertEqual(first["filename"], "infra-workflow")
            self.assertEqual(second["filename"], "infra-workflow-2")
            content = (root / "infra-workflow" / "SKILL.md").read_text(encoding="utf-8")
            _frontmatter, body, valid = main.split_markdown_frontmatter_source(content)
            self.assertTrue(valid)
            self.assertIn("name: infra-workflow", content)
            self.assertIn("title: \"基础设施工作流\"", content)
            self.assertEqual(body, generated["content"].strip() + "\n")
            self.assertIn(
                "error",
                api.ai_save_skill({"filename": "AGENTS.md", "content": "# overwrite"}),
            )


if __name__ == "__main__":
    unittest.main()
