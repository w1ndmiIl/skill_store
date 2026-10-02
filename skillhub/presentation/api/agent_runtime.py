"""Agent runtime assembly and lifecycle endpoints."""

from agent_runtime import (
    AgentRuntime,
    OpenAICompatibleModel,
    ToolDefinition,
)


class AgentRuntimeApiMixin:
    """Assemble tools and expose bounded Agent task lifecycle operations."""

    @staticmethod
    def _agent_object_schema(properties, required=None):
        return {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        }

    def _agent_tools(self):
        object_schema = self._agent_object_schema
        return [
            ToolDefinition(
                "search_skills",
                "Search the local global Skill library by name, description, category, or tags.",
                object_schema({
                    "query": {"type": "string", "minLength": 1, "maxLength": 200},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30},
                }, ["query"]),
                self._tool_search_skills,
            ),
            ToolDefinition(
                "inspect_skill",
                "Read metadata and the necessary entry content of one global Skill.",
                object_schema({
                    "filename": {"type": "string", "minLength": 1, "maxLength": 240},
                    "max_chars": {"type": "integer", "minimum": 500, "maximum": 16000},
                }, ["filename"]),
                self._tool_inspect_skill,
            ),
            ToolDefinition(
                "audit_skill_library",
                "Audit the Skill library with deterministic rules; never modifies files.",
                object_schema({
                    "minimum_severity": {
                        "type": "string",
                        "enum": ["info", "warning", "error"],
                    },
                }),
                self._tool_audit_skill_library,
            ),
            ToolDefinition(
                "web_research",
                "Search the web for Skill authoring standards and return attributed sources.",
                object_schema({
                    "query": {"type": "string", "minLength": 2, "maxLength": 300},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 8},
                }, ["query"]),
                self._tool_web_research,
            ),
            ToolDefinition(
                "fetch_skillhub_install_guide",
                (
                    "Read the fixed official public document at "
                    "https://skillhub.cn/install/skillhub.md. Use this whenever "
                    "the user asks to follow that installation guide."
                ),
                object_schema({}),
                self._tool_fetch_skillhub_install_guide,
            ),
            ToolDefinition(
                "search_skillhub_catalog",
                (
                    "Search the official public SkillHub catalog and return "
                    "source, owner, exact slug, version, popularity, and API-key "
                    "requirements. This never installs anything."
                ),
                object_schema({
                    "query": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 200,
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                    },
                }, ["query"]),
                self._tool_search_skillhub_catalog,
            ),
            ToolDefinition(
                "preview_skillhub_catalog_install",
                (
                    "Download and safely stage one exact public SkillHub catalog "
                    "slug using the official registry semantics and the active "
                    "global Skill directory. Return hash-locked package evidence, "
                    "risk findings, and conflict choices without modifying the "
                    "global library."
                ),
                object_schema({
                    "slug": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 100,
                    },
                }, ["slug"]),
                self._tool_preview_skillhub_catalog_install,
            ),
            ToolDefinition(
                "draft_skill_change",
                "Create a read-only Skill change preview with target, summary, content, and diff.",
                object_schema({
                    "filename": {"type": "string", "minLength": 1, "maxLength": 240},
                    "summary": {"type": "string", "minLength": 1, "maxLength": 500},
                    "content": {"type": "string", "minLength": 1, "maxLength": 100000},
                }, ["filename", "summary", "content"]),
                self._tool_draft_skill_change,
            ),
            ToolDefinition(
                "preview_remote_skill_install",
                (
                    "Fetch and stage one exact public GitHub SKILL.md, validate its "
                    "frontmatter name, and return a hash-locked read-only install preview."
                ),
                object_schema({
                    "repository": {
                        "type": "string",
                        "minLength": 19,
                        "maxLength": 300,
                    },
                    "ref": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 120,
                    },
                    "skill_path": {
                        "type": "string",
                        "minLength": 16,
                        "maxLength": 500,
                    },
                    "install_name": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 100,
                    },
                }, ["repository", "skill_path", "install_name"]),
                self._tool_preview_remote_skill_install,
            ),
            ToolDefinition(
                "preview_remote_skill_collection",
                (
                    "Fetch a public GitHub repository archive and preview every "
                    "immediate skills/*/SKILL.md child as one SkillHub collection. "
                    "Repository may be a root URL or a /tree/<ref> URL. "
                    "Use this for repository-level goals; do not collapse the "
                    "repository to its default or first Skill."
                ),
                object_schema({
                    "repository": {
                        "type": "string",
                        "minLength": 19,
                        "maxLength": 300,
                    },
                    "ref": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 120,
                    },
                }, ["repository"]),
                self._tool_preview_remote_skill_collection,
            ),
            ToolDefinition(
                "preview_project_sync",
                "Preview project Skill synchronization without writing files.",
                object_schema({
                    "project_path": {"type": "string", "minLength": 1, "maxLength": 1000},
                    "enabled_skills": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1, "maxLength": 240},
                        "maxItems": 500,
                    },
                }, ["project_path", "enabled_skills"]),
                self._tool_preview_project_sync,
            ),
            ToolDefinition(
                "apply_skill_change",
                "Apply an approved Skill file change with a local backup when replacing a file.",
                object_schema({
                    "filename": {"type": "string", "minLength": 1, "maxLength": 240},
                    "content": {"type": "string", "minLength": 1, "maxLength": 100000},
                    "expected_target_exists": {"type": "boolean"},
                    "expected_before_sha256": {"type": "string", "minLength": 64, "maxLength": 64},
                    "expected_content_sha256": {"type": "string", "minLength": 64, "maxLength": 64},
                    "reason": {"type": "string", "minLength": 1, "maxLength": 500},
                }, [
                    "filename",
                    "content",
                    "expected_target_exists",
                    "expected_before_sha256",
                    "expected_content_sha256",
                    "reason",
                ]),
                self._tool_apply_skill_change,
                risk="write",
            ),
            ToolDefinition(
                "apply_remote_skill_install",
                (
                    "Install the exact bytes from a hash-locked remote Skill preview. "
                    "This is a high-risk write and requires explicit user approval."
                ),
                object_schema({
                    "preview_token": {
                        "type": "string",
                        "minLength": 32,
                        "maxLength": 32,
                    },
                    "install_name": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 100,
                    },
                    "expected_sha256": {
                        "type": "string",
                        "minLength": 64,
                        "maxLength": 64,
                    },
                    "replace_existing": {"type": "boolean"},
                    "reason": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                    },
                }, [
                    "preview_token",
                    "install_name",
                    "expected_sha256",
                    "replace_existing",
                    "reason",
                ]),
                self._tool_apply_remote_skill_install,
                risk="write",
            ),
            ToolDefinition(
                "apply_skillhub_catalog_install",
                (
                    "Install the exact bytes from a hash-locked official SkillHub "
                    "catalog preview. Use conflict_strategy=install only for a new "
                    "target. Existing targets require the user's explicit choice "
                    "of replace or keep_both; cancellation uses approval rejection."
                ),
                object_schema({
                    "preview_token": {
                        "type": "string",
                        "minLength": 32,
                        "maxLength": 32,
                    },
                    "slug": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 100,
                    },
                    "expected_package_sha256": {
                        "type": "string",
                        "minLength": 64,
                        "maxLength": 64,
                    },
                    "expected_source_hash": {
                        "type": "string",
                        "minLength": 64,
                        "maxLength": 64,
                    },
                    "conflict_strategy": {
                        "type": "string",
                        "enum": ["install", "replace", "keep_both"],
                    },
                    "reason": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                    },
                }, [
                    "preview_token",
                    "slug",
                    "expected_package_sha256",
                    "expected_source_hash",
                    "conflict_strategy",
                    "reason",
                ]),
                self._tool_apply_skillhub_catalog_install,
                risk="write",
            ),
            ToolDefinition(
                "apply_remote_skill_collection",
                (
                    "Install all non-duplicate children from an approved, "
                    "hash-locked remote repository collection preview. This is "
                    "a high-risk write and requires explicit user approval."
                ),
                object_schema({
                    "preview_token": {
                        "type": "string",
                        "minLength": 32,
                        "maxLength": 32,
                    },
                    "expected_archive_sha256": {
                        "type": "string",
                        "minLength": 64,
                        "maxLength": 64,
                    },
                    "expected_source_hash": {
                        "type": "string",
                        "minLength": 64,
                        "maxLength": 64,
                    },
                    "expected_collection_count": {
                        "type": "integer",
                        "minimum": 2,
                        "maximum": 200,
                    },
                    "accept_high_risk": {"type": "boolean"},
                    "accept_collection_conflicts": {"type": "boolean"},
                    "reason": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 500,
                    },
                }, [
                    "preview_token",
                    "expected_archive_sha256",
                    "expected_source_hash",
                    "expected_collection_count",
                    "accept_high_risk",
                    "accept_collection_conflicts",
                    "reason",
                ]),
                self._tool_apply_remote_skill_collection,
                risk="write",
            ),
            ToolDefinition(
                "apply_project_sync",
                "Apply an exact approved project synchronization preview.",
                object_schema({
                    "project_path": {"type": "string", "minLength": 1, "maxLength": 1000},
                    "enabled_skills": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1, "maxLength": 240},
                        "maxItems": 500,
                    },
                    "plan_token": {"type": "string", "minLength": 64, "maxLength": 64},
                    "allow_conflicts": {"type": "boolean"},
                    "allow_bundle_files": {"type": "boolean"},
                }, ["project_path", "enabled_skills", "plan_token"]),
                self._tool_apply_project_sync,
                risk="write",
            ),
            ToolDefinition(
                "recall_memory",
                "Recall only memories relevant to the current SkillOps task.",
                object_schema({
                    "query": {"type": "string", "minLength": 1, "maxLength": 500},
                    "project_path": {"type": "string", "maxLength": 1000},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 12},
                }, ["query"]),
                lambda arguments: {
                    "ok": True,
                    "memories": self._agent_memory.recall(
                        arguments["query"],
                        project_path=arguments.get("project_path", ""),
                        limit=arguments.get("limit", 6),
                    ),
                },
            ),
            ToolDefinition(
                "remember_memory",
                "Persist a concise project fact, user preference, or decision. Never store secrets or full sensitive files.",
                object_schema({
                    "kind": {
                        "type": "string",
                        "enum": ["project", "preference", "decision"],
                    },
                    "summary": {"type": "string", "minLength": 1, "maxLength": 1200},
                    "project_path": {"type": "string", "maxLength": 1000},
                }, ["kind", "summary"]),
                lambda arguments: self._agent_memory.remember(
                    arguments["kind"],
                    arguments["summary"],
                    project_path=arguments.get("project_path", ""),
                    source="user_request",
                ),
            ),
        ]

    def _agent_runtime(self):
        model = OpenAICompatibleModel(
            self.deepseek_api_key,
            self.deepseek_model,
            self.api_base,
            reasoning_effort=getattr(self, "ai_reasoning_effort", "high"),
        )
        return AgentRuntime(
            model,
            self._agent_tools(),
            self._agent_tasks,
            self._agent_memory,
            self._agent_recorder,
            max_steps=32,
            language=self.language,
        )

    def _agent_conversation_context(self, session_id):
        """Load persisted history for one chat without trusting client payloads."""
        session_id = str(session_id or "").strip()
        if not session_id:
            return []
        try:
            loaded = self._chat_session_service().load_session(session_id)
        except (AttributeError, OSError, TypeError, ValueError):
            return []
        session = loaded.get("session") if isinstance(loaded, dict) else None
        messages = session.get("messages") if isinstance(session, dict) else None
        return messages if isinstance(messages, list) else []

    def agent_start(self, goal, session_id="", project_path=""):
        if not self.deepseek_api_key:
            return {
                "error": (
                    "请先配置 API Key；SkillOps Agent 必须使用支持 Function Calling 的模型。"
                    if self.language == "zh"
                    else "Configure an API key for a model that supports Function Calling."
                )
            }
        return self._agent_runtime().start(
            goal,
            session_id=session_id,
            project_path=project_path,
            conversation_context=self._agent_conversation_context(session_id),
        )

    def agent_resume(self, run_id):
        if not self.deepseek_api_key:
            return {"error": "请先配置 API Key"}
        return self._agent_runtime().resume(run_id)

    def agent_approve(self, run_id, approval_id=""):
        if not self.deepseek_api_key:
            return {"error": "请先配置 API Key"}
        return self._agent_runtime().approve(run_id, approval_id)

    def agent_reject(self, run_id, reason=""):
        return self._agent_runtime().reject(run_id, reason)

    def agent_get_task(self, run_id):
        return self._agent_runtime().get(run_id)

    def agent_list_tasks(self):
        return self._agent_tasks.list_public()

    def agent_memory_view(self):
        return self._agent_memory.public_view()

    def agent_memory_set_enabled(self, enabled):
        return self._agent_memory.set_enabled(bool(enabled))

    def agent_memory_clear(self):
        return self._agent_memory.clear()
