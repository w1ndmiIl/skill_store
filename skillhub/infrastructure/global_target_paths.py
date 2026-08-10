"""Global target paths, descriptors, and read-only publication state."""

import hashlib
import os
import re

from skillhub.domain.frontmatter import split_markdown_frontmatter
from skillhub.domain.global_targets import (
    CODEX_ADAPTER_MANIFEST,
    DEFAULT_GLOBAL_SKILL_TARGETS,
    FORCE_PORTABLE_NAME_TARGETS,
    GLOBAL_SKILL_TARGETS,
    SKILL_LIBRARY_STATE_DIR,
    normalize_global_skill_targets,
)
from skillhub.domain.naming import normalize_agent_skill_name
from skillhub.infrastructure.filesystem import (
    get_tree_sha256,
    is_path_reparse_point,
    load_json_file,
    safe_child_path,
    safe_real_child_path,
)


class GlobalTargetPathsMixin:
    """Resolve portable client targets and report their managed state."""

    @staticmethod
    def _normalize_global_skill_targets(targets) -> list:
        return normalize_global_skill_targets(targets)

    def _configured_global_target_ids(self) -> list:
        configured = getattr(
            self, "global_skill_targets", list(DEFAULT_GLOBAL_SKILL_TARGETS)
        )
        normalized = self._normalize_global_skill_targets(configured)
        return normalized or list(DEFAULT_GLOBAL_SKILL_TARGETS)

    def _global_skill_target_dir(self, target_id: str) -> str:
        definition = GLOBAL_SKILL_TARGETS.get(target_id, {})
        if definition.get("kind") != "link":
            return ""
        overrides = getattr(self, "_global_skill_target_dir_overrides", {})
        if isinstance(overrides, dict) and overrides.get(target_id):
            return os.path.abspath(overrides[target_id])
        if target_id == "codex":
            legacy_override = getattr(
                self, "_codex_global_skills_dir_override", ""
            )
            if legacy_override:
                return os.path.abspath(legacy_override)
            codex_home = os.environ.get("CODEX_HOME") or os.path.join(
                os.path.expanduser("~"), ".codex"
            )
            return os.path.abspath(os.path.join(codex_home, "skills"))
        return os.path.join(
            os.path.expanduser("~"), *definition.get("path_parts", ())
        )

    def _global_skill_target_available(self, target_id: str) -> bool:
        """Return whether a client-owned Skill directory already exists.

        SkillHub may add managed entries inside a detected client directory, but
        it must not manufacture that directory for a client that is not present.
        Export-only targets remain available because they do not write into a
        client-owned path.
        """
        definition = GLOBAL_SKILL_TARGETS.get(target_id, {})
        if definition.get("kind") == "export":
            return True
        target_dir = self._global_skill_target_dir(target_id)
        return bool(target_dir and os.path.isdir(target_dir))

    def _legacy_codex_global_skills_dir(self) -> str:
        """Return the pre-3.3.2 SkillHub Codex target for safe migration."""
        override = getattr(self, "_legacy_codex_global_skills_dir_override", "")
        if override:
            return os.path.abspath(override)
        return os.path.join(os.path.expanduser("~"), ".agents", "skills")

    def _claude_desktop_export_root(self) -> str:
        return os.path.join(
            self.skills_dir,
            SKILL_LIBRARY_STATE_DIR,
            "exports",
            "claude-desktop",
        )

    def _global_skill_target_options(self) -> list:
        options = []
        for target_id, definition in GLOBAL_SKILL_TARGETS.items():
            kind = definition["kind"]
            options.append({
                "id": target_id,
                "label": definition["label"],
                "kind": kind,
                "available": self._global_skill_target_available(target_id),
                "path": (
                    self._global_skill_target_dir(target_id)
                    if kind == "link"
                    else self._claude_desktop_export_root()
                ),
                "requires_manual_install": kind == "export",
            })
        return options

    def _codex_global_skills_dir(self) -> str:
        """Return Codex's per-user Skill directory.

        Tests may set ``_codex_global_skills_dir_override`` so global-link
        behavior can be verified without touching the real user directory.
        """
        return self._global_skill_target_dir("codex")

    @staticmethod
    def _same_real_path(first: str, second: str) -> bool:
        if not first or not second:
            return False
        return os.path.normcase(os.path.realpath(first)) == os.path.normcase(
            os.path.realpath(second)
        )

    def _codex_global_adapter_root(self) -> str:
        return os.path.join(
            self.skills_dir,
            SKILL_LIBRARY_STATE_DIR,
            "codex-global",
        )

    def _codex_standard_adapter_root(self) -> str:
        """Store Codex-only normalized views beside the D-drive Skill library."""
        return self._target_standard_adapter_root("codex")

    def _target_standard_adapter_root(self, target_id: str) -> str:
        safe_target = re.sub(r"[^a-z0-9-]+", "-", target_id.casefold()).strip("-")
        return os.path.join(
            self.skills_dir,
            SKILL_LIBRARY_STATE_DIR,
            f"{safe_target}-standard",
        )

    def _codex_global_entry_name(self, filename: str, source: str, parent="") -> str:
        """Return a stable Codex package name for an adapted Skill."""
        source_name = os.path.splitext(os.path.basename(source))[0]
        seed = "-".join(part for part in (parent, source_name) if part)
        ascii_slug = re.sub(r"[^a-z0-9]+", "-", seed.casefold()).strip("-")
        if not ascii_slug:
            ascii_slug = "skill"
        digest = hashlib.sha256(filename.encode("utf-8")).hexdigest()[:8]
        return f"skillhub-{ascii_slug[:40].strip('-')}-{digest}"

    def _codex_global_skill_descriptor(self, filename: str, source="") -> dict:
        """Resolve any executable Skill format to a Codex package descriptor."""
        parent = ""
        if filename.startswith("@bundle:"):
            virtual = self._resolve_virtual_skill(filename)
            source = virtual.get("path", "")
            parent = virtual.get("parent", "")
        elif not source:
            source = safe_child_path(self.skills_dir, filename)
        if not source or not os.path.exists(source):
            return {}

        if os.path.isdir(source):
            skill_file = os.path.join(source, "SKILL.md")
            if os.path.isfile(skill_file):
                entry_name = os.path.basename(source)
                try:
                    with open(skill_file, "r", encoding="utf-8") as handle:
                        source_content = handle.read()
                    source_frontmatter, _source_body = split_markdown_frontmatter(
                        source_content
                    )
                except OSError:
                    source_frontmatter = {}
                portable_name = normalize_agent_skill_name(
                    source_frontmatter.get("name") or entry_name,
                    entry_name,
                )
                target_entry_names = {
                    target_id: portable_name
                    for target_id in FORCE_PORTABLE_NAME_TARGETS
                }
                target_adapter_paths = {
                    target_id: safe_real_child_path(
                        self._target_standard_adapter_root(target_id),
                        target_entry_names.get(target_id, entry_name),
                    )
                    for target_id in GLOBAL_SKILL_TARGETS
                }
                if not all(target_adapter_paths.values()):
                    return {}
                return {
                    "filename": filename,
                    "source": source,
                    "source_root": source,
                    "entry_file": skill_file,
                    "entry_name": entry_name,
                    "link_source": source,
                    "adapted": False,
                    "codex_link_source": target_adapter_paths["codex"],
                    "codex_adapted": True,
                    "target_entry_names": target_entry_names,
                    "target_adapter_paths": target_adapter_paths,
                }
            readme_file = os.path.join(source, "README.md")
            if not os.path.isfile(readme_file):
                return {}
            entry_file = readme_file
            source_root = source
        elif os.path.isfile(source) and source.lower().endswith(".md"):
            entry_file = source
            source_root = source
        else:
            return {}

        naming_source = source if os.path.isdir(source) else entry_file
        entry_name = self._codex_global_entry_name(filename, naming_source, parent)
        adapter = safe_real_child_path(self._codex_global_adapter_root(), entry_name)
        target_adapter_paths = {
            target_id: safe_real_child_path(
                self._target_standard_adapter_root(target_id), entry_name
            )
            for target_id in GLOBAL_SKILL_TARGETS
        }
        if not adapter or not all(target_adapter_paths.values()):
            return {}
        return {
            "filename": filename,
            "source": source,
            "source_root": source_root,
            "entry_file": entry_file,
            "entry_name": entry_name,
            "link_source": adapter,
            "adapted": True,
            "codex_link_source": target_adapter_paths["codex"],
            "codex_adapted": True,
            "target_entry_names": {
                target_id: entry_name
                for target_id in FORCE_PORTABLE_NAME_TARGETS
            },
            "target_adapter_paths": target_adapter_paths,
        }

    def _codex_global_source_hash(self, descriptor: dict) -> str:
        source_root = descriptor.get("source_root", "")
        if not source_root or not os.path.exists(source_root):
            return ""
        return get_tree_sha256(source_root)

    @staticmethod
    def _global_target_entry_name(descriptor: dict, target_id: str) -> str:
        return descriptor.get("target_entry_names", {}).get(
            target_id, descriptor.get("entry_name", "")
        )

    @staticmethod
    def _global_target_link_source(descriptor: dict, target_id: str) -> str:
        if target_id in GLOBAL_SKILL_TARGETS:
            return descriptor.get("target_adapter_paths", {}).get(
                target_id,
                descriptor.get("codex_link_source", "")
                if target_id == "codex" else "",
            )
        return descriptor.get("link_source", "")

    @staticmethod
    def _global_target_uses_adapter(descriptor: dict, target_id: str) -> bool:
        return target_id in GLOBAL_SKILL_TARGETS

    def _legacy_codex_global_target(self, descriptor: dict) -> str:
        return safe_child_path(
            self._legacy_codex_global_skills_dir(), descriptor["entry_name"]
        )

    def _is_managed_codex_source(self, path: str, descriptor: dict) -> bool:
        candidates = {
            descriptor.get("source", ""),
            descriptor.get("link_source", ""),
            descriptor.get("codex_link_source", ""),
            *descriptor.get("target_adapter_paths", {}).values(),
        }
        return any(
            candidate and self._same_real_path(path, candidate)
            for candidate in candidates
        )

    def _global_target_state(
        self,
        descriptor: dict,
        target_id: str,
        source_hash_getter=None,
    ) -> dict:
        definition = GLOBAL_SKILL_TARGETS.get(target_id, {})
        kind = definition.get("kind", "")
        available = self._global_skill_target_available(target_id)
        state = {
            "id": target_id,
            "label": definition.get("label", target_id),
            "kind": kind,
            "available": available,
            "enabled": False,
            "status": "disabled",
            "managed": False,
            "target": "",
            "requires_manual_install": kind == "export",
        }
        if not definition:
            state["status"] = "invalid"
            return state

        def current_source_hash() -> str:
            if source_hash_getter is not None:
                return source_hash_getter()
            return self._codex_global_source_hash(descriptor)

        if kind == "export":
            export_root = self._claude_desktop_export_root()
            package_path = safe_child_path(
                export_root,
                f'{self._global_target_entry_name(descriptor, target_id)}.zip',
            )
            manifest_path = safe_child_path(
                export_root,
                f'{self._global_target_entry_name(descriptor, target_id)}.json',
            )
            if not package_path or not manifest_path:
                state["status"] = "invalid"
                return state
            state["target"] = package_path
            if not os.path.isfile(package_path):
                return state
            manifest = load_json_file(manifest_path, {})
            state.update({"enabled": True, "status": "enabled", "managed": True})
            if manifest.get("source_hash") != current_source_hash():
                state["status"] = "outdated"
            return state

        target_dir = self._global_skill_target_dir(target_id)
        target = safe_child_path(
            target_dir, self._global_target_entry_name(descriptor, target_id)
        )
        if not target:
            state["status"] = "invalid"
            return state
        state["target"] = target
        if not os.path.lexists(target):
            if target_id == "codex":
                legacy_target = self._legacy_codex_global_target(descriptor)
                if (
                    legacy_target
                    and os.path.lexists(legacy_target)
                    and is_path_reparse_point(legacy_target)
                    and self._is_managed_codex_source(legacy_target, descriptor)
                ):
                    state.update({
                        "enabled": True,
                        "status": "legacy",
                        "managed": True,
                        "legacy_target": legacy_target,
                    })
            if not state["enabled"] and not available:
                state["status"] = "unavailable"
            return state
        expected_source = self._global_target_link_source(descriptor, target_id)
        if not self._same_real_path(target, expected_source):
            if (
                is_path_reparse_point(target)
                and self._is_managed_codex_source(target, descriptor)
            ):
                state.update({
                    "enabled": True,
                    "status": "legacy",
                    "managed": True,
                })
                return state
            state["status"] = "conflict"
            return state
        state.update({
            "enabled": True,
            "status": "enabled",
            "managed": is_path_reparse_point(target),
        })
        if self._global_target_uses_adapter(descriptor, target_id):
            manifest = load_json_file(
                os.path.join(expected_source, CODEX_ADAPTER_MANIFEST), {}
            )
            if manifest.get("source_hash") != current_source_hash():
                state["status"] = "outdated"
        return state

    def _codex_global_skill_state(self, filename: str, source="") -> dict:
        """Describe aggregate state across configured global Skill targets."""
        descriptor = self._codex_global_skill_descriptor(filename, source)
        compatible = bool(descriptor)
        state = {
            "codex_global_compatible": compatible,
            "codex_global_enabled": False,
            "codex_global_status": "unsupported" if not compatible else "disabled",
            "codex_global_managed": False,
            "codex_global_target": "",
            "codex_global_entry_name": descriptor.get("entry_name", ""),
            "codex_global_adapted": bool(
                descriptor.get("adapted") or descriptor.get("codex_adapted")
            ),
            "global_target_states": [],
            "global_target_ids": self._configured_global_target_ids(),
        }
        if not compatible:
            return state

        source_hash = []

        def current_source_hash() -> str:
            if not source_hash:
                source_hash.append(self._codex_global_source_hash(descriptor))
            return source_hash[0]

        target_states = [
            self._global_target_state(
                descriptor,
                target_id,
                source_hash_getter=current_source_hash,
            )
            for target_id in GLOBAL_SKILL_TARGETS
        ]
        state["global_target_states"] = target_states
        state["codex_global_target"] = (
            target_states[0]["target"] if target_states else ""
        )
        enabled_targets = [target for target in target_states if target["enabled"]]
        if any(target["status"] == "outdated" for target in enabled_targets):
            aggregate = "outdated"
        elif enabled_targets:
            aggregate = "enabled"
        else:
            aggregate = "disabled"
        state.update({
            "codex_global_enabled": aggregate == "enabled",
            "codex_global_status": aggregate,
            "codex_global_managed": bool(enabled_targets) and all(
                target["managed"] for target in enabled_targets
            ),
        })
        return state
