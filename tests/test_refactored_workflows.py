import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import main
from agent_runtime import AgentRuntime
from skillhub.domain.imports import scan_skill_text
from skillhub.infrastructure.filesystem import atomic_write_text


ROOT = Path(__file__).resolve().parents[1]


def write_text(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write_text(path, content)


class RefactoredWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = self.temporary.name
        self.skills_dir = os.path.join(self.root, "skills")
        self.sources_dir = os.path.join(self.root, "sources")
        os.makedirs(self.skills_dir)
        os.makedirs(self.sources_dir)
        self.api = main.Api()
        self.api.skills_dir = self.skills_dir
        self.api.projects = []
        self.api.language = "zh"
        self.api.deepseek_api_key = ""
        self.api.ai_import_optimization = False
        self.api.ai_display_translation = False

    def tearDown(self):
        self.temporary.cleanup()

    def test_category_delete_rolls_back_through_library_adapter_dependency(self):
        paths = [
            os.path.join(self.skills_dir, "a.md"),
            os.path.join(self.skills_dir, "b.md"),
        ]
        originals = []
        for index, path in enumerate(paths):
            content = (
                "---\n"
                f"title: Skill {index}\n"
                "category: 测试类别\n"
                "---\n\n"
                f"# Skill {index}\n"
            )
            originals.append(content)
            write_text(path, content)
        calls = 0

        def fail_second_write(path, content):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated write failure")
            atomic_write_text(path, content)

        with mock.patch(
            "skillhub.presentation.api.library.atomic_write_text",
            side_effect=fail_second_write,
        ):
            result = self.api.delete_skill_category("测试类别")

        self.assertIn("simulated write failure", result["error"])
        self.assertTrue(result["rolled_back"])
        for path, original in zip(paths, originals):
            self.assertEqual(Path(path).read_text(encoding="utf-8"), original)

    def test_import_tree_rejects_reparse_points_through_preparation_adapter(self):
        source = os.path.join(self.sources_dir, "linked-skill")
        write_text(
            os.path.join(source, "SKILL.md"),
            "---\nname: linked-skill\ndescription: Linked.\n---\n",
        )
        linked = os.path.join(source, "linked")
        os.makedirs(linked)
        with mock.patch(
            "skillhub.presentation.api.import_preparation.is_path_reparse_point",
            side_effect=lambda path: (
                os.path.normcase(path) == os.path.normcase(linked)
            ),
        ):
            preview = self.api.preview_skill_import(source)
        self.assertIn("reparse point", preview["error"].lower())

    def test_truncated_ai_diff_falls_back_via_candidate_adapter(self):
        self.api.ai_import_optimization = True
        self.api.deepseek_api_key = "sk-test-key"
        source = os.path.join(self.sources_dir, "review.md")
        write_text(source, "# Review\n\nCheck behavior.\n")
        response = mock.Mock(status_code=200)
        response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "# AI Review\n\n" + ("Changed behavior.\n" * 100)
                }
            }]
        }
        with (
            mock.patch("skillhub.domain.imports.SKILL_IMPORT_DIFF_MAX_CHARS", 80),
            mock.patch(
                "skillhub.presentation.api.import_candidates.requests.post",
                return_value=response,
            ),
        ):
            preview = self.api.preview_skill_import(source)
        self.assertFalse(preview["ai_used"])
        self.assertTrue(any(
            finding["code"] == "ai_optimization_fallback"
            for finding in preview["findings"]
        ))

    def test_collection_category_is_persisted_exposed_and_deletable(self):
        for name in ("alpha-review", "beta-review"):
            write_text(
                os.path.join(self.skills_dir, name, "SKILL.md"),
                f"---\nname: {name}\ndescription: Review.\n---\n",
            )
        collection = self.api._upsert_skill_collection(
            "research-suite",
            ["alpha-review", "beta-review"],
        )

        updated = self.api.set_collection_category(
            collection["id"],
            "文献研究",
        )

        self.assertTrue(updated["ok"])
        members = {
            skill["filename"]: skill
            for skill in self.api.get_skills()
        }
        self.assertEqual(
            members["alpha-review"]["collection"]["category"],
            "文献研究",
        )
        preview = self.api.preview_delete_skill_category("文献研究")
        self.assertEqual(preview["affected_count"], 1)
        self.assertEqual(
            preview["affected"][0]["filename"],
            f"@collection:{collection['id']}",
        )
        deleted = self.api.delete_skill_category("文献研究")
        self.assertTrue(deleted["ok"])
        self.assertEqual(deleted["affected_count"], 1)
        refreshed = {
            skill["filename"]: skill
            for skill in self.api.get_skills()
        }
        self.assertEqual(
            refreshed["alpha-review"]["collection"]["category"],
            "",
        )

    def test_large_collection_skips_per_member_ai_calls(self):
        repository = os.path.join(self.sources_dir, "large-repository")
        for index in range(9):
            name = f"large-skill-{index}"
            write_text(
                os.path.join(repository, "skills", name, "SKILL.md"),
                f"---\nname: {name}\ndescription: Large collection member.\n---\n",
            )
        self.api.ai_import_optimization = True
        self.api.ai_display_translation = True
        self.api.deepseek_api_key = "sk-test-key"

        with (
            mock.patch(
                "skillhub.presentation.api.import_candidates.requests.post"
            ) as optimize,
            mock.patch(
                "skillhub.presentation.api.collections.requests.post"
            ) as translate,
        ):
            preview = self.api.preview_skill_import(repository)

        self.assertTrue(preview["ok"])
        self.assertFalse(preview["ai_used"])
        self.assertFalse(preview["display_translation_used"])
        optimize.assert_not_called()
        translate.assert_not_called()
        codes = {finding["code"] for finding in preview["findings"]}
        self.assertIn("ai_optimization_fallback", codes)
        self.assertIn("display_translation_fallback", codes)

    def test_collection_with_more_than_500_skill_files_previews(self):
        repository = os.path.join(self.sources_dir, "many-files-repository")
        for skill_index in range(2):
            name = f"many-files-{skill_index}"
            write_text(
                os.path.join(repository, "skills", name, "SKILL.md"),
                f"---\nname: {name}\ndescription: Many files.\n---\n",
            )
            for file_index in range(300):
                write_text(
                    os.path.join(
                        repository,
                        "skills",
                        name,
                        "references",
                        f"reference-{file_index}.md",
                    ),
                    "# Reference\n",
                )

        preview = self.api.preview_skill_import(repository)

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["collection_count"], 2)

    def test_remote_collection_ignores_non_skill_repository_files(self):
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as archive:
            for index in range(520):
                archive.writestr(
                    f"research-suite-main/docs/note-{index}.md",
                    "# Not a skill\n",
                )
            for name in ("alpha-review", "beta-review"):
                archive.writestr(
                    f"research-suite-main/skills/{name}/SKILL.md",
                    f"---\nname: {name}\ndescription: Review.\n---\n",
                )

        class Response:
            status_code = 200
            content = archive_buffer.getvalue()

        self.api._agent_remote_download_root = os.path.join(
            self.root,
            "remote-downloads",
        )
        with mock.patch(
            "skillhub.presentation.api.agent_remote.requests.get",
            return_value=Response(),
        ):
            preview = self.api._tool_preview_remote_skill_collection({
                "repository": "https://github.com/example/research-suite",
                "ref": "main",
            })

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["collection_count"], 2)
        self.assertEqual(
            {item["install_name"] for item in preview["children"]},
            {"alpha-review", "beta-review"},
        )

    def test_sensitive_logging_scan_understands_compound_prohibitions(self):
        findings = scan_skill_text(
            "全程记录访问路径，但不读取或导出浏览器 cookie、密码、"
            "localStorage 或 session 文件。"
        )

        self.assertNotIn(
            "sensitive_logging",
            {finding["code"] for finding in findings},
        )

    def test_github_tree_url_is_normalized_without_guessing_another_ref(self):
        repository, owner, name, reference = (
            self.api._validated_agent_github_source(
                "https://github.com/Yuan1z0825/nature-skills/tree/main"
            )
        )

        self.assertEqual(repository, "https://github.com/Yuan1z0825/nature-skills")
        self.assertEqual(owner, "Yuan1z0825")
        self.assertEqual(name, "nature-skills")
        self.assertEqual(reference, "main")
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.api._validated_agent_github_source(
                "https://github.com/Yuan1z0825/nature-skills/tree/main",
                "master",
            )

    def test_agent_prompt_preserves_an_explicit_github_source(self):
        runtime = AgentRuntime.__new__(AgentRuntime)
        runtime.language = "zh"

        prompt = runtime._system_prompt([])

        self.assertIn("不得猜测其他分支", prompt)
        self.assertIn("企业重打包或第三方来源替代", prompt)
        self.assertIn("仓库级安装目标必须优先使用集合预览", prompt)
