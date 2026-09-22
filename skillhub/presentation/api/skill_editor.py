"""First-class editing for SKILL.md and usage-affecting OpenAI metadata."""

import os
import re
import hashlib
import difflib
import uuid
from skillhub.settings import USER_DATA_DIR
from skillhub.infrastructure.filesystem import atomic_write_json
from skillhub.infrastructure.json_store import file_lock

import yaml

from skillhub.domain.catalog import parse_markdown_metadata
from skillhub.infrastructure.filesystem import atomic_write_text, safe_real_child_path


class SkillEditorApiMixin:
    """Read, validate, and jointly save editable Skill package sources."""

    OPENAI_TOOL_FIELDS = (
        "type",
        "value",
        "description",
        "transport",
        "url",
    )

    def _skill_editor_files(self, filename: str) -> dict:
        source = self._editable_skill_source(filename)
        skill_path = source.get("path", "")
        if not skill_path:
            return {}
        result = {
            "skill_path": skill_path,
            "openai_yaml_path": "",
            "openai_yaml_supported": False,
        }
        if os.path.basename(skill_path).casefold() != "skill.md":
            return result
        package_root = os.path.dirname(skill_path)
        metadata_path = safe_real_child_path(
            package_root,
            os.path.join("agents", "openai.yaml"),
        )
        if metadata_path:
            result["openai_yaml_path"] = metadata_path
            result["openai_yaml_supported"] = True
        return result

    def _default_openai_yaml(self, filename: str, skill_path: str) -> str:
        metadata = parse_markdown_metadata(skill_path)
        package_name = os.path.basename(os.path.dirname(skill_path))
        invocation_name = re.sub(
            r"[^a-z0-9]+",
            "-",
            package_name.casefold(),
        ).strip("-") or "skill"
        display_name = str(metadata.get("title") or package_name or filename).strip()
        description = str(metadata.get("description") or "").strip()
        prompt = (
            f"使用 ${invocation_name} 完成当前任务。"
            if self.language == "zh"
            else f"Use ${invocation_name} for the current task."
        )
        content = {
            "interface": {
                "display_name": display_name,
                "short_description": description,
                "default_prompt": prompt,
            },
            "policy": {"allow_implicit_invocation": True},
        }
        rendered = yaml.safe_dump(
            content,
            allow_unicode=True,
            sort_keys=False,
            width=1000,
        )
        return rendered + (
            "\n# Optional tool dependencies:\n"
            "# dependencies:\n"
            "#   tools:\n"
            "#     - type: mcp\n"
            "#       value: tool-name\n"
            "#       description: Explain why this tool is required.\n"
        )

    def export_editor_draft(self, filename, editor_data):
        if not isinstance(editor_data, dict) or not all(isinstance(editor_data.get(k, ""), str) for k in ("skill_content", "openai_yaml_content")):
            return {"error": "Invalid draft"}
        path = os.path.join(USER_DATA_DIR, "editor-drafts", uuid.uuid4().hex + ".json")
        try:
            atomic_write_json(path, {"filename": str(filename), "skill_content": editor_data.get("skill_content", ""), "openai_yaml_content": editor_data.get("openai_yaml_content", "")})
            return {"ok": True, "path": path}
        except OSError as error:
            return {"error": str(error)}

    def _editor_version(self, files):
        result = {}
        for key in ("skill_path", "openai_yaml_path"):
            path = files.get(key)
            result[key] = None
            if path and os.path.isfile(path):
                with open(path, "rb") as handle:
                    result[key] = hashlib.sha256(handle.read()).hexdigest()
        return result

    def get_skill_editor_data(self, filename):
        with file_lock(self.skills_dir):
            files = self._skill_editor_files(filename)
            before = self._editor_version(files)
            result = self._get_skill_editor_data(filename)
            if before != self._editor_version(files):
                return {"error": "文件在加载期间变化，请重新打开 / File changed while loading"}
            return result

    def _get_skill_editor_data(self, filename):
        files = self._skill_editor_files(filename)
        skill_path = files.get("skill_path", "")
        if not skill_path or not os.path.isfile(skill_path):
            return {"error": "File not found"}
        try:
            with open(skill_path, "r", encoding="utf-8") as handle:
                skill_content = handle.read()
            metadata_path = files.get("openai_yaml_path", "")
            metadata_exists = bool(metadata_path and os.path.isfile(metadata_path))
            if metadata_exists:
                with open(metadata_path, "r", encoding="utf-8") as handle:
                    metadata_content = handle.read()
            elif files.get("openai_yaml_supported"):
                metadata_content = self._default_openai_yaml(filename, skill_path)
            else:
                metadata_content = ""
            form_result = (
                self.parse_openai_yaml_form(metadata_content)
                if metadata_content
                else {"form": {}}
            )
            return {
                "version": self._editor_version(files),
                "skill_content": skill_content,
                "openai_yaml_content": metadata_content,
                "openai_form": form_result.get("form", {}),
                "openai_form_error": form_result.get("error", ""),
                "openai_yaml_exists": metadata_exists,
                "openai_yaml_supported": bool(
                    files.get("openai_yaml_supported")
                ),
            }
        except Exception as error:
            return {"error": str(error)}

    @classmethod
    def _openai_form_from_document(cls, document: dict) -> dict:
        interface = document.get("interface") or {}
        policy = document.get("policy") or {}
        tools = (document.get("dependencies") or {}).get("tools") or []
        return {
            "display_name": str(interface.get("display_name") or ""),
            "short_description": str(interface.get("short_description") or ""),
            "default_prompt": str(interface.get("default_prompt") or ""),
            "allow_implicit_invocation": policy.get(
                "allow_implicit_invocation",
                True,
            ) is not False,
            "tools": [
                {
                    **{
                        field: str(tool.get(field) or "")
                        for field in cls.OPENAI_TOOL_FIELDS
                    },
                    "_source_index": index,
                }
                for index, tool in enumerate(tools)
                if isinstance(tool, dict)
            ],
        }

    def parse_openai_yaml_form(self, content):
        validation_error = self._validate_openai_yaml(content)
        if validation_error:
            return {"error": validation_error}
        document = yaml.safe_load(content) or {}
        return {"ok": True, "form": self._openai_form_from_document(document)}

    def render_openai_yaml_form(self, content, form_data):
        validation_error = self._validate_openai_yaml(content)
        if validation_error:
            return {"error": validation_error}
        if not isinstance(form_data, dict):
            return {"error": "Invalid OpenAI metadata form"}
        document = yaml.safe_load(content) or {}
        interface = document.setdefault("interface", {})
        policy = document.setdefault("policy", {})
        if not isinstance(interface, dict) or not isinstance(policy, dict):
            return {"error": "interface and policy must be YAML mappings"}

        for field in ("display_name", "short_description", "default_prompt"):
            value = form_data.get(field, "")
            if not isinstance(value, str):
                return {"error": f"{field} must be text"}
            if value.strip():
                interface[field] = value.strip()
            else:
                interface.pop(field, None)
        implicit = form_data.get("allow_implicit_invocation")
        if not isinstance(implicit, bool):
            return {"error": "allow_implicit_invocation must be true or false"}
        policy["allow_implicit_invocation"] = implicit

        requested_tools = form_data.get("tools", [])
        if not isinstance(requested_tools, list):
            return {"error": "tools must be a list"}
        dependencies = document.get("dependencies")
        if dependencies is None:
            dependencies = {}
        if not isinstance(dependencies, dict):
            return {"error": "dependencies must be a YAML mapping"}
        original_tools = dependencies.get("tools") or []
        rendered_tools = []
        for index, requested in enumerate(requested_tools):
            if not isinstance(requested, dict):
                return {"error": f"tools[{index}] must be an object"}
            source_index = requested.get("_source_index")
            existing = (
                dict(original_tools[source_index])
                if isinstance(source_index, int)
                and 0 <= source_index < len(original_tools)
                and isinstance(original_tools[source_index], dict)
                else {}
            )
            for field in self.OPENAI_TOOL_FIELDS:
                value = requested.get(field, "")
                if not isinstance(value, str):
                    return {"error": f"tools[{index}].{field} must be text"}
                if value.strip():
                    existing[field] = value.strip()
                else:
                    existing.pop(field, None)
            if not existing.get("type") or not existing.get("value"):
                return {"error": f"tools[{index}] requires type and value"}
            rendered_tools.append(existing)
        if rendered_tools:
            dependencies["tools"] = rendered_tools
            document["dependencies"] = dependencies
        else:
            dependencies.pop("tools", None)
            if dependencies:
                document["dependencies"] = dependencies
            else:
                document.pop("dependencies", None)

        rendered = yaml.safe_dump(
            document,
            allow_unicode=True,
            sort_keys=False,
            width=1000,
        )
        return {
            "ok": True,
            "content": rendered,
            "form": self._openai_form_from_document(document),
        }

    @staticmethod
    def _validate_openai_yaml(content: str) -> str:
        if not str(content or "").strip():
            return "agents/openai.yaml cannot be empty"
        try:
            document = yaml.safe_load(content)
        except yaml.YAMLError as error:
            return f"Invalid agents/openai.yaml: {error}"
        if not isinstance(document, dict):
            return "agents/openai.yaml must contain a YAML mapping"
        for section_name in ("interface", "policy"):
            section = document.get(section_name)
            if section is not None and not isinstance(section, dict):
                return f"{section_name} must be a YAML mapping"
        interface = document.get("interface") or {}
        for field in ("display_name", "short_description", "default_prompt"):
            value = interface.get(field)
            if value is not None and not isinstance(value, str):
                return f"interface.{field} must be a string"
        policy = document.get("policy") or {}
        implicit = policy.get("allow_implicit_invocation")
        if implicit is not None and not isinstance(implicit, bool):
            return "policy.allow_implicit_invocation must be true or false"
        dependencies = document.get("dependencies")
        if dependencies is not None and not isinstance(dependencies, dict):
            return "dependencies must be a YAML mapping"
        tools = (dependencies or {}).get("tools")
        if tools is not None:
            if not isinstance(tools, list):
                return "dependencies.tools must be a YAML list"
            for index, tool in enumerate(tools):
                if not isinstance(tool, dict):
                    return f"dependencies.tools[{index}] must be a YAML mapping"
                for field in SkillEditorApiMixin.OPENAI_TOOL_FIELDS:
                    value = tool.get(field)
                    if value is not None and not isinstance(value, str):
                        return f"dependencies.tools[{index}].{field} must be a string"
        return ""

    def save_skill_editor_data(self, filename, editor_data):
        with file_lock(self.skills_dir):
            return self._save_skill_editor_data(filename, editor_data)

    def _save_skill_editor_data(self, filename, editor_data):
        if not isinstance(editor_data, dict):
            return {"error": "Invalid editor data"}
        skill_content = editor_data.get("skill_content")
        metadata_content = editor_data.get("openai_yaml_content", "")
        save_metadata = editor_data.get("save_openai_yaml") is True
        if not isinstance(skill_content, str):
            return {"error": "SKILL.md content must be text"}
        if save_metadata and not isinstance(metadata_content, str):
            return {"error": "agents/openai.yaml content must be text"}

        files = self._skill_editor_files(filename)
        skill_path = files.get("skill_path", "")
        metadata_path = files.get("openai_yaml_path", "")
        expected = editor_data.get("expected_version")
        if expected is not None and expected != self._editor_version(files):
            return {"error": "文件已被外部修改，草稿已保留。 / File changed externally.",
                    "conflict": True, "current": self.get_skill_editor_data(filename),
                    "diff": "".join(difflib.unified_diff(
                        self.get_skill_editor_data(filename).get("skill_content", "").splitlines(True),
                        skill_content.splitlines(True), fromfile="Disk", tofile="Draft"))[:100000]}
        if not skill_path or not os.path.isfile(skill_path):
            return {"error": "File not found"}
        if save_metadata and not files.get("openai_yaml_supported"):
            return {"error": "This Skill does not support agents/openai.yaml"}
        if save_metadata:
            validation_error = self._validate_openai_yaml(metadata_content)
            if validation_error:
                return {"error": validation_error}

        try:
            with open(skill_path, "rb") as handle:
                original_skill = handle.read()
            metadata_existed = bool(metadata_path and os.path.isfile(metadata_path))
            original_metadata = b""
            if metadata_existed:
                with open(metadata_path, "rb") as handle:
                    original_metadata = handle.read()
        except OSError as error:
            return {"error": str(error)}

        try:
            if save_metadata:
                atomic_write_text(metadata_path, metadata_content)
            atomic_write_text(skill_path, skill_content)
            self._register_library_entry(filename, source="edited")
            return {
                "ok": True,
                "openai_yaml_saved": save_metadata,
                "openai_yaml_created": save_metadata and not metadata_existed,
            }
        except Exception as error:
            rollback_errors = []
            try:
                atomic_write_text(skill_path, original_skill.decode("utf-8"))
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
            if save_metadata:
                try:
                    if metadata_existed:
                        atomic_write_text(
                            metadata_path,
                            original_metadata.decode("utf-8"),
                        )
                    elif os.path.exists(metadata_path):
                        os.remove(metadata_path)
                except Exception as rollback_error:
                    rollback_errors.append(str(rollback_error))
            message = str(error)
            if rollback_errors:
                message += "; rollback failed: " + "; ".join(rollback_errors)
            return {"error": message}
