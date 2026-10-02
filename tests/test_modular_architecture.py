import ast
import builtins
import os
import re
import symtable
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main
from skillhub.application.chat_sessions import ChatSessionService
from skillhub.domain import frontmatter, global_targets, naming
from skillhub.infrastructure import filesystem
from skillhub.infrastructure.config_repository import ConfigRepository
from skillhub.infrastructure.global_targets import GlobalTargetService
from skillhub.settings import APP_VERSION, get_user_data_dir


ROOT = Path(__file__).resolve().parents[1]


class InMemorySessionRepository:
    def __init__(self):
        self.sessions = []

    def load(self):
        return [dict(session) for session in self.sessions]

    def save(self, sessions):
        self.sessions = [dict(session) for session in sessions]
        return True


class ModularArchitectureTests(unittest.TestCase):
    def test_user_data_directory_is_stable_and_overridable(self):
        local_root = os.path.join(str(ROOT), "local-app-data")
        self.assertEqual(
            get_user_data_dir({"LOCALAPPDATA": local_root}),
            os.path.join(local_root, "SkillHub"),
        )
        override = os.path.join(str(ROOT), "portable-data")
        self.assertEqual(
            get_user_data_dir({"SKILLHUB_DATA_DIR": override}),
            os.path.abspath(override),
        )

    def test_main_keeps_legacy_helper_exports_during_migration(self):
        self.assertIs(main.split_markdown_frontmatter, frontmatter.split_markdown_frontmatter)
        self.assertIs(main.normalize_agent_skill_name, naming.normalize_agent_skill_name)
        self.assertIs(main.atomic_write_json, filesystem.atomic_write_json)
        self.assertIs(main.safe_real_child_path, filesystem.safe_real_child_path)

    def test_runtime_version_matches_both_readmes(self):
        readme_versions = []
        for filename in ("README.md", "README_EN.md"):
            content = (ROOT / filename).read_text(encoding="utf-8")
            match = re.search(r"(?:当前版本：|Current version: )\*\*([^*]+)\*\*", content)
            self.assertIsNotNone(match, filename)
            readme_versions.append(match.group(1))
        self.assertEqual(readme_versions, [APP_VERSION, APP_VERSION])

    def test_domain_layer_does_not_import_ui_network_or_infrastructure(self):
        self._assert_layer_avoids_imports(
            ROOT / "skillhub" / "domain",
            {
                "main",
                "requests",
                "webview",
                "skillhub.application",
                "skillhub.infrastructure",
            },
        )

    def test_application_layer_depends_on_ports_not_ui_or_infrastructure(self):
        self._assert_layer_avoids_imports(
            ROOT / "skillhub" / "application",
            {
                "main",
                "requests",
                "webview",
                "skillhub.infrastructure",
            },
        )

    def test_infrastructure_services_do_not_depend_on_desktop_entrypoint(self):
        self._assert_layer_avoids_imports(
            ROOT / "skillhub" / "infrastructure",
            {"main", "webview"},
        )

    def test_presentation_adapters_do_not_import_composition_root(self):
        self._assert_layer_avoids_imports(
            ROOT / "skillhub" / "presentation" / "api",
            {"main"},
        )

    def test_main_is_a_small_composition_root(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        api = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "Api"
        )
        own_methods = {
            node.name for node in api.body if isinstance(node, ast.FunctionDef)
        }
        self.assertEqual(own_methods, {"__init__", "set_window"})
        self.assertLessEqual(len(source.splitlines()), 500)

    def test_api_modules_remain_bounded_and_have_resolved_globals(self):
        for path in (ROOT / "skillhub" / "presentation" / "api").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertLessEqual(
                len(source.splitlines()),
                800,
                f"{path.name} needs another responsibility split",
            )
            root = symtable.symtable(source, str(path), "exec")
            module_names = {symbol.get_name() for symbol in root.get_symbols()}
            unresolved = set()
            pending = list(root.get_children())
            while pending:
                table = pending.pop()
                pending.extend(table.get_children())
                for symbol in table.get_symbols():
                    name = symbol.get_name()
                    if (
                        symbol.is_global()
                        and symbol.is_referenced()
                        and name not in module_names
                        and not hasattr(builtins, name)
                    ):
                        unresolved.add(name)
            self.assertFalse(
                unresolved,
                f"{path.name} has unresolved module dependencies: {unresolved}",
            )

    def test_api_inherits_global_target_service_without_duplicate_methods(self):
        self.assertTrue(issubclass(main.Api, GlobalTargetService))
        self.assertNotIn("_global_target_state", main.Api.__dict__)
        self.assertNotIn("set_skill_global_targets", main.Api.__dict__)
        self.assertIs(
            main.GLOBAL_SKILL_TARGETS,
            global_targets.GLOBAL_SKILL_TARGETS,
        )
        self.assertIs(
            main.CODEX_ADAPTER_MANIFEST,
            global_targets.CODEX_ADAPTER_MANIFEST,
        )

    def _assert_layer_avoids_imports(self, directory, forbidden_prefixes):
        for path in directory.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            violations = {
                imported_name
                for imported_name in imported
                for prefix in forbidden_prefixes
                if imported_name == prefix or imported_name.startswith(f"{prefix}.")
            }
            self.assertFalse(
                violations,
                f"{path.name} crosses its layer boundary: {violations}",
            )

    def test_config_repository_round_trips_without_api_dependency(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            config_path = os.path.join(temp_dir, "config.json")
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}):
                repository = ConfigRepository(
                    config_path,
                    temp_dir,
                    ("codex",),
                )
                defaults = repository.load()
                self.assertEqual(defaults["global_skill_targets"], ["codex"])
                self.assertTrue(defaults["skills_dir"].startswith(temp_dir))
                defaults["language"] = "en"
                self.assertTrue(repository.save(defaults))
                self.assertEqual(repository.load()["language"], "en")

    def test_config_repository_migrates_legacy_projects_file(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            config_path = os.path.join(temp_dir, "config.json")
            filesystem.atomic_write_json(
                os.path.join(temp_dir, "projects.json"),
                [{"name": "demo", "path": "D:/demo"}],
            )
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}):
                repository = ConfigRepository(
                    config_path,
                    temp_dir,
                    ("codex",),
                )
                migrated = repository.load()
            self.assertEqual(migrated["projects"][0]["name"], "demo")
            self.assertEqual(migrated["global_skill_targets"], ["codex"])
            self.assertTrue(os.path.isfile(config_path))

    def test_config_repository_migrates_legacy_adjacent_config(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            legacy_dir = os.path.join(temp_dir, "legacy")
            user_data_dir = os.path.join(temp_dir, "user-data")
            os.makedirs(legacy_dir)
            legacy_path = os.path.join(legacy_dir, "config.json")
            config_path = os.path.join(user_data_dir, "config.json")
            filesystem.atomic_write_json(
                legacy_path,
                {
                    "skills_dir": "D:/skills",
                    "projects": [{"name": "demo", "path": "D:/demo"}],
                    "language": "en",
                },
            )
            repository = ConfigRepository(
                config_path,
                legacy_dir,
                ("codex",),
            )

            migrated = repository.load()

            self.assertEqual(migrated["language"], "en")
            self.assertEqual(migrated["projects"][0]["name"], "demo")
            self.assertEqual(migrated["global_skill_targets"], ["codex"])
            self.assertTrue(os.path.isfile(config_path))

    def test_chat_application_service_is_independent_of_pywebview(self):
        repository = InMemorySessionRepository()
        service = ChatSessionService(
            repository,
            language="en",
            clock=lambda: "2026-08-05T12:00:00",
        )
        saved = service.save_session("session-1", "", [{"role": "user"}])
        self.assertTrue(saved["ok"])
        self.assertEqual(saved["id"], "session-1")
        self.assertIn("summary", saved["metadata"])
        self.assertEqual(service.list_sessions()[0]["title"], "New Chat")
        self.assertEqual(
            service.load_session("session-1")["session"]["messages"],
            [{"role": "user"}],
        )

    def test_filesystem_layer_rejects_traversal_and_writes_atomically(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
            self.assertEqual(filesystem.safe_child_path(temp_dir, "..\\escape"), "")
            target = os.path.join(temp_dir, "state", "value.json")
            filesystem.atomic_write_json(target, {"ok": True})
            self.assertEqual(filesystem.load_json_file(target, {}), {"ok": True})


if __name__ == "__main__":
    unittest.main()
