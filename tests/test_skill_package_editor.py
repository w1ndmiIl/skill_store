import tempfile
import unittest
from pathlib import Path

import yaml

from skillhub.presentation.api.library import LibraryApiMixin
from skillhub.presentation.api.skill_editor import SkillEditorApiMixin


ROOT = Path(__file__).resolve().parents[1]


class EditorApi(SkillEditorApiMixin, LibraryApiMixin):
    def __init__(self, skills_dir: Path, language: str = "zh"):
        self.skills_dir = str(skills_dir)
        self.language = language
        self.registered = []

    def _resolve_virtual_skill(self, _filename):
        return {}

    def _register_library_entry(self, filename, source=""):
        self.registered.append((filename, source))


class SkillPackageEditorApiTests(unittest.TestCase):
    def _write_skill(self, root: Path, name: str = "demo-skill") -> Path:
        package = root / name
        package.mkdir(parents=True)
        (package / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: 处理示例任务\n---\n\n# Demo\n",
            encoding="utf-8",
        )
        return package

    def test_editor_returns_skill_and_existing_openai_metadata(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            root = Path(temp_dir)
            package = self._write_skill(root)
            metadata = package / "agents" / "openai.yaml"
            metadata.parent.mkdir()
            metadata.write_text(
                "interface:\n  display_name: Demo\n"
                "policy:\n  allow_implicit_invocation: false\n",
                encoding="utf-8",
            )

            result = EditorApi(root).get_skill_editor_data("demo-skill")

            self.assertNotIn("error", result)
            self.assertIn("# Demo", result["skill_content"])
            self.assertIn("display_name: Demo", result["openai_yaml_content"])
            self.assertEqual(result["openai_form"]["display_name"], "Demo")
            self.assertIs(
                result["openai_form"]["allow_implicit_invocation"],
                False,
            )
            self.assertTrue(result["openai_yaml_exists"])
            self.assertTrue(result["openai_yaml_supported"])

    def test_editor_builds_complete_unsaved_template_when_yaml_is_missing(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            root = Path(temp_dir)
            self._write_skill(root)

            result = EditorApi(root).get_skill_editor_data("demo-skill")
            document = yaml.safe_load(result["openai_yaml_content"])

            self.assertFalse(result["openai_yaml_exists"])
            self.assertEqual(document["interface"]["display_name"], "demo-skill")
            self.assertEqual(
                document["interface"]["short_description"],
                "处理示例任务",
            )
            self.assertIn("$demo-skill", document["interface"]["default_prompt"])
            self.assertIs(document["policy"]["allow_implicit_invocation"], True)
            self.assertIn("dependencies:", result["openai_yaml_content"])

    def test_editor_saves_both_sources_and_creates_agents_directory(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            root = Path(temp_dir)
            package = self._write_skill(root)
            api = EditorApi(root)
            metadata_content = (
                "interface:\n"
                "  display_name: Demo UI\n"
                "  short_description: A short description.\n"
                "  default_prompt: Use $demo-skill now.\n"
                "policy:\n"
                "  allow_implicit_invocation: false\n"
            )

            result = api.save_skill_editor_data(
                "demo-skill",
                {
                    "skill_content": "---\nname: demo-skill\ndescription: Updated\n---\n",
                    "openai_yaml_content": metadata_content,
                    "save_openai_yaml": True,
                },
            )

            self.assertEqual(result["ok"], True)
            self.assertTrue(result["openai_yaml_created"])
            self.assertIn("description: Updated", (package / "SKILL.md").read_text(encoding="utf-8"))
            self.assertEqual(
                (package / "agents" / "openai.yaml").read_text(encoding="utf-8"),
                metadata_content,
            )
            self.assertEqual(api.registered, [("demo-skill", "edited")])

    def test_invalid_yaml_rejects_whole_save_without_touching_skill(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            root = Path(temp_dir)
            package = self._write_skill(root)
            original = (package / "SKILL.md").read_text(encoding="utf-8")

            result = EditorApi(root).save_skill_editor_data(
                "demo-skill",
                {
                    "skill_content": "changed",
                    "openai_yaml_content": "interface: [broken",
                    "save_openai_yaml": True,
                },
            )

            self.assertIn("Invalid agents/openai.yaml", result["error"])
            self.assertEqual((package / "SKILL.md").read_text(encoding="utf-8"), original)
            self.assertFalse((package / "agents" / "openai.yaml").exists())

    def test_known_dependency_fields_are_type_checked(self):
        valid = (
            "dependencies:\n"
            "  tools:\n"
            "    - type: mcp\n"
            "      value: docs\n"
            "      url: https://example.test/mcp\n"
        )
        invalid = "dependencies:\n  tools: mcp\n"

        self.assertEqual(EditorApi._validate_openai_yaml(valid), "")
        self.assertEqual(
            EditorApi._validate_openai_yaml(invalid),
            "dependencies.tools must be a YAML list",
        )

    def test_visual_form_round_trip_preserves_unknown_fields(self):
        api = EditorApi(ROOT)
        source = (
            "interface:\n"
            "  display_name: Old name\n"
            "  icon_small: ./assets/icon.svg\n"
            "policy:\n"
            "  allow_implicit_invocation: true\n"
            "dependencies:\n"
            "  tools:\n"
            "    - type: mcp\n"
            "      value: old-docs\n"
            "      custom_header: keep-me\n"
            "future_section:\n"
            "  enabled: true\n"
        )

        parsed = api.parse_openai_yaml_form(source)
        form = parsed["form"]
        form["display_name"] = "New name"
        form["short_description"] = "Explains the Skill."
        form["default_prompt"] = "Use $demo-skill now."
        form["allow_implicit_invocation"] = False
        form["tools"][0]["value"] = "new-docs"
        rendered = api.render_openai_yaml_form(source, form)
        document = yaml.safe_load(rendered["content"])

        self.assertEqual(document["interface"]["display_name"], "New name")
        self.assertEqual(document["interface"]["icon_small"], "./assets/icon.svg")
        self.assertFalse(document["policy"]["allow_implicit_invocation"])
        self.assertEqual(document["dependencies"]["tools"][0]["value"], "new-docs")
        self.assertEqual(
            document["dependencies"]["tools"][0]["custom_header"],
            "keep-me",
        )
        self.assertEqual(document["future_section"], {"enabled": True})

    def test_visual_form_requires_dependency_type_and_value(self):
        api = EditorApi(ROOT)
        source = "interface: {}\npolicy: {}\n"
        result = api.render_openai_yaml_form(
            source,
            {
                "display_name": "Demo",
                "short_description": "",
                "default_prompt": "",
                "allow_implicit_invocation": True,
                "tools": [{"type": "mcp", "value": ""}],
            },
        )

        self.assertEqual(result["error"], "tools[0] requires type and value")

    def test_single_markdown_skill_does_not_offer_package_metadata(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            root = Path(temp_dir)
            (root / "single.md").write_text("# Single\n", encoding="utf-8")

            result = EditorApi(root).get_skill_editor_data("single.md")

            self.assertFalse(result["openai_yaml_supported"])
            self.assertEqual(result["openai_yaml_content"], "")


class SkillPackageEditorFrontendTests(unittest.TestCase):
    def test_editor_exposes_both_package_sources_and_explains_invocation(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn("agents/openai.yaml", html)
        self.assertIn("description 参与隐式匹配", html)
        self.assertIn("allow_implicit_invocation", html)
        self.assertIn("display_name", html)
        self.assertIn("short_description", html)
        self.assertIn("default_prompt", html)
        self.assertIn("dependencies.tools", html)
        self.assertIn("可视化配置", html)
        self.assertIn("仅手动调用", html)
        self.assertIn("它不是 Skill 的内部执行指令", html)
        self.assertIn('spellcheck="false"', html)
        self.assertIn("get_skill_editor_data(filename)", javascript)
        self.assertIn("parse_openai_yaml_form", javascript)
        self.assertIn("render_openai_yaml_form", javascript)
        self.assertIn("save_skill_editor_data(editingFilename", javascript)
        self.assertIn("editorOpenaiYamlCreateRequested", javascript)


if __name__ == "__main__":
    unittest.main()
