from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "static" / "index.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")


class FrontendUiQualityTests(unittest.TestCase):
    def test_inactive_dialogs_are_removed_from_focus_and_accessibility_trees(self):
        for modal_id in (
            "editor-modal",
            "collection-modal",
            "global-target-modal",
            "settings-modal",
            "ai-modal",
            "dialog-modal",
            "review-modal",
        ):
            self.assertIn(f'id="{modal_id}" class="modal-overlay"', HTML)
            self.assertRegex(
                HTML,
                rf'id="{modal_id}"[^>]*\binert\b',
                msg=f"{modal_id} must start inert",
            )
        self.assertIn("visibility:hidden", CSS.replace(" ", ""))
        self.assertIn("modal.inert = false", JS)
        self.assertIn("modal.inert = true", JS)

    def test_primary_controls_have_accessible_names_and_live_feedback(self):
        self.assertIn('id="toast-container" class="toast-container" role="status" aria-live="polite"', HTML)
        for control_id in (
            "settings-skills-dir",
            "settings-scan-dir",
            "settings-apibase",
            "settings-apikey",
            "settings-aimodel",
        ):
            self.assertIn(f'for="{control_id}"', HTML)
        self.assertIn('aria-labelledby="settings-label-ai-import"', HTML)
        self.assertIn('aria-labelledby="settings-label-ai-display-translation"', HTML)
        self.assertIn(".switch:focus-within", CSS)

    def test_narrow_layout_keeps_settings_and_prevents_horizontal_clipping(self):
        compact_css = CSS.replace(" ", "").replace("\n", "")
        self.assertIn(".skill-list-shell{min-width:0", compact_css)
        self.assertNotIn(".sidebar-footer{display:none}", compact_css)
        self.assertIn(".skills-dir-config,.service-status-row{display:none}", compact_css)
        self.assertIn("@media(max-width:820px)", compact_css)

    def test_agent_empty_state_starts_at_the_top_and_localizes_suggestions(self):
        self.assertIn("aiChatMessages.scrollTop = aiChatHistory.length", JS)
        self.assertIn("getAgentEmptyStateMarkup", JS)
        self.assertIn("agentSuggestionReview", JS)
        self.assertIn("window.innerWidth <= 820", JS)

    def test_project_mode_label_stays_inside_workspace_mode_scope(self):
        workspace_mode = JS.split("function updateWorkspaceMode()", 1)[1].split(
            "function handleShowLibrary()", 1
        )[0]
        category_renderer = JS.split("function renderCategoryFilterBar()", 1)[1].split(
            "window.handleSelectCategory", 1
        )[0]
        self.assertIn("const isProjectMode = Boolean(project)", workspace_mode)
        self.assertIn("const label = isProjectMode", workspace_mode)
        self.assertNotIn("isProjectMode", category_renderer)

    def test_advanced_interaction_components_are_present(self):
        self.assertIn('id="review-modal"', HTML)
        self.assertIn("showStructuredReview", JS)
        self.assertIn('id="editor-dirty-indicator"', HTML)
        self.assertIn("editorInitialSnapshot", JS)
        self.assertIn("category-more", JS)
        self.assertIn("getSkillListIcon", JS)
        self.assertIn("@media (prefers-reduced-motion: reduce)", CSS)
        self.assertIn("editorSourceBar.classList.add('viewer-workbench')", JS)
        self.assertIn("editorSourceSkill.parentElement.hidden = true", JS)
        self.assertIn("editorSourceBar.hidden = false", JS)


if __name__ == "__main__":
    unittest.main()
