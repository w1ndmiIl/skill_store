import hashlib
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import main


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


class CodexGlobalSkillTests(unittest.TestCase):
    def make_api(self, skills_dir: Path) -> main.Api:
        api = main.Api.__new__(main.Api)
        api.skills_dir = str(skills_dir)
        api.language = "zh"
        api._global_skill_target_dir_overrides = {}
        return api

    def test_codex_view_preserves_body_and_supported_semantic_fields(self):
        source = """---
name: sample-skill
description: Keep the original behavior.
allowed-tools:
  - Read
metadata:
  owner: example
category: display-only
trigger: legacy-ui
---

# Workflow

Never change this instruction.
"""
        rendered, removed = main.build_codex_skill_view(
            source, "sample-skill", "fallback"
        )
        source_frontmatter, source_body, _ = main.split_markdown_frontmatter_source(
            source
        )
        rendered_frontmatter, rendered_body, _ = (
            main.split_markdown_frontmatter_source(rendered)
        )

        self.assertEqual(source_body, rendered_body)
        self.assertIn("allowed-tools:", rendered_frontmatter)
        self.assertIn("metadata:", rendered_frontmatter)
        self.assertNotIn("category:", rendered_frontmatter)
        self.assertNotIn("trigger:", rendered_frontmatter)
        self.assertEqual(removed, ["category", "trigger"])
        self.assertIn("category:", source_frontmatter)

    def test_codex_target_uses_codex_home(self):
        api = self.make_api(Path("D:/unused"))
        with mock.patch.dict(os.environ, {"CODEX_HOME": "D:/CodexHome"}):
            self.assertEqual(
                os.path.normcase(api._global_skill_target_dir("codex")),
                os.path.normcase(os.path.abspath("D:/CodexHome/skills")),
            )

    def test_popular_agent_targets_use_documented_user_directories(self):
        api = self.make_api(Path("D:/unused"))
        expected = {
            "cursor": (".cursor", "skills"),
            "cline": (".cline", "skills"),
            "opencode": (".config", "opencode", "skills"),
            "windsurf": (".codeium", "windsurf", "skills"),
        }
        with mock.patch("os.path.expanduser", return_value="D:/Users/example"):
            actual = {
                target_id: api._global_skill_target_dir(target_id)
                for target_id in expected
            }

        for target_id, path_parts in expected.items():
            with self.subTest(target=target_id):
                self.assertEqual(
                    os.path.normcase(actual[target_id]),
                    os.path.normcase(
                        os.path.join("D:/Users/example", *path_parts)
                    ),
                )

        additions = [
            target_id for target_id in main.GLOBAL_SKILL_TARGETS
            if target_id in expected
        ]
        self.assertEqual(
            additions, ["cursor", "cline", "opencode", "windsurf"]
        )

    def test_missing_agent_skill_directories_are_reported_without_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            home.mkdir()
            api = self.make_api(Path(temporary) / "library")

            with mock.patch("os.path.expanduser", return_value=str(home)):
                options = {
                    option["id"]: option
                    for option in api._global_skill_target_options()
                }

            for target_id in ("cursor", "cline", "opencode", "windsurf"):
                with self.subTest(target=target_id):
                    self.assertFalse(options[target_id]["available"])
                    self.assertFalse(Path(options[target_id]["path"]).exists())
            self.assertEqual(list(home.iterdir()), [])

    def test_enable_refuses_missing_agent_directory_without_creating_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skills = root / "skills"
            skill = skills / "sample-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Stable behavior.\n---\n",
                encoding="utf-8",
            )
            api = self.make_api(skills)
            missing_target = root / "missing-cursor" / "skills"
            api._global_skill_target_dir_overrides = {
                target_id: str(root / f"missing-{target_id}" / "skills")
                for target_id, definition in main.GLOBAL_SKILL_TARGETS.items()
                if definition["kind"] == "link"
            }
            api._global_skill_target_dir_overrides["cursor"] = str(missing_target)

            result = api.set_skill_global_targets("sample-skill", ["cursor"])

            self.assertIn("will not create", result.get("error", ""))
            self.assertEqual(result.get("failed_target"), "cursor")
            self.assertFalse((root / "missing-cursor").exists())
            self.assertFalse(
                (skills / ".skill-hub" / "cursor-standard").exists()
            )

    def test_link_creation_requires_an_existing_agent_skill_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            api = self.make_api(root / "library")
            target = root / "missing-agent" / "skills" / "sample-skill"

            with self.assertRaisesRegex(OSError, "will not create"):
                api._create_codex_global_link(str(source), str(target))

            self.assertFalse((root / "missing-agent").exists())

    def test_standard_adapter_copies_resources_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skills = root / "skills"
            skill = skills / "sample-skill"
            (skill / "agents").mkdir(parents=True)
            (skill / "references").mkdir()
            source_content = """---
name: sample-skill
description: Keep the original behavior.
allowed-tools: Read
category: display-only
---

# Workflow

Never change this instruction.
"""
            (skill / "SKILL.md").write_text(source_content, encoding="utf-8")
            (skill / "agents" / "openai.yaml").write_text(
                'policy:\n  allow_implicit_invocation: false\n', encoding="utf-8"
            )
            (skill / "references" / "rules.md").write_text(
                "unchanged resource", encoding="utf-8"
            )
            api = self.make_api(skills)
            descriptor = api._codex_global_skill_descriptor("sample-skill")
            before_hash = tree_hash(skill)

            api._write_codex_standard_adapter(descriptor)

            adapter = Path(descriptor["codex_link_source"])
            self.assertEqual(before_hash, tree_hash(skill))
            self.assertEqual(
                (adapter / "references" / "rules.md").read_bytes(),
                (skill / "references" / "rules.md").read_bytes(),
            )
            self.assertEqual(
                (adapter / "agents" / "openai.yaml").read_bytes(),
                (skill / "agents" / "openai.yaml").read_bytes(),
            )
            with open(skill / "SKILL.md", "r", encoding="utf-8", newline="") as handle:
                stored_source = handle.read()
            _source_frontmatter, source_body, _ = (
                main.split_markdown_frontmatter_source(stored_source)
            )
            with open(adapter / "SKILL.md", "r", encoding="utf-8", newline="") as handle:
                adapter_content = handle.read()
            adapter_frontmatter, adapter_body, _ = (
                main.split_markdown_frontmatter_source(adapter_content)
            )
            self.assertEqual(source_body, adapter_body)
            self.assertIn("allowed-tools:", adapter_frontmatter)
            self.assertNotIn("category:", adapter_frontmatter)
            self.assertTrue((adapter / main.CODEX_ADAPTER_MANIFEST).is_file())

    def test_vscode_adapter_matches_folder_name_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skills = root / "skills"
            skill = skills / "legacy-folder"
            skill.mkdir(parents=True)
            source_content = """---
name: portable-skill
description: Preserve the original workflow.
allowed-tools: Read
category: display-only
---

# Workflow

Keep this body unchanged.
"""
            (skill / "SKILL.md").write_text(source_content, encoding="utf-8")
            api = self.make_api(skills)
            descriptor = api._codex_global_skill_descriptor("legacy-folder")
            before_hash = tree_hash(skill)

            api._write_codex_standard_adapter(descriptor, "vscode")

            adapter = Path(descriptor["target_adapter_paths"]["vscode"])
            rendered = (adapter / "SKILL.md").read_text(encoding="utf-8")
            frontmatter, body, _ = main.split_markdown_frontmatter_source(rendered)
            _source_frontmatter, source_body, _ = (
                main.split_markdown_frontmatter_source(source_content)
            )
            self.assertEqual(adapter.name, "portable-skill")
            self.assertEqual(main.yaml.safe_load(frontmatter)["name"], "portable-skill")
            self.assertNotIn("allowed-tools:", frontmatter)
            self.assertEqual(body, source_body)
            self.assertEqual(tree_hash(skill), before_hash)

    def test_popular_agent_adapters_use_independent_frontmatter_allowlists(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skills = root / "skills"
            skill = skills / "legacy-folder"
            (skill / "references").mkdir(parents=True)
            source_content = """---
name: portable-skill
description: Preserve the original workflow.
paths:
  - "**/*.py"
disable-model-invocation: true
license: MIT
compatibility: Requires Python.
metadata:
  owner: example
allowed-tools: Read
category: display-only
---

# Workflow

Keep this body unchanged.
"""
            (skill / "SKILL.md").write_text(source_content, encoding="utf-8")
            (skill / "references" / "rules.md").write_text(
                "unchanged resource", encoding="utf-8"
            )
            api = self.make_api(skills)
            descriptor = api._codex_global_skill_descriptor("legacy-folder")
            before_hash = tree_hash(skill)
            allowed_by_target = {
                "cursor": main.CURSOR_FRONTMATTER_KEYS,
                "cline": main.CLINE_FRONTMATTER_KEYS,
                "opencode": main.OPENCODE_FRONTMATTER_KEYS,
                "windsurf": main.WINDSURF_FRONTMATTER_KEYS,
            }
            _source_frontmatter, source_body, _ = (
                main.split_markdown_frontmatter_source(source_content)
            )

            for target_id, allowed_keys in allowed_by_target.items():
                with self.subTest(target=target_id):
                    api._write_codex_standard_adapter(descriptor, target_id)
                    adapter = Path(
                        descriptor["target_adapter_paths"][target_id]
                    )
                    rendered = (adapter / "SKILL.md").read_text(encoding="utf-8")
                    frontmatter, body, _ = (
                        main.split_markdown_frontmatter_source(rendered)
                    )
                    parsed = main.yaml.safe_load(frontmatter)
                    self.assertEqual(adapter.name, "portable-skill")
                    self.assertEqual(parsed["name"], "portable-skill")
                    self.assertFalse(set(parsed) - allowed_keys)
                    self.assertEqual(body, source_body)
                    self.assertEqual(
                        (adapter / "references" / "rules.md").read_text(
                            encoding="utf-8"
                        ),
                        "unchanged resource",
                    )

            self.assertEqual(tree_hash(skill), before_hash)

    def test_claude_desktop_export_strips_client_only_fields_from_upload_view(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skills = root / "skills"
            skill = skills / "sample-skill"
            (skill / "references").mkdir(parents=True)
            source_content = """---
name: sample-skill
description: Preserve the original workflow.
allowed-tools:
  - Read
metadata:
  owner: example
---

# Workflow

Keep this body unchanged.
"""
            (skill / "SKILL.md").write_text(source_content, encoding="utf-8")
            (skill / "references" / "rule.md").write_text(
                "resource stays unchanged", encoding="utf-8"
            )
            api = self.make_api(skills)
            descriptor = api._codex_global_skill_descriptor("sample-skill")
            before_hash = tree_hash(skill)

            api._write_claude_desktop_export(descriptor)

            package = Path(api._claude_desktop_export_root()) / "sample-skill.zip"
            self.assertTrue(package.is_file())
            with zipfile.ZipFile(package) as archive:
                names = set(archive.namelist())
                self.assertIn("sample-skill/SKILL.md", names)
                self.assertIn("sample-skill/references/rule.md", names)
                self.assertFalse(any(main.CODEX_ADAPTER_MANIFEST in name for name in names))
                rendered = archive.read("sample-skill/SKILL.md").decode("utf-8")
            frontmatter, body, _ = main.split_markdown_frontmatter_source(rendered)
            with open(skill / "SKILL.md", "r", encoding="utf-8", newline="") as handle:
                stored_source = handle.read()
            _source_frontmatter, source_body, _ = (
                main.split_markdown_frontmatter_source(stored_source)
            )
            self.assertEqual(main.yaml.safe_load(frontmatter)["name"], "sample-skill")
            self.assertIn("description:", frontmatter)
            self.assertNotIn("allowed-tools:", frontmatter)
            self.assertNotIn("metadata:", frontmatter)
            self.assertEqual(body, source_body)
            self.assertEqual(tree_hash(skill), before_hash)

    def test_local_compatibility_check_reports_target_adaptation_and_permissions(self):
        content = """---
name: portable-skill
description: Preserve the original workflow.
allowed-tools:
  - Read
  - Write
---

# Workflow
"""
        result = main.inspect_agent_skill_compatibility(
            content, "legacy-folder", package_bytes=1024
        )
        self.assertEqual(result["targets"]["codex"]["status"], "ready")
        self.assertEqual(result["targets"]["vscode"]["status"], "adapted")
        self.assertEqual(result["targets"]["claude_code"]["status"], "warning")
        self.assertEqual(result["targets"]["cursor"]["status"], "adapted")
        self.assertEqual(result["targets"]["cline"]["status"], "adapted")
        self.assertEqual(result["targets"]["opencode"]["status"], "adapted")
        self.assertEqual(result["targets"]["windsurf"]["status"], "adapted")
        self.assertEqual(result["targets"]["claude_desktop"]["status"], "adapted")
        self.assertIn(
            "claude_allowed_tools",
            {finding["code"] for finding in result["findings"]},
        )

    def test_import_health_check_includes_local_client_matrix(self):
        with tempfile.TemporaryDirectory() as temporary:
            skill = Path(temporary) / "legacy-folder"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\nname: portable-skill\ndescription: Stable workflow.\n"
                "category: display-only\n---\n\n# Workflow\n",
                encoding="utf-8",
            )
            api = self.make_api(Path(temporary))

            result = api._inspect_import_compatibility(
                str(skill), "standard", "legacy-folder"
            )

            self.assertEqual(set(result["targets"]), set(main.GLOBAL_SKILL_TARGETS))
            self.assertEqual(result["targets"]["vscode"]["status"], "adapted")
            self.assertEqual(result["targets"]["gemini_cli"]["status"], "adapted")
            self.assertTrue(result["findings"])

    def test_gemini_cli_has_its_own_user_target(self):
        api = self.make_api(Path("D:/unused"))
        with mock.patch("os.path.expanduser", return_value="D:/Users/example"):
            target = api._global_skill_target_dir("gemini_cli")
        self.assertEqual(
            os.path.normcase(target),
            os.path.normcase(os.path.join("D:/Users/example", ".gemini", "skills")),
        )

    def test_non_latin_names_receive_stable_distinct_portable_ids(self):
        first = main.normalize_agent_skill_name("代码审查", "代码审查")
        second = main.normalize_agent_skill_name("报告写作", "报告写作")
        self.assertRegex(first, main.AGENT_SKILL_NAME_RE)
        self.assertRegex(second, main.AGENT_SKILL_NAME_RE)
        self.assertNotEqual(first, second)
        self.assertEqual(
            first, main.normalize_agent_skill_name("代码审查", "代码审查")
        )

    def test_other_client_legacy_link_migrates_to_client_adapter(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skills = root / "skills"
            skill = skills / "sample-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Stable behavior.\n"
                "category: display-only\n---\n\n# Workflow\n\nDo the task.\n",
                encoding="utf-8",
            )
            api = self.make_api(skills)
            claude_target = root / "claude" / "skills"
            api._global_skill_target_dir_overrides = {
                "claude_code": str(claude_target)
            }
            claude_target.mkdir(parents=True)
            api._create_codex_global_link(
                str(skill), str(claude_target / "sample-skill")
            )
            descriptor = api._codex_global_skill_descriptor("sample-skill")
            before_hash = tree_hash(skill)
            legacy = api._global_target_state(descriptor, "claude_code")
            self.assertEqual(legacy["status"], "legacy")

            result = api.set_skill_global_targets("sample-skill", ["claude_code"])

            self.assertTrue(result.get("ok"), result)
            published = claude_target / "sample-skill"
            adapter = descriptor["target_adapter_paths"]["claude_code"]
            self.assertTrue(api._same_real_path(str(published), adapter))
            frontmatter, _body, _ = main.split_markdown_frontmatter_source(
                (Path(adapter) / "SKILL.md").read_text(encoding="utf-8")
            )
            self.assertFalse(
                set(main.yaml.safe_load(frontmatter))
                - main.CLAUDE_CODE_FRONTMATTER_KEYS
            )
            self.assertEqual(tree_hash(skill), before_hash)

    def test_enable_uses_codex_target_and_migrates_managed_legacy_link(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skills = root / "skills"
            skill = skills / "sample-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Stable behavior.\n"
                "category: display-only\n---\n\n# Workflow\n\nDo the task.\n",
                encoding="utf-8",
            )
            api = self.make_api(skills)
            codex_target = root / "codex" / "skills"
            legacy_target = root / "agents" / "skills"
            api._global_skill_target_dir_overrides = {
                "codex": str(codex_target)
            }
            api._legacy_codex_global_skills_dir_override = str(legacy_target)
            codex_target.mkdir(parents=True)
            legacy_target.mkdir(parents=True)
            api._create_codex_global_link(
                str(skill), str(legacy_target / "sample-skill")
            )
            before_hash = tree_hash(skill)
            legacy_state = api._codex_global_skill_state("sample-skill")
            codex_state = next(
                item for item in legacy_state["global_target_states"]
                if item["id"] == "codex"
            )
            self.assertEqual(codex_state["status"], "legacy")
            self.assertTrue(codex_state["enabled"])

            result = api.set_skill_global_targets("sample-skill", ["codex"])

            self.assertTrue(result.get("ok"), result)
            descriptor = api._codex_global_skill_descriptor("sample-skill")
            published = codex_target / "sample-skill"
            self.assertTrue(published.exists())
            self.assertTrue(
                api._same_real_path(
                    str(published), descriptor["codex_link_source"]
                )
            )
            self.assertFalse(os.path.lexists(legacy_target / "sample-skill"))
            self.assertEqual(before_hash, tree_hash(skill))

            disabled = api.set_skill_global_targets("sample-skill", [])
            self.assertTrue(disabled.get("ok"), disabled)
            self.assertFalse(os.path.lexists(published))
            self.assertFalse(Path(descriptor["codex_link_source"]).exists())

    def test_disabled_targets_do_not_hash_skill_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skills = root / "skills"
            skill = skills / "sample-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Stable behavior.\n---\n",
                encoding="utf-8",
            )
            api = self.make_api(skills)
            api._global_skill_target_dir_overrides = {
                target_id: str(root / target_id)
                for target_id in main.GLOBAL_SKILL_TARGETS
            }

            with mock.patch.object(
                api,
                "_codex_global_source_hash",
                wraps=api._codex_global_source_hash,
            ) as source_hash:
                state = api._codex_global_skill_state("sample-skill")

            self.assertEqual(state["codex_global_status"], "disabled")
            source_hash.assert_not_called()

    def test_enabled_targets_share_one_source_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skills = root / "skills"
            skill = skills / "sample-skill"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Stable behavior.\n---\n",
                encoding="utf-8",
            )
            api = self.make_api(skills)
            api._global_skill_target_dir_overrides = {
                target_id: str(root / target_id)
                for target_id in main.GLOBAL_SKILL_TARGETS
            }
            for target_id in ("codex", "claude_code"):
                (root / target_id / "sample-skill").mkdir(parents=True)

            with (
                mock.patch.object(api, "_same_real_path", return_value=True),
                mock.patch.object(
                    api,
                    "_codex_global_source_hash",
                    wraps=api._codex_global_source_hash,
                ) as source_hash,
            ):
                state = api._codex_global_skill_state("sample-skill")

            enabled = {
                target["id"]
                for target in state["global_target_states"]
                if target["enabled"]
            }
            self.assertEqual(enabled, {"codex", "claude_code"})
            source_hash.assert_called_once()


if __name__ == "__main__":
    unittest.main()
