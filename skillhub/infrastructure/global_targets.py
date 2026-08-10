"""Transactional global publication, reconciliation, and rollback operations."""

import os
import shutil
from skillhub.domain.global_targets import GLOBAL_SKILL_TARGETS
from skillhub.infrastructure.filesystem import (
    is_path_reparse_point,
    safe_child_path,
)
from skillhub.infrastructure.global_adapters import GlobalAdaptersMixin
from skillhub.infrastructure.global_target_paths import GlobalTargetPathsMixin


class GlobalTargetService(GlobalTargetPathsMixin, GlobalAdaptersMixin):
    """Reconcile per-Skill target selections with rollback on partial failure."""


























    def _set_global_skill_target(
        self,
        filename: str,
        enabled: bool,
        target_id: str,
        source="",
        descriptor=None,
    ) -> dict:
        descriptor = descriptor or self._codex_global_skill_descriptor(
            filename, source
        )
        if not descriptor or target_id not in GLOBAL_SKILL_TARGETS:
            return {"error": "Invalid global Skill target"}
        target_state = self._global_target_state(descriptor, target_id)
        if target_state["status"] == "conflict":
            return {
                "error": (
                    f'A different Skill already uses this name in '
                    f'{target_state["label"]}'
                ),
                "target": target_state,
            }
        if (
            enabled
            and target_state["kind"] == "link"
            and not target_state.get("available", False)
        ):
            return {
                "error": (
                    f'{target_state["label"]} Skill directory was not detected; '
                    "SkillHub will not create it automatically"
                ),
                "target": target_state,
            }
        try:
            if enabled and target_state["kind"] == "link":
                self._write_codex_standard_adapter(descriptor, target_id)
                target_state = self._global_target_state(descriptor, target_id)

            if target_state["kind"] == "export":
                package_path = target_state["target"]
                manifest_path = os.path.splitext(package_path)[0] + ".json"
                if enabled:
                    self._write_claude_desktop_export(descriptor)
                else:
                    for generated in (package_path, manifest_path):
                        if os.path.isfile(generated):
                            os.remove(generated)
            elif enabled:
                if target_state["status"] == "legacy":
                    if os.path.lexists(target_state["target"]):
                        os.rmdir(target_state["target"])
                    self._create_codex_global_link(
                        self._global_target_link_source(descriptor, target_id),
                        target_state["target"],
                    )
                elif target_state["status"] not in ("enabled", "outdated"):
                    if os.path.lexists(target_state["target"]):
                        return {"ok": True, "target": target_state}
                    self._create_codex_global_link(
                        self._global_target_link_source(descriptor, target_id),
                        target_state["target"],
                    )
            else:
                target = target_state["target"]
                if os.path.lexists(target):
                    if target_state["status"] not in ("enabled", "outdated"):
                        return {
                            "error": (
                                f'Refusing to remove a different Skill from '
                                f'{target_state["label"]}'
                            ),
                            "target": target_state,
                        }
                    if not target_state["managed"]:
                        return {
                            "error": (
                                f'The {target_state["label"]} entry is a real '
                                "directory, not a removable SkillHub link"
                            ),
                            "target": target_state,
                        }
                    if os.path.islink(target):
                        os.unlink(target)
                    else:
                        os.rmdir(target)

            if target_id == "codex":
                legacy_target = self._legacy_codex_global_target(descriptor)
                if (
                    legacy_target
                    and os.path.lexists(legacy_target)
                    and is_path_reparse_point(legacy_target)
                    and self._is_managed_codex_source(legacy_target, descriptor)
                ):
                    os.rmdir(legacy_target)
        except Exception as error:
            return {"error": str(error), "target": target_state}
        return {
            "ok": True,
            "target": self._global_target_state(descriptor, target_id),
        }

    def _codex_global_adapter_in_use(self, descriptor: dict) -> bool:
        if not descriptor.get("adapted"):
            return False
        legacy_adapter = descriptor.get("link_source", "")
        for target_id in GLOBAL_SKILL_TARGETS:
            state = self._global_target_state(descriptor, target_id)
            if (
                state["enabled"]
                and state["kind"] == "link"
                and legacy_adapter
                and self._same_real_path(state["target"], legacy_adapter)
            ):
                return True
        return False

    def _cleanup_unused_global_adapters(self, descriptor: dict) -> None:
        for target_id, adapter in descriptor.get(
            "target_adapter_paths", {}
        ).items():
            target_state = self._global_target_state(descriptor, target_id)
            if (
                not target_state["enabled"]
                and adapter
                and os.path.isdir(adapter)
                and not is_path_reparse_point(adapter)
            ):
                shutil.rmtree(adapter)
        if (
            descriptor.get("adapted")
            and not self._codex_global_adapter_in_use(descriptor)
            and os.path.isdir(descriptor["link_source"])
            and not is_path_reparse_point(descriptor["link_source"])
        ):
            shutil.rmtree(descriptor["link_source"])

    def set_codex_global_skill(self, filename: str, enabled: bool) -> dict:
        """Enable or remove a library Skill across configured global targets."""
        source = "" if filename.startswith("@bundle:") else safe_child_path(
            self.skills_dir, filename
        )
        if not filename.startswith("@bundle:") and (
            not source or os.path.basename(source) != filename
        ):
            return {"error": "Invalid filename"}
        descriptor = self._codex_global_skill_descriptor(filename, source)
        initial_state = self._codex_global_skill_state(filename, source)
        if not initial_state["codex_global_compatible"]:
            return {"error": "This entry cannot be adapted to a Codex Skill"}
        changed_targets = []
        target_ids = self._configured_global_target_ids()
        if enabled:
            target_ids = [
                target_id for target_id in target_ids
                if self._global_skill_target_available(target_id)
            ]
            if not target_ids:
                return {
                    "error": (
                        "No configured Agent Skill directory was detected; "
                        "SkillHub will not create one automatically"
                    ),
                    **initial_state,
                }
        for target_id in target_ids:
            result = self._set_global_skill_target(
                filename, bool(enabled), target_id, source, descriptor
            )
            if result.get("error"):
                for changed_id in reversed(changed_targets):
                    previous = next(
                        (
                            target for target in initial_state["global_target_states"]
                            if target["id"] == changed_id
                        ),
                        {},
                    )
                    self._set_global_skill_target(
                        filename,
                        bool(previous.get("enabled")),
                        changed_id,
                        source,
                        descriptor,
                    )
                return {"error": result["error"], **initial_state}
            changed_targets.append(target_id)

        if not enabled:
            self._cleanup_unused_global_adapters(descriptor)

        updated = self._codex_global_skill_state(filename, source)
        return {"ok": True, **updated}

    def set_codex_global_skills(self, filenames: list, enabled: bool) -> dict:
        """Apply a collection-sized global change with best-effort rollback."""
        requested = list(dict.fromkeys(
            str(filename) for filename in (filenames or []) if filename
        ))
        if not requested or len(requested) > 100:
            return {"error": "Invalid Skill list"}
        original = {
            filename: {
                target["id"]: bool(target["enabled"])
                for target in self._codex_global_skill_state(filename).get(
                    "global_target_states", []
                )
            }
            for filename in requested
        }
        changed = []
        for filename in requested:
            result = self.set_codex_global_skill(filename, bool(enabled))
            if result.get("error"):
                rollback_errors = []
                for changed_name in reversed(changed):
                    descriptor = self._codex_global_skill_descriptor(changed_name)
                    for target_id, was_enabled in original[changed_name].items():
                        rollback = self._set_global_skill_target(
                            changed_name,
                            was_enabled,
                            target_id,
                            descriptor=descriptor,
                        )
                        if rollback.get("error"):
                            rollback_errors.append(rollback["error"])
                message = result["error"]
                if rollback_errors:
                    message += "; rollback failed: " + "; ".join(rollback_errors)
                return {"error": message, "failed": filename}
            if original[filename] != bool(enabled):
                changed.append(filename)
        return {"ok": True, "enabled": bool(enabled), "skills": requested}

    def set_skill_global_targets(self, filename: str, target_ids: list) -> dict:
        """Reconcile one Skill to an explicit per-Skill target selection."""
        desired = self._normalize_global_skill_targets(target_ids)
        source = "" if filename.startswith("@bundle:") else safe_child_path(
            self.skills_dir, filename
        )
        if not filename.startswith("@bundle:") and (
            not source or os.path.basename(source) != filename
        ):
            return {"error": "Invalid filename"}
        descriptor = self._codex_global_skill_descriptor(filename, source)
        if not descriptor:
            return {"error": "This entry cannot be adapted to an Agent Skill"}

        original = {
            target_id: self._global_target_state(descriptor, target_id)
            for target_id in GLOBAL_SKILL_TARGETS
        }
        changed = []
        for target_id in GLOBAL_SKILL_TARGETS:
            before = original[target_id]
            should_enable = target_id in desired
            needs_update = should_enable and before["status"] in (
                "outdated",
                "legacy",
            )
            if before["enabled"] == should_enable and not needs_update:
                continue
            result = self._set_global_skill_target(
                filename,
                should_enable,
                target_id,
                source,
                descriptor,
            )
            if result.get("error"):
                rollback_errors = []
                for changed_id in reversed(changed):
                    rollback = self._set_global_skill_target(
                        filename,
                        original[changed_id]["enabled"],
                        changed_id,
                        source,
                        descriptor,
                    )
                    if rollback.get("error"):
                        rollback_errors.append(rollback["error"])
                message = result["error"]
                if rollback_errors:
                    message += "; rollback failed: " + "; ".join(rollback_errors)
                return {"error": message, "failed_target": target_id}
            changed.append(target_id)

        self._cleanup_unused_global_adapters(descriptor)
        return {
            "ok": True,
            "selected_targets": desired,
            **self._codex_global_skill_state(filename, source),
        }

    def set_skills_global_targets(self, filenames: list, target_ids: list) -> dict:
        """Reconcile every member of a collection to the same target selection."""
        requested = list(dict.fromkeys(
            str(filename) for filename in (filenames or []) if filename
        ))
        if not requested or len(requested) > 100:
            return {"error": "Invalid Skill list"}
        desired = self._normalize_global_skill_targets(target_ids)
        original = {
            filename: [
                target["id"]
                for target in self._codex_global_skill_state(filename).get(
                    "global_target_states", []
                )
                if target["enabled"]
            ]
            for filename in requested
        }
        changed = []
        for filename in requested:
            result = self.set_skill_global_targets(filename, desired)
            if result.get("error"):
                rollback_errors = []
                for changed_name in reversed(changed):
                    rollback = self.set_skill_global_targets(
                        changed_name, original[changed_name]
                    )
                    if rollback.get("error"):
                        rollback_errors.append(rollback["error"])
                message = result["error"]
                if rollback_errors:
                    message += "; rollback failed: " + "; ".join(rollback_errors)
                return {"error": message, "failed": filename}
            changed.append(filename)
        return {"ok": True, "selected_targets": desired, "skills": requested}
