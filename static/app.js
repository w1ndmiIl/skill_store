// ==========================================
// SkillHub - pywebview Frontend
// ==========================================

let projects = [];
let skills = [];
let currentProjectPath = null;
let enabledSkills = new Set();
let editingFilename = null;
let isViewingSkill = false;
let displaySkillsByFilename = new Map();
let activeCollectionId = null;
let pendingSyncSummary = null;
let pendingSyncRequestId = 0;
let pendingSyncTimer = null;
const modalReturnFocus = new WeakMap();
let categoryResizeTimer = null;

// i18n & Theme State
let currentLanguage = 'zh';
let currentTheme = 'light';
let defaultScanDir = '';
let deepseekApiKey = '';
let deepseekModel = 'deepseek-chat';
let apiBase = 'https://api.deepseek.com/v1';
let hasAiKey = false;
let apiKeyHint = '';
let aiImportOptimization = false;
let aiDisplayTranslation = false;
let globalSkillTargets = ['codex'];
let globalSkillTargetOptions = [];
let aiGeneratedSkill = null; // cached AI result
let activeCategoryFilter = null; // active category filter (null = show all)
let searchRenderTimer = null;
let activeDrawerFilename = null;
let drawerReturnFocus = null;
let loadedEditorCategory = '';
let pendingEditorCategories = new Set();
let pendingGlobalTargetSkill = null;
let activeEditorSource = 'skill';
let editorSkillContent = '';
let editorOpenaiYamlContent = '';
let editorOpenaiYamlInitialContent = '';
let editorOpenaiYamlExists = false;
let editorOpenaiYamlSupported = false;
let editorOpenaiYamlDirty = false;
let editorOpenaiYamlCreateRequested = false;
let openaiEditorMode = 'form';
let editorOpenaiForm = {};
let editorOpenaiFormDirty = false;
let editorOpenaiFormError = '';
let editorInitialSnapshot = null;
let editorClosePending = false;
let reviewResolve = null;

// DOM cache
const projectList = document.getElementById('project-list');
const cardsGrid = document.getElementById('cards-grid');
const syncBtn = document.getElementById('sync-btn');
const undoSyncBtn = document.getElementById('undo-sync-btn');
const currentProjectTitle = document.getElementById('current-project-title');
const currentProjectDesc = document.getElementById('current-project-desc');
const editorModal = document.getElementById('editor-modal');
const modalTitle = document.getElementById('modal-title');
const modalEmoji = document.getElementById('modal-emoji');
const modalBody = document.getElementById('modal-body');
const markdownTextarea = document.getElementById('markdown-textarea');
const markdownPreview = document.getElementById('markdown-preview');
const modalTabEdit = document.getElementById('modal-tab-edit');
const modalTabPreview = document.getElementById('modal-tab-preview');
const modalCloseFooter = document.getElementById('modal-close-footer');
const modalSaveBtn = document.getElementById('modal-save-btn');
const skillMetadataBar = document.getElementById('skill-metadata-bar');
const skillCategoryLabel = document.getElementById('skill-category-label');
const skillCategorySelect = document.getElementById('skill-category-select');
const skillCategoryAddLabel = document.getElementById('skill-category-add-label');
const skillCategoryDelete = document.getElementById('skill-category-delete');
const skillCategoryDeleteLabel = document.getElementById('skill-category-delete-label');
const skillCategoryHint = document.getElementById('skill-category-hint');
const editorSourceBar = document.getElementById('editor-source-bar');
const editorSourceSkill = document.getElementById('editor-source-skill');
const editorSourceOpenai = document.getElementById('editor-source-openai');
const editorOpenaiState = document.getElementById('editor-openai-state');
const editorSourceHint = document.getElementById('editor-source-hint');
const editorOpenaiHint = document.getElementById('editor-openai-hint');
const editorOpenaiHintTitle = document.getElementById('editor-openai-hint-title');
const editorOpenaiHintBody = document.getElementById('editor-openai-hint-body');
const editorOpenaiModeForm = document.getElementById('editor-openai-mode-form');
const editorOpenaiModeYaml = document.getElementById('editor-openai-mode-yaml');
const openaiFormEditor = document.getElementById('openai-form-editor');
const openaiDisplayName = document.getElementById('openai-display-name');
const openaiShortDescription = document.getElementById('openai-short-description');
const openaiDefaultPrompt = document.getElementById('openai-default-prompt');
const openaiToolsList = document.getElementById('openai-tools-list');
const openaiToolsEmpty = document.getElementById('openai-tools-empty');
const toastContainer = document.getElementById('toast-container');
const searchInput = document.getElementById('search-input');
const skillsDirPath = document.getElementById('skills-dir-path');
const toolbarStats = document.getElementById('toolbar-stats');
const categoryFilterBar = document.getElementById('category-filter-bar');
const collectionModal = document.getElementById('collection-modal');
const collectionModalTitle = document.getElementById('collection-modal-title');
const collectionModalSummary = document.getElementById('collection-modal-summary');
const collectionMembersList = document.getElementById('collection-members-list');
const collectionModalHint = document.getElementById('collection-modal-hint');
const navLibrary = document.getElementById('nav-library');
const navSkillCount = document.getElementById('nav-skill-count');
const workspaceKicker = document.getElementById('workspace-kicker');
const syncActionBar = document.getElementById('sync-action-bar');
const syncBarTitle = document.getElementById('sync-bar-title');
const syncBarSummary = document.getElementById('sync-bar-summary');
const skillDrawer = document.getElementById('skill-detail-drawer');
const skillDrawerBackdrop = document.getElementById('skill-drawer-backdrop');
const skillDetailEmoji = document.getElementById('skill-detail-emoji');
const skillDetailTitle = document.getElementById('skill-detail-title');
const skillDetailKind = document.getElementById('skill-detail-kind');
const skillDetailMeta = document.getElementById('skill-detail-meta');
const skillDetailContent = document.getElementById('skill-detail-content');
const skillDetailCodexGlobal = document.getElementById('skill-detail-codex-global');
const skillDetailEdit = document.getElementById('skill-detail-edit');
const skillDetailDelete = document.getElementById('skill-detail-delete');
const globalTargetModal = document.getElementById('global-target-modal');
const skillGlobalTargets = document.getElementById('skill-global-targets');
const appContainer = document.querySelector('.app-container');
const editorDirtyIndicator = document.getElementById('editor-dirty-indicator');
const skillDetailClose = document.getElementById('skill-detail-close');
const reviewModal = document.getElementById('review-modal');

function getModalFocusableElements(modal) {
  return Array.from(modal.querySelectorAll(
    'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
  )).filter(element => element.offsetParent !== null);
}

function activateModal(modal, preferredFocus = null) {
  if (!modal) return;
  if (!modal.classList.contains('active')) {
    modalReturnFocus.set(modal, document.activeElement);
  }
  modal.removeAttribute('inert');
  modal.inert = false;
  modal.classList.add('active');
  modal.setAttribute('aria-hidden', 'false');
  setTimeout(() => {
    const focusTarget = preferredFocus || getModalFocusableElements(modal)[0];
    if (focusTarget) focusTarget.focus();
  }, 0);
}

function deactivateModal(modal) {
  if (!modal) return;
  modal.classList.remove('active');
  modal.setAttribute('aria-hidden', 'true');
  modal.setAttribute('inert', '');
  modal.inert = true;
  const returnFocus = modalReturnFocus.get(modal);
  modalReturnFocus.delete(modal);
  if (returnFocus && document.contains(returnFocus)) {
    setTimeout(() => returnFocus.focus(), 0);
  }
}

function trapModalFocus(event, modal) {
  const focusable = getModalFocusableElements(modal);
  if (!focusable.length) {
    event.preventDefault();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  } else if (!modal.contains(document.activeElement)) {
    event.preventDefault();
    first.focus();
  }
}

document.addEventListener('keydown', event => {
  const activeModals = Array.from(document.querySelectorAll('.modal-overlay.active'));
  const modal = activeModals[activeModals.length - 1];
  if (!modal) {
    if (skillDrawer?.classList.contains('active')) {
      if (event.key === 'Tab') {
        trapModalFocus(event, skillDrawer);
      } else if (event.key === 'Escape') {
        event.preventDefault();
        closeSkillDrawer();
      }
    }
    return;
  }
  if (event.key === 'Tab') {
    trapModalFocus(event, modal);
    return;
  }
  if (event.key === 'Escape') {
    event.preventDefault();
    event.stopPropagation();
    const closeActions = {
      'dialog-modal': closeDialogModal,
      'review-modal': () => closeStructuredReview(false),
      'editor-modal': closeEditorModal,
      'collection-modal': closeCollectionModal,
      'global-target-modal': closeGlobalTargetModal,
      'settings-modal': closeSettingsModal,
      'ai-modal': closeAIModal,
    };
    closeActions[modal.id]?.();
  }
}, true);

// ------------------------------------------
// Bilingual i18n Dictionary
// ------------------------------------------
const locales = {
  zh: {
    sidebarTitle: 'SkillHub',
    sidebarSub: '本地 Skill 工作台',
    btnAssociate: '关联项目',
    btnNewSkill: '新建技能',
    headingProjects: '目标项目',
    emptyProjects: '暂无关联项目',
    emptyProjectsSub: '点击上方按钮选取文件夹',
    btnSettings: '系统设置',
    noProjectTitle: '管理你的 Skill',
    noProjectDesc: '浏览、维护并组合可复用的本地开发规范',
    syncBtn: '预览并同步',
    checkingBtn: '检查变更…',
    syncingBtn: '同步中…',
    syncPreviewTitle: '同步变更预览',
    syncPreviewIntro: '确认后才会写入项目：',
    syncPreviewConflict: '存在需要明确确认的覆盖冲突。',
    syncPreviewNoChanges: '当前项目已经是最新状态',
    syncApply: '应用同步',
    undoSyncTitle: '撤销最近同步',
    undoSyncMessage: '将恢复最近一次同步修改过的文件。同步后又被手动编辑的文件会自动跳过。',
    undoSyncConfirm: '撤销同步',
    toastUndoSuccess: '最近一次同步已撤销',
    toastUndoPartial: '撤销完成，但跳过了已被再次修改的文件: ',
    toastUndoFail: '撤销失败: ',
    statTotal: '全局技能库',
    statSynced: '已装载',
    statUnsynced: '技能有更新',
    statPendingFiles: '个文件待应用',
    statUpToDate: '已是最新',
    listHeader: '全部 Skill',
    listHeaderProject: '项目 Skill 配置',
    tableSkill: 'Skill',
    tableDescription: '说明',
    tableCategory: '分类',
    tableStatus: '状态',
    tableActions: '操作',
    searchPlaceholder: '搜索技能名称、标签…',
    statusSynced: '已同步',
    statusUpdated: '有更新',
    statusPendingMount: '待装载',
    statusPendingUnmount: '待从项目移除',
    statusProjectCustom: '项目自定义 · 已保留',
    statusUnloaded: '未装载',
    statusReadonly: '未选择项目',
    btnAI: 'SkillOps Agent',
    aiWebSearch: '联网检索',
    aiGenerate: '生成技能',
    btnViewSkill: '查看文档',
    btnEditSkill: '编辑技能',
    toggleLabel: '启用装载',
    viewModalTitle: '查看文档',
    viewModalTabSource: 'Markdown 源码',
    viewModalTabPreview: '文档预览',
    viewModalClose: '关闭',
    editModalTitle: '编辑技能',
    editCategoryLabel: '分类',
    editCategoryUncategorized: '未分类',
    editCategoryAdd: '新增类别',
    editCategoryAddTitle: '新增 Skill 类别',
    editCategoryAddMessage: '输入新类别名称；保存当前 Skill 后，该类别会出现在分类列表中。',
    editCategoryAddPlaceholder: '例如：安全工程',
    editCategoryDelete: '删除类别',
    editCategoryDeleteTitle: '删除 Skill 类别',
    editCategoryDeletePending: '尚未保存的新类别已移除',
    editCategoryDeleteEmpty: '这个类别没有可修改的全局 Skill，无法删除',
    editCategoryDeleteSuccess: '类别已删除，相关 Skill 已归入未分类',
    editCategoryHint: '保存时会同步更新 Skill 文件中的 category 字段',
    editSourceSkillHint: 'name 标识 Skill；description 参与隐式匹配；正文是选中后加载的执行指令',
    editSourceOpenaiHint: 'OpenAI/Codex 的界面元数据与调用策略',
    editOpenaiExisting: '已存在',
    editOpenaiNew: '保存后创建',
    editOpenaiUnsupported: '不适用',
    editOpenaiHintTitle: '调用策略与使用配置',
    editOpenaiHintBody: '发布或启用全局目标只决定 Skill 是否可被发现；是否允许自动调用由 policy.allow_implicit_invocation 独立控制。',
    editFieldDisplayName: '界面显示名称',
    editFieldShortDescription: '界面简短说明',
    editFieldDefaultPrompt: '显式调用时的推荐提示',
    editFieldImplicit: '是否允许系统自动选择此 Skill',
    editFieldDependencies: 'Skill 所需的 MCP 等工具依赖',
    openaiModeForm: '可视化配置',
    openaiModeYaml: 'YAML 源码',
    openaiFormTitle: 'Skill 使用配置',
    openaiFormDescription: '这些字段影响 Skill 在 OpenAI/Codex 中如何显示、被调用以及运行前需要哪些工具。',
    openaiFormSourceNote: '保存时同步写入 agents/openai.yaml',
    openaiDisplayNameLabel: '显示名称',
    openaiDisplayNameHelp: '显示在 Skill 选择界面中；不会改变 Skill 的 $调用名称。',
    openaiShortDescriptionLabel: '界面简短说明',
    openaiShortDescriptionHelp: '帮助用户在列表中理解用途；隐式匹配仍由 SKILL.md 的 description 决定。',
    openaiDefaultPromptLabel: '推荐使用提示',
    openaiDefaultPromptHelp: '用户选择此 Skill 时可参考的起始请求；它不是 Skill 的内部执行指令。',
    openaiImplicitTitle: '自动调用策略',
    openaiImplicitHelp: '控制系统能否根据用户请求自动选择此 Skill；与是否发布到全局目标无关。',
    openaiImplicitAllowTitle: '允许自动调用',
    openaiImplicitAllowHelp: '请求与 SKILL.md 的 description 匹配时，系统可以自动选择。',
    openaiImplicitManualTitle: '仅手动调用',
    openaiImplicitManualHelp: '系统不会自动选择，但用户仍可通过 $skill-name 显式调用。',
    openaiDependenciesTitle: '工具依赖（可选）',
    openaiDependenciesHelp: '声明 Skill 正常运行所需的 MCP 等工具；这里只描述依赖，不会自动安装、授权或连接工具。',
    openaiAddTool: '添加工具依赖',
    openaiToolsEmpty: '当前没有工具依赖。无需外部工具的 Skill 可以保持为空。',
    openaiToolTitle: '工具依赖',
    openaiToolType: '类型（必填）',
    openaiToolValue: '工具标识（必填）',
    openaiToolDescription: '用途说明',
    openaiToolTransport: '连接方式',
    openaiToolUrl: '服务地址',
    openaiToolRemove: '删除此依赖',
    editModalTabSource: '编辑',
    editModalTabPreview: '预览',
    editModalCancel: '取消',
    editModalSave: '保存并更新',
    toastLoadFail: '获取列表失败: ',
    toastConfigFail: '获取系统配置失败: ',
    toastProjectFail: '获取项目列表失败: ',
    toastAssocSuccess: '已关联项目: ',
    toastAssocExists: '该项目已关联',
    toastCreateSuccess: '技能文件已创建: ',
    toastCreateExists: '该文件已存在',
    toastSaveSuccess: '全局技能已保存',
    toastSyncSuccess: '同步完成！已装载 ',
    toastSyncFail: '同步失败: ',
    toastRemoveSuccess: '项目已移除',
    toastPathUpdate: '全局技能库路径已更新',
    toastRefreshSuccess: '全局技能库已成功重扫描刷新 🟢',
    toastSettingsSaved: '系统配置已保存并生效 ⚙️',
    settingsTitle: '系统设置',
    settingsCancel: '取消',
    settingsSave: '保存配置',
    settingsHeadingGeneral: '通用偏好',
    settingsLabelLang: '系统语言',
    settingsDescLang: '切换整个界面的显示语言',
    settingsLabelTheme: '界面主题',
    settingsDescTheme: '选择明亮模式或护眼深色模式',
    settingsThemeLight: '明亮模式',
    settingsThemeDark: '深色模式',
    settingsHeadingPaths: '路径管理',
    settingsLabelSkillsdir: '全局技能库路径',
    settingsDescSkillsdir: '存放全局技能规约 Markdown 文件的目录',
    settingsLabelScandir: '项目默认扫描起点',
    settingsDescScandir: '点击“关联项目”时，默认打开的初始目录',
    settingsHeadingAI: 'AI 与大模型配置',
    settingsLabelApibase: 'API 接口地址',
    settingsDescApibase: '自定义 OpenAI 兼容接口，例如：官方 https://api.deepseek.com/v1，本地 Ollama 填 http://localhost:11434/v1，SiliconFlow 填 https://api.siliconflow.cn/v1',
    settingsLabelApikey: 'API 密钥',
    settingsDescApikey: '用于 AI 智能编写和辅助生成技能内容',
    settingsLabelAimodel: 'AI 模型名称',
    settingsDescAimodel: '输入你要调用的模型，如 deepseek-chat, qwen2.5:7b, gpt-4o 等',
    btnTestConnection: '测试连接',
    exitProjectMode: '已返回技能库',
    confirmRemove: '确定要移除此项目的关联吗？\n不会删除项目中的任何文件。',
    defaultDesc: '此技能暂无详细描述信息。',
    agentSessionList: '会话列表',
    agentEmptyTitle: '给 SkillOps Agent 一个目标',
    agentEmptyDescription: 'Agent 会自主选择检查、检索和草案工具；写入前始终等待你的批准。',
    agentSuggestionReview: '生成代码审查规范',
    agentSuggestionReviewNote: '从技术栈和风险点开始',
    agentSuggestionAudit: '检查现有 Skill',
    agentSuggestionAuditNote: '发现冲突、重复和缺口',
    agentSuggestionExtract: '从文档提取规范',
    agentSuggestionExtractNote: '整理为可复用的规则',
    agentPromptReview: '根据当前项目技术栈，帮我生成一份代码审查 Skill',
    agentPromptAudit: '检查现有 Skill 是否有冲突、重复或不清晰的规则',
    agentPromptExtract: '帮我把项目文档整理成一份结构清晰的开发 Skill'
  },
  en: {
    sidebarTitle: 'SkillHub',
    sidebarSub: 'Local Skill workspace',
    btnAssociate: 'Link Project',
    btnNewSkill: 'New Skill',
    headingProjects: 'Target Projects',
    emptyProjects: 'No Linked Projects',
    emptyProjectsSub: 'Click button above to select folder',
    btnSettings: 'Settings',
    noProjectTitle: 'Manage your Skills',
    noProjectDesc: 'Browse, maintain, and combine reusable local development guidance',
    syncBtn: 'Preview & Sync',
    checkingBtn: 'Checking changes...',
    syncingBtn: 'Syncing...',
    syncPreviewTitle: 'Sync Change Preview',
    syncPreviewIntro: 'Files will only be written after confirmation:',
    syncPreviewConflict: 'Explicit confirmation is required for overwrite conflicts.',
    syncPreviewNoChanges: 'This project is already up to date',
    syncApply: 'Apply Sync',
    undoSyncTitle: 'Undo Last Sync',
    undoSyncMessage: 'Files changed by the most recent sync will be restored. Files edited afterward will be skipped.',
    undoSyncConfirm: 'Undo Sync',
    toastUndoSuccess: 'The most recent sync was undone',
    toastUndoPartial: 'Undo completed, but skipped files edited afterward: ',
    toastUndoFail: 'Undo failed: ',
    statTotal: 'Global Skill Library',
    statSynced: 'Currently Loaded',
    statUnsynced: 'Skills Updated',
    statPendingFiles: 'files to apply',
    statUpToDate: 'Up to date',
    listHeader: 'All Skills',
    listHeaderProject: 'Project Skill Setup',
    tableSkill: 'Skill',
    tableDescription: 'Description',
    tableCategory: 'Category',
    tableStatus: 'Status',
    tableActions: 'Actions',
    searchPlaceholder: 'Search skills, tags...',
    statusSynced: 'Synced',
    statusUpdated: 'Updated',
    statusPendingMount: 'Pending Mount',
    statusPendingUnmount: 'Pending Project Removal',
    statusProjectCustom: 'Project Custom · Retained',
    statusUnloaded: 'Unloaded',
    statusReadonly: 'No Project Selected',
    btnAI: 'SkillOps Agent',
    aiWebSearch: 'Web search',
    aiGenerate: 'Generate Skill',
    btnViewSkill: 'View Docs',
    btnEditSkill: 'Edit Skill',
    toggleLabel: 'Enable Mount',
    viewModalTitle: 'View Docs',
    viewModalTabSource: 'Markdown Source',
    viewModalTabPreview: 'Document Preview',
    viewModalClose: 'Close',
    editModalTitle: 'Edit Skill',
    editCategoryLabel: 'Category',
    editCategoryUncategorized: 'Uncategorized',
    editCategoryAdd: 'Add category',
    editCategoryAddTitle: 'Add Skill Category',
    editCategoryAddMessage: 'Enter a category name. It will appear in the category list after this Skill is saved.',
    editCategoryAddPlaceholder: 'e.g. Security Engineering',
    editCategoryDelete: 'Delete category',
    editCategoryDeleteTitle: 'Delete Skill Category',
    editCategoryDeletePending: 'The unsaved category was removed',
    editCategoryDeleteEmpty: 'No editable global Skill uses this category',
    editCategoryDeleteSuccess: 'Category deleted; related Skills are now uncategorized',
    editCategoryHint: 'Saving updates the category field in the Skill file',
    editSourceSkillHint: 'name identifies the Skill; description drives implicit matching; the body contains instructions loaded after selection',
    editSourceOpenaiHint: 'OpenAI/Codex UI metadata and invocation policy',
    editOpenaiExisting: 'Existing',
    editOpenaiNew: 'Created on save',
    editOpenaiUnsupported: 'Not applicable',
    editOpenaiHintTitle: 'Invocation policy and usage configuration',
    editOpenaiHintBody: 'Publishing or enabling a global target only makes the Skill discoverable. policy.allow_implicit_invocation independently controls whether the system may select it automatically.',
    editFieldDisplayName: 'User-facing display name',
    editFieldShortDescription: 'Short UI description',
    editFieldDefaultPrompt: 'Suggested prompt for explicit use',
    editFieldImplicit: 'Whether the system may select this Skill automatically',
    editFieldDependencies: 'Required MCP and other tool dependencies',
    openaiModeForm: 'Visual configuration',
    openaiModeYaml: 'YAML source',
    openaiFormTitle: 'Skill usage configuration',
    openaiFormDescription: 'These fields control how the Skill appears, is invoked, and declares required tools in OpenAI/Codex.',
    openaiFormSourceNote: 'Saved to agents/openai.yaml',
    openaiDisplayNameLabel: 'Display name',
    openaiDisplayNameHelp: 'Shown in the Skill picker; it does not change the Skill\'s $invocation name.',
    openaiShortDescriptionLabel: 'Short UI description',
    openaiShortDescriptionHelp: 'Helps users understand the Skill in lists; implicit matching still uses SKILL.md description.',
    openaiDefaultPromptLabel: 'Suggested starting prompt',
    openaiDefaultPromptHelp: 'A starting request users can reference when selecting this Skill; it is not an internal instruction.',
    openaiImplicitTitle: 'Automatic invocation policy',
    openaiImplicitHelp: 'Controls whether the system may select this Skill from the user request; independent of global publication.',
    openaiImplicitAllowTitle: 'Allow automatic invocation',
    openaiImplicitAllowHelp: 'The system may select the Skill when the request matches the SKILL.md description.',
    openaiImplicitManualTitle: 'Manual invocation only',
    openaiImplicitManualHelp: 'The system will not select it automatically; users can still invoke it with $skill-name.',
    openaiDependenciesTitle: 'Tool dependencies (optional)',
    openaiDependenciesHelp: 'Declares MCP and other tools required by the Skill. This does not install, authorize, or connect tools.',
    openaiAddTool: 'Add tool dependency',
    openaiToolsEmpty: 'No tool dependencies. Skills that need no external tools can leave this empty.',
    openaiToolTitle: 'Tool dependency',
    openaiToolType: 'Type (required)',
    openaiToolValue: 'Tool identifier (required)',
    openaiToolDescription: 'Purpose',
    openaiToolTransport: 'Transport',
    openaiToolUrl: 'Service URL',
    openaiToolRemove: 'Remove dependency',
    editModalTabSource: 'Edit',
    editModalTabPreview: 'Preview',
    editModalCancel: 'Cancel',
    editModalSave: 'Save & Update',
    toastLoadFail: 'Failed to fetch skill list: ',
    toastConfigFail: 'Failed to fetch configuration: ',
    toastProjectFail: 'Failed to fetch projects list: ',
    toastAssocSuccess: 'Linked project: ',
    toastAssocExists: 'This project is already linked',
    toastCreateSuccess: 'Skill file created: ',
    toastCreateExists: 'File already exists',
    toastSaveSuccess: 'Global skill saved successfully',
    toastSyncSuccess: 'Sync completed! Loaded ',
    toastSyncFail: 'Sync failed: ',
    toastRemoveSuccess: 'Project association removed',
    toastPathUpdate: 'Global skills path updated',
    toastRefreshSuccess: 'Global skill library rescanned & refreshed 🟢',
    toastSettingsSaved: 'Settings saved and applied ⚙️',
    settingsTitle: 'System Settings',
    settingsCancel: 'Cancel',
    settingsSave: 'Save Settings',
    settingsHeadingGeneral: 'General Preferences',
    settingsLabelLang: 'System Language',
    settingsDescLang: 'Switch display language across the interface',
    settingsLabelTheme: 'Theme Mode',
    settingsDescTheme: 'Choose light or eye-protection dark mode',
    settingsThemeLight: 'Light Mode',
    settingsThemeDark: 'Dark Mode',
    settingsHeadingPaths: 'Paths Management',
    settingsLabelSkillsdir: 'Global Skill Library Path',
    settingsDescSkillsdir: 'Folder storing global Markdown files',
    settingsLabelScandir: 'Project Scan Starting Path',
    settingsDescScandir: 'Default folder shown when adding a project',
    settingsHeadingAI: 'AI & Large Model Configs',
    settingsLabelApibase: 'API Base URL',
    settingsDescApibase: 'Custom OpenAI-compatible base URL. e.g. DeepSeek: https://api.deepseek.com/v1, local Ollama: http://localhost:11434/v1, SiliconFlow: https://api.siliconflow.cn/v1',
    settingsLabelApikey: 'API Key',
    settingsDescApikey: 'Used for AI generation and search-assisted writing',
    settingsLabelAimodel: 'AI Model Name',
    settingsDescAimodel: 'Enter target model name, e.g. deepseek-chat, qwen2.5:7b, gpt-4o',
    btnTestConnection: 'Test Link',
    exitProjectMode: 'Back to the Skill library',
    confirmRemove: 'Are you sure you want to unlink this project?\nNo files will be deleted from your disk.',
    defaultDesc: 'No detailed description available for this skill.',
    agentSessionList: 'Sessions',
    agentEmptyTitle: 'Give SkillOps Agent a goal',
    agentEmptyDescription: 'The agent chooses inspection, research, and drafting tools; writes always wait for your approval.',
    agentSuggestionReview: 'Create review guidance',
    agentSuggestionReviewNote: 'Start from the stack and risks',
    agentSuggestionAudit: 'Audit existing Skills',
    agentSuggestionAuditNote: 'Find conflicts, duplication, and gaps',
    agentSuggestionExtract: 'Extract guidance from docs',
    agentSuggestionExtractNote: 'Turn project docs into reusable rules',
    agentPromptReview: 'Create a code review Skill based on the current project stack',
    agentPromptAudit: 'Check existing Skills for conflicts, duplication, or unclear rules',
    agentPromptExtract: 'Turn the project documentation into a clear development Skill'
  }
};


const tagTranslations = {
  zh: {
    'Git': 'Git',
    'Collaboration': '协作',
    'Basic': '基础',
    'General': '常规',
    'Python': 'Python',
    'Env Isolation': '环境隔离',
    'Team Collaboration': '团队协作',
    'Workflow': '工作流',
    'Rules': '规范',
    'Standards': '规范',
    'Frontend': '前端',
    'Optimization': '优化',
    'Performance': '性能',
    '协作': '协作',
    '基础': '基础',
    '常规': '常规',
    '环境隔离': '环境隔离',
    '团队协作': '团队协作',
    '工作流': '工作流',
    '规范': '规范',
    '前端': '前端',
    '优化': '优化',
    '性能': '性能',
    '主控': '主控',
    '模板': '模板',
    '项目级': '项目级',
    'Master': '主控',
    'Template': '模板',
    'Project-Level': '项目级'
  },
  en: {
    'Git': 'Git',
    '协作': 'Collaboration',
    '基础': 'Basic',
    '常规': 'General',
    'Python': 'Python',
    '环境隔离': 'Env Isolation',
    '团队协作': 'Team Collaboration',
    '工作流': 'Workflow',
    '规范': 'Rules',
    '前端': 'Frontend',
    '优化': 'Optimization',
    '性能': 'Performance',
    'Collaboration': 'Collaboration',
    'Basic': 'Basic',
    'General': 'General',
    'Env Isolation': 'Env Isolation',
    'Team Collaboration': 'Team Collaboration',
    'Workflow': 'Workflow',
    'Rules': 'Rules',
    'Frontend': 'Frontend',
    'Optimization': 'Optimization',
    'Performance': 'Performance',
    '主控': 'Master',
    '模板': 'Template',
    '项目级': 'Project-Level',
    'Master': 'Master',
    'Template': 'Template',
    'Project-Level': 'Project-Level'
  }
};

const categoryTranslations = {
  zh: {
    'Development': '编程开发',
    'Workflow': '工作流程',
    'Engineering Efficiency': '工程效率',
    'Engineering Quality': '工程质量',
    'Team Collaboration': '团队协作',
    'Frontend Development': '前端开发',
    'Code Analysis': '代码分析',
    'Text Optimization': '文本优化',
    'Security Engineering': '安全工程',
    'Uncategorized': '未分类',
    '编程开发': '编程开发',
    '工作流程': '工作流程',
    '工作流': '工作流程',
    '未分类': '未分类',
    '文本优化': '文本优化',
    '安全工程': '安全工程'
  },
  en: {
    '编程开发': 'Development',
    '工作流程': 'Workflow',
    '工作流': 'Workflow',
    '工程效率': 'Engineering Efficiency',
    '工程质量': 'Engineering Quality',
    '团队协作': 'Team Collaboration',
    '前端开发': 'Frontend Development',
    '代码分析': 'Code Analysis',
    '文本优化': 'Text Optimization',
    '安全工程': 'Security Engineering',
    '未分类': 'Uncategorized',
    'Development': 'Development',
    'Workflow': 'Workflow',
    'Uncategorized': 'Uncategorized',
    'Text Optimization': 'Text Optimization',
    'Security Engineering': 'Security Engineering'
  }
};

// Wait for pywebview bridge
window.addEventListener('pywebviewready', () => {
  init();
});

async function init() {
  await fetchConfig();
  await fetchSkills();
  await fetchProjects();
  lucide.createIcons();
  checkForUnregisteredSkills();
}

async function fetchConfig() {
  try {
    const config = await window.pywebview.api.get_config();
    skillsDirPath.textContent = config.skills_dir;
    skillsDirPath.title = config.skills_dir;
    projects = config.projects || [];
    currentLanguage = config.language || 'zh';
    currentTheme = config.theme || 'light';
    defaultScanDir = config.default_scan_dir || '';
    deepseekModel = config.deepseek_model || 'deepseek-chat';
    apiBase = config.api_base || 'https://api.deepseek.com/v1';
    hasAiKey = Boolean(config.has_ai_key);
    apiKeyHint = config.api_key_hint || '';
    aiImportOptimization = Boolean(config.ai_import_optimization);
    aiDisplayTranslation = Boolean(config.ai_display_translation);
    globalSkillTargets = Array.isArray(config.global_skill_targets)
      ? config.global_skill_targets
      : ['codex'];
    globalSkillTargetOptions = Array.isArray(config.global_skill_target_options)
      ? config.global_skill_target_options
      : [];

    applyTheme(currentTheme);
    applyLanguage(currentLanguage);
    updateAIConfigurationIndicators();
  } catch (e) {
    showToast(currentLanguage === 'zh' ? '获取系统配置失败: ' + e : 'Failed to fetch config: ' + e, 'error');
  }
}

function applyTheme(theme) {
  currentTheme = theme;
  if (theme === 'dark') {
    document.body.classList.add('dark-theme');
  } else {
    document.body.classList.remove('dark-theme');
  }
}

function applyLanguage(lang) {
  currentLanguage = lang;
  const t = locales[lang];
  
  // Sidebar
  document.querySelector('.brand-title h1').textContent = t.sidebarTitle;
  document.querySelector('.brand-title p').textContent = t.sidebarSub;
  const addProjectButton = document.getElementById('btn-add-project');
  addProjectButton.title = t.btnAssociate;
  addProjectButton.setAttribute('aria-label', t.btnAssociate);
  document.getElementById('btn-new-skill').innerHTML = `<i data-lucide="plus"></i> ${lang === 'zh' ? '新建 Skill' : 'New Skill'}`;
  document.getElementById('btn-import-skill').innerHTML = `<i data-lucide="download"></i> ${lang === 'zh' ? '导入' : 'Import'}`;
  document.querySelector('#btn-ai-search span:not(.nav-status-dot)').textContent = t.btnAI;
  document.querySelector('#nav-library span:not(.nav-count)').textContent = lang === 'zh' ? '技能库' : 'Skill Library';
  document.getElementById('ai-modal-title').textContent = 'SkillOps Agent';
  document.querySelector('.sidebar-section .section-title h2').textContent = t.headingProjects;
  document.getElementById('sidebar-settings-text').textContent = t.btnSettings;

  // Main Header / Project View
  updateWorkspaceMode();
  
  // Sync Button Text
  syncBtn.innerHTML = `<i data-lucide="refresh-cw"></i> ${t.syncBtn}`;
  undoSyncBtn.title = t.undoSyncTitle;
  
  // Search Controls & Header Title
  if (!currentProjectPath) {
    document.querySelector('.content-toolbar h3').textContent = t.listHeader;
  } else {
    document.querySelector('.content-toolbar h3').textContent = t.listHeaderProject;
  }
  searchInput.placeholder = t.searchPlaceholder;
  document.getElementById('btn-refresh-skills').title = lang === 'zh' ? '刷新全局技能库' : 'Refresh Global Skills';
  document.getElementById('skill-list-header-skill').textContent = t.tableSkill;
  document.getElementById('skill-list-header-description').textContent = t.tableDescription;
  document.getElementById('skill-list-header-category').textContent = t.tableCategory;
  document.getElementById('skill-list-header-status').textContent = t.tableStatus;
  document.getElementById('skill-list-header-actions').textContent = t.tableActions;

  // Modals (Editor)
  modalTabEdit.textContent = isViewingSkill ? t.viewModalTabSource : t.editModalTabSource;
  modalTabPreview.textContent = isViewingSkill ? t.viewModalTabPreview : t.editModalTabPreview;
  modalCloseFooter.textContent = isViewingSkill ? t.viewModalClose : t.editModalCancel;
  modalSaveBtn.innerHTML = `<i data-lucide="save" style="width:16px;height:16px;"></i> ${t.editModalSave}`;
  skillCategoryLabel.textContent = t.editCategoryLabel;
  skillCategoryAddLabel.textContent = t.editCategoryAdd;
  skillCategoryDeleteLabel.textContent = t.editCategoryDelete;
  skillCategoryHint.textContent = t.editCategoryHint;
  editorOpenaiHintTitle.textContent = t.editOpenaiHintTitle;
  editorOpenaiHintBody.textContent = t.editOpenaiHintBody;
  editorOpenaiModeForm.textContent = t.openaiModeForm;
  editorOpenaiModeYaml.textContent = t.openaiModeYaml;
  const editorTexts = {
    'openai-form-title': t.openaiFormTitle,
    'openai-form-description': t.openaiFormDescription,
    'openai-form-source-note': t.openaiFormSourceNote,
    'openai-display-name-label': t.openaiDisplayNameLabel,
    'openai-display-name-help': t.openaiDisplayNameHelp,
    'openai-short-description-label': t.openaiShortDescriptionLabel,
    'openai-short-description-help': t.openaiShortDescriptionHelp,
    'openai-default-prompt-label': t.openaiDefaultPromptLabel,
    'openai-default-prompt-help': t.openaiDefaultPromptHelp,
    'openai-implicit-title': t.openaiImplicitTitle,
    'openai-implicit-help': t.openaiImplicitHelp,
    'openai-implicit-allow-title': t.openaiImplicitAllowTitle,
    'openai-implicit-allow-help': t.openaiImplicitAllowHelp,
    'openai-implicit-manual-title': t.openaiImplicitManualTitle,
    'openai-implicit-manual-help': t.openaiImplicitManualHelp,
    'openai-dependencies-title': t.openaiDependenciesTitle,
    'openai-dependencies-help': t.openaiDependenciesHelp,
    'openai-add-tool-label': t.openaiAddTool,
    'openai-tools-empty': t.openaiToolsEmpty,
  };
  Object.entries(editorTexts).forEach(([id, value]) => {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  });
  renderOpenaiToolDependencies();
  refreshEditorSourceUi();
  updateEditorDirtyState();
  if (!skillMetadataBar.hidden) populateSkillCategoryOptions(skillCategorySelect.value);

  // Modals (Settings)
  document.getElementById('settings-modal-title').textContent = t.settingsTitle;
  document.getElementById('settings-nav-general').textContent = lang === 'zh' ? '通用' : 'General';
  document.getElementById('settings-nav-paths').textContent = lang === 'zh' ? '路径' : 'Paths';
  document.getElementById('settings-nav-targets').textContent = lang === 'zh' ? '全局目标' : 'Global targets';
  document.getElementById('settings-nav-ai').textContent = 'AI';
  document.getElementById('settings-heading-general').textContent = t.settingsHeadingGeneral;
  document.getElementById('settings-label-lang').textContent = t.settingsLabelLang;
  document.getElementById('settings-desc-lang').textContent = t.settingsDescLang;
  document.getElementById('settings-label-theme').textContent = t.settingsLabelTheme;
  document.getElementById('settings-desc-theme').textContent = t.settingsDescTheme;
  document.getElementById('settings-theme-option-light').textContent = t.settingsThemeLight;
  document.getElementById('settings-theme-option-dark').textContent = t.settingsThemeDark;
  document.getElementById('settings-heading-paths').textContent = t.settingsHeadingPaths;
  document.getElementById('settings-label-skillsdir').textContent = t.settingsLabelSkillsdir;
  document.getElementById('settings-desc-skillsdir').textContent = t.settingsDescSkillsdir;
  document.getElementById('settings-label-scandir').textContent = t.settingsLabelScandir;
  document.getElementById('settings-desc-scandir').textContent = t.settingsDescScandir;
  document.getElementById('settings-heading-global-targets').textContent = lang === 'zh'
    ? '默认全局目标'
    : 'Default global targets';
  document.getElementById('settings-label-global-targets').textContent = lang === 'zh'
    ? '新 Skill 首次全局启用时默认勾选哪些客户端'
    : 'Choose the default clients for a Skill\'s first global enablement';
  document.getElementById('settings-desc-global-targets').textContent = lang === 'zh'
    ? '每个 Skill 打开全局目标窗口后仍可单独修改，不会影响其他 Skill。'
    : 'Each Skill can override these choices independently without affecting other Skills.';
  document.getElementById('settings-claude-desktop-note').textContent = lang === 'zh'
    ? '导出 ZIP，需在 Claude 中上传'
    : 'Export ZIP; upload it in Claude';
  document.querySelector('#settings-global-target-note span').textContent = lang === 'zh'
    ? '未检测到现有 Skill 目录的客户端会被禁用，SkillHub 不会替它创建路径。Claude Desktop 无本地监听目录，只生成上传包。'
    : 'Clients without an existing Skill directory are disabled, and SkillHub will not create their paths. Claude Desktop only exports an upload package.';
  document.getElementById('settings-btn-cancel').textContent = t.settingsCancel;
  document.getElementById('settings-btn-save').innerHTML = `<i data-lucide="save" style="width:16px;height:16px;"></i> ${t.settingsSave}`;

  // Modals (Settings AI Section)
  document.getElementById('settings-heading-ai').textContent = t.settingsHeadingAI;
  document.getElementById('settings-label-apibase').textContent = t.settingsLabelApibase;
  document.getElementById('settings-desc-apibase').textContent = t.settingsDescApibase;
  document.getElementById('settings-label-apikey').textContent = t.settingsLabelApikey;
  document.getElementById('settings-desc-apikey').textContent = t.settingsDescApikey;
  document.getElementById('settings-label-ai-import').textContent = lang === 'zh'
    ? '导入时使用 AI 优化'
    : 'Use AI optimization during import';
  document.getElementById('settings-desc-ai-import').textContent = lang === 'zh'
    ? '开启后先完成本地结构、安全与多客户端兼容体检，再调用 AI 优化入口文档；导入前会显示差异并要求确认。'
    : 'Runs local structure, security, and multi-client compatibility checks, then asks AI to optimize the entry document; the diff must be reviewed and accepted before import.';
  document.getElementById('settings-label-ai-display-translation').textContent = lang === 'zh'
    ? '导入时生成双语说明'
    : 'Generate bilingual descriptions on import';
  document.getElementById('settings-desc-ai-display-translation').textContent = lang === 'zh'
    ? '仅将 Skill 标题和说明发送到已配置的 AI；翻译只用于界面显示，不修改 SKILL.md。'
    : 'Sends only the Skill title and description to the configured AI. Translations are display-only and never modify SKILL.md.';
  document.getElementById('settings-label-aimodel').textContent = t.settingsLabelAimodel;
  document.getElementById('settings-desc-aimodel').textContent = t.settingsDescAimodel;
  document.getElementById('btn-test-connection').innerHTML = `<i data-lucide="zap" style="width:13px;height:13px;"></i> ${t.btnTestConnection}`;

  // Re-render components to apply dynamic texts
  renderProjectsList();
  renderCategoryFilterBar();
  renderSkillsGrid();
  updateStatistics();
  updateAIConfigurationIndicators();
  if (typeof updateAgentDialogControls === 'function') {
    updateAgentDialogControls();
  }
  lucide.createIcons();
}

// ------------------------------------------
// Data Layer (pywebview bridge)
// ------------------------------------------

async function fetchSkills() {
  try {
    skills = await window.pywebview.api.get_skills();
    renderCategoryFilterBar();
    renderSkillsGrid();
  } catch (e) {
    showToast(locales[currentLanguage].toastLoadFail + e, 'error');
  }
}

async function fetchProjects() {
  try {
    projects = await window.pywebview.api.get_projects();
    renderProjectsList();
    updateStatistics();
  } catch (e) {
    showToast(locales[currentLanguage].toastProjectFail + e, 'error');
  }
}

function updateStatistics() {
  if (!currentProjectPath) {
    toolbarStats.style.display = 'none';
    pendingSyncSummary = null;
    if (syncBarSummary) syncBarSummary.textContent = currentLanguage === 'zh' ? '选择项目后可预览同步变更' : 'Select a project to preview sync changes';
    return;
  }
  const proj = projects.find(p => p.path === currentProjectPath);
  let synced = 0, unsynced = 0;
  if (proj && !proj.error) {
    Object.values(proj.skills_status || {}).forEach(s => {
      if (s === 'synced') synced++;
      if (s === 'out_of_sync') unsynced++;
    });
  }
  const t = locales[currentLanguage];
  const pendingCount = pendingSyncSummary
    ? (pendingSyncSummary.add || 0) + (pendingSyncSummary.adopt || 0) + (pendingSyncSummary.modify || 0) + (pendingSyncSummary.delete || 0)
    : null;
  const pendingText = pendingCount === null
    ? t.checkingBtn
    : pendingCount > 0
      ? `${pendingCount} ${t.statPendingFiles}`
      : t.statUpToDate;
  toolbarStats.innerHTML = `
    <span><span class="toolbar-stat-dot synced"></span>${synced} ${t.statSynced}</span>
    ${unsynced ? `<span>·</span><span><span class="toolbar-stat-dot unsynced"></span>${unsynced} ${t.statUnsynced}</span>` : ''}
    <span>·</span>
    <span class="${pendingCount > 0 ? 'pending-files' : 'up-to-date'}">${escapeHtml(pendingText)}</span>`;
  toolbarStats.style.display = 'flex';
  if (syncBarSummary) {
    if (pendingCount === null) {
      syncBarSummary.textContent = t.checkingBtn;
    } else if (pendingCount === 0) {
      syncBarSummary.textContent = currentLanguage === 'zh' ? `${synced} 个 Skill 已装载，无待处理变更` : `${synced} Skills loaded, no pending changes`;
    } else {
      const summary = pendingSyncSummary || {};
      syncBarSummary.textContent = currentLanguage === 'zh'
        ? `新增 ${summary.add || 0} · 纳管 ${summary.adopt || 0} · 更新 ${summary.modify || 0} · 移除 ${summary.delete || 0}`
        : `Add ${summary.add || 0} · Adopt ${summary.adopt || 0} · Update ${summary.modify || 0} · Remove ${summary.delete || 0}`;
    }
  }
}

async function refreshPendingSyncSummary() {
  const projectPath = currentProjectPath;
  if (!projectPath) return;
  const requestId = ++pendingSyncRequestId;
  try {
    const preview = await window.pywebview.api.preview_sync(
      projectPath,
      Array.from(enabledSkills)
    );
    if (requestId !== pendingSyncRequestId || projectPath !== currentProjectPath) return;
    pendingSyncSummary = preview && !preview.error ? preview.summary : null;
  } catch (_error) {
    if (requestId !== pendingSyncRequestId || projectPath !== currentProjectPath) return;
    pendingSyncSummary = null;
  }
  updateStatistics();
}

function queuePendingSyncSummary() {
  clearTimeout(pendingSyncTimer);
  pendingSyncSummary = null;
  updateStatistics();
  pendingSyncTimer = setTimeout(refreshPendingSyncSummary, 100);
}

// ------------------------------------------
// Rendering
// ------------------------------------------

function updateWorkspaceMode() {
  const t = locales[currentLanguage];
  const project = currentProjectPath
    ? projects.find(item => item.path === currentProjectPath)
    : null;
  const isProjectMode = Boolean(project);
  document.body.classList.toggle('project-mode', isProjectMode);
  navLibrary?.classList.toggle('active', !isProjectMode);
  syncActionBar?.classList.toggle('visible', isProjectMode);
  const statusHeader = document.getElementById('skill-list-header-status');
  if (statusHeader) {
    statusHeader.textContent = isProjectMode
      ? t.tableStatus
      : (currentLanguage === 'zh' ? '多端全局' : 'Global targets');
  }
  if (workspaceKicker) {
    workspaceKicker.textContent = isProjectMode
      ? (currentLanguage === 'zh' ? '项目配置' : 'Project setup')
      : (currentLanguage === 'zh' ? '技能库' : 'Skill library');
  }
  const newSkillButton = document.getElementById('btn-new-skill');
  if (newSkillButton) {
    const label = isProjectMode
      ? (currentLanguage === 'zh' ? '新建全局 Skill' : 'New Global Skill')
      : (currentLanguage === 'zh' ? '新建 Skill' : 'New Skill');
    newSkillButton.innerHTML = `<i data-lucide="plus" aria-hidden="true"></i>${label}`;
  }
  if (isProjectMode) {
    currentProjectTitle.textContent = project.name;
    currentProjectDesc.textContent = project.path;
    if (syncBarTitle) syncBarTitle.textContent = currentLanguage === 'zh' ? `${project.name} 的同步变更` : `Sync changes for ${project.name}`;
  } else {
    currentProjectTitle.textContent = t.noProjectTitle;
    currentProjectDesc.textContent = t.noProjectDesc;
    if (syncBarTitle) syncBarTitle.textContent = currentLanguage === 'zh' ? '项目变更' : 'Project changes';
  }
  const heading = document.querySelector('.content-toolbar h3');
  if (heading) heading.textContent = isProjectMode ? t.listHeaderProject : t.listHeader;
}

function handleShowLibrary() {
  if (currentProjectPath) {
    handleSelectProject(currentProjectPath);
    return;
  }
  updateWorkspaceMode();
  renderProjectsList();
}

function renderProjectsList() {
  updateWorkspaceMode();
  projectList.innerHTML = '';
  if (projects.length === 0) {
    projectList.innerHTML = `
      <div class="sidebar-empty-state">
        <p>${locales[currentLanguage].emptyProjects}</p>
        <button type="button" onclick="handlePickProject()">${currentLanguage === 'zh' ? '关联第一个项目' : 'Link your first project'}</button>
      </div>`;
    return;
  }
  projects.forEach(proj => {
    const item = document.createElement('div');
    item.className = `project-item ${proj.path === currentProjectPath ? 'active' : ''}`;
    const errorBadge = proj.error
      ? `<span style="font-size:0.65rem;color:#d1242f;font-weight:600;">⚠️ ${currentLanguage === 'zh' ? '路径无效' : 'Invalid Path'}</span>`
      : '';
    const encodedPath = encodeURIComponent(proj.path);
    const escapedPath = proj.path.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    item.innerHTML = `
      <button type="button" class="project-details" onclick="handleSelectProject(decodeURIComponent('${encodedPath}'))" aria-label="${escapeHtml(currentLanguage === 'zh' ? `打开项目 ${proj.name}` : `Open project ${proj.name}`)}">
        <span class="project-name">${escapeHtml(proj.name)}</span>
        <span class="project-path">${escapeHtml(proj.path)}</span>
        ${errorBadge}
      </button>
      <button class="delete-project-btn btn-icon" onclick="handleDeleteProject(event, '${escapedPath}')" title="移除项目">
        <i data-lucide="trash-2" style="width:14px;height:14px;"></i>
      </button>`;
    projectList.appendChild(item);
  });
  lucide.createIcons();
}

function getSmartEmojiAndTags(skill) {
  let emoji = skill.emoji || '📄';
  let tags = [...(skill.tags || [])];
  
  const text = (skill.title + ' ' + skill.filename + ' ' + skill.description).toLowerCase();
  
  // Smart Emoji fallbacks if default page is used
  if (emoji === '📄' || emoji === '📝' || emoji === '\ud83d\udcc4') {
    if (text.includes('git') || text.includes('commit') || text.includes('版本')) {
      emoji = '🌱';
    } else if (text.includes('性能') || text.includes('优化') || text.includes('performance') || text.includes('speed')) {
      emoji = '🚀';
    } else if (text.includes('接力') || text.includes('交接') || text.includes('handoff') || text.includes('resume')) {
      emoji = '🔄';
    } else if (text.includes('安全') || text.includes('security') || text.includes('safe') || text.includes('密')) {
      emoji = '🛡️';
    } else if (text.includes('规范') || text.includes('guideline') || text.includes('rule') || text.includes('标准') || text.includes('约')) {
      emoji = '📋';
    } else if (text.includes('测试') || text.includes('test') || text.includes('jest') || text.includes('unit')) {
      emoji = '🧪';
    } else if (text.includes('前端') || text.includes('frontend') || text.includes('css') || text.includes('html')) {
      emoji = '🎨';
    }
  }
  
  // Smart automatic Tag cleanup/enforcement
  if (tags.length === 0 || (tags.length === 1 && (tags[0] === '常规' || tags[0] === 'General' || tags[0] === '常规, 基础'))) {
    const newTags = [];
    if (text.includes('git') || text.includes('commit')) newTags.push('Git');
    if (text.includes('性能') || text.includes('优化') || text.includes('performance')) newTags.push(currentLanguage === 'zh' ? '性能' : 'Performance');
    if (text.includes('交接') || text.includes('接力') || text.includes('handoff')) newTags.push(currentLanguage === 'zh' ? '交接' : 'Handoff');
    if (text.includes('安全') || text.includes('security')) newTags.push(currentLanguage === 'zh' ? '安全' : 'Security');
    if (text.includes('规范') || text.includes('规约') || text.includes('rule')) newTags.push(currentLanguage === 'zh' ? '规范' : 'Rules');
    if (text.includes('前端') || text.includes('web') || text.includes('css')) newTags.push(currentLanguage === 'zh' ? '前端' : 'Frontend');
    
    if (newTags.length > 0) {
      tags = newTags;
    }
  }
  
  return { emoji, tags };
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function sanitizeHtml(html) {
  const template = document.createElement('template');
  template.innerHTML = html;
  template.content.querySelectorAll('script, iframe, object, embed, link, meta').forEach(node => node.remove());
  template.content.querySelectorAll('*').forEach(node => {
    [...node.attributes].forEach(attr => {
      const name = attr.name.toLowerCase();
      const value = attr.value.trim().toLowerCase();
      if (name.startsWith('on') || value.startsWith('javascript:') || value.startsWith('data:text/html')) {
        node.removeAttribute(attr.name);
      }
    });
  });
  return template.innerHTML;
}

function splitMarkdownFrontmatter(markdown) {
  const source = String(markdown || '');
  const match = source.match(/^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/);
  if (!match) return { frontmatter: '', body: source };
  return {
    frontmatter: match[1].trim(),
    body: source.slice(match[0].length)
  };
}

function getMarkdownFrontmatterCategory(markdown) {
  const { frontmatter } = splitMarkdownFrontmatter(markdown);
  if (!frontmatter) return '';
  const line = frontmatter.split(/\r?\n/).find(item => /^\s*category\s*:/i.test(item));
  if (!line) return '';
  const value = line.replace(/^\s*category\s*:\s*/i, '').trim();
  if (
    value.length >= 2
    && ((value.startsWith('"') && value.endsWith('"'))
      || (value.startsWith("'") && value.endsWith("'")))
  ) {
    return value.slice(1, -1);
  }
  return value;
}

function formatFrontmatterScalar(value) {
  const normalized = String(value || '').trim();
  if (/^[^:#\[\]{}'",\r\n\t]+$/.test(normalized)) return normalized;
  return JSON.stringify(normalized);
}

function setMarkdownFrontmatterCategory(markdown, category) {
  const source = String(markdown || '');
  const normalizedCategory = String(category || '').trim();
  const newline = source.includes('\r\n') ? '\r\n' : '\n';
  const match = source.match(/^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/);

  if (!match) {
    if (!normalizedCategory) return source;
    return [
      '---',
      `category: ${formatFrontmatterScalar(normalizedCategory)}`,
      '---',
      '',
      source,
    ].join(newline);
  }

  const lines = match[1].split(/\r?\n/);
  const categoryIndex = lines.findIndex(line => /^\s*category\s*:/i.test(line));
  if (categoryIndex >= 0) {
    if (normalizedCategory) {
      const indentation = lines[categoryIndex].match(/^\s*/)?.[0] || '';
      lines[categoryIndex] = `${indentation}category: ${formatFrontmatterScalar(normalizedCategory)}`;
    } else {
      lines.splice(categoryIndex, 1);
    }
  } else if (normalizedCategory) {
    lines.push(`category: ${formatFrontmatterScalar(normalizedCategory)}`);
  }

  const replacement = `---${newline}${lines.join(newline)}${newline}---${newline}`;
  return replacement + source.slice(match[0].length);
}

function renderMarkdown(markdown) {
  const { frontmatter, body } = splitMarkdownFrontmatter(markdown);
  const metadata = frontmatter
    ? `<details class="frontmatter-panel"><summary>${currentLanguage === 'zh' ? '文档元数据' : 'Document metadata'}</summary><pre>${escapeHtml(frontmatter)}</pre></details>`
    : '';
  return metadata + sanitizeHtml(marked.parse(body || ''));
}

// COLLECTION_DISPLAY_METADATA_HELPER_START
function resolveCollectionDisplayMetadata(primary, collectionId, childCount, language = currentLanguage) {
  const collection = primary.collection || {};
  const title = collection.display_title || collection.title || collectionId;
  const controllerDescription = collection.is_controller
    ? (primary.display_description || primary.description || '')
    : '';
  const fallbackDescription = language === 'zh'
    ? `包含 ${childCount} 个子技能的技能集合。`
    : `A skill collection containing ${childCount} child skills.`;
  const description = collection.display_description || controllerDescription || fallbackDescription;
  return {
    title,
    description,
    display_title: title,
    display_description: description,
  };
}
// COLLECTION_DISPLAY_METADATA_HELPER_END

function buildDisplaySkills() {
  const groups = new Map();
  skills.forEach(skill => {
    const collectionId = skill.collection?.id;
    if (!collectionId) return;
    if (!groups.has(collectionId)) groups.set(collectionId, []);
    groups.get(collectionId).push(skill);
  });

  const emitted = new Set();
  const display = [];
  skills.forEach(skill => {
    const collectionId = skill.collection?.id;
    if (!collectionId) {
      display.push(skill);
      return;
    }
    if (emitted.has(collectionId)) return;
    emitted.add(collectionId);
    const members = groups.get(collectionId) || [];
    const primary = members.find(member => member.filename === collectionId) || members[0];
    const childCount = members.filter(member => member.filename !== collectionId).length;
    const enabledCount = members.filter(member => member.collection?.effective_enabled).length;
    const configuredCount = members.filter(member => member.collection?.enabled).length;
    const tags = Array.from(new Set(members.flatMap(member => member.tags || []))).slice(0, 5);
    const displayMetadata = resolveCollectionDisplayMetadata(
      primary,
      collectionId,
      childCount,
    );
    const globalMembers = members.filter(member => member.codex_global_compatible);
    const globalEnabledCount = globalMembers.filter(member => member.codex_global_enabled).length;
    const hasGlobalConflict = globalMembers.some(member => member.codex_global_status === 'conflict');
    const hasGlobalUpdate = globalMembers.some(member => member.codex_global_status === 'outdated');
    const hasPartialGlobal = globalMembers.some(member => member.codex_global_status === 'partial');
    const collectionGlobalStatus = hasGlobalConflict
      ? 'conflict'
      : hasGlobalUpdate
        ? 'outdated'
        : globalEnabledCount === globalMembers.length && globalMembers.length > 0
          ? 'enabled'
          : globalEnabledCount > 0 || hasPartialGlobal
            ? 'partial'
            : 'disabled';
    const collectionTargetStates = globalSkillTargetOptions.map(option => {
      const memberStates = globalMembers.map(member => (
        member.global_target_states || []
      ).find(target => target.id === option.id)).filter(Boolean);
      const enabledTargets = memberStates.filter(target => target.enabled);
      const status = memberStates.some(target => target.status === 'conflict')
        ? 'conflict'
        : memberStates.some(target => target.status === 'outdated')
          ? 'outdated'
          : memberStates.length > 0 && enabledTargets.length === memberStates.length
            ? 'enabled'
            : enabledTargets.length > 0
              ? 'partial'
              : 'disabled';
      return {
        ...option,
        enabled: status === 'enabled' || status === 'outdated',
        status,
        managed: enabledTargets.every(target => target.managed),
        target: option.path,
      };
    });
    display.push({
      ...primary,
      ...displayMetadata,
      filename: `@collection:${collectionId}`,
      emoji: '🧰',
      tags,
      is_dir: true,
      is_collection: true,
      collection_id: collectionId,
      collection_members: members,
      collection_child_count: childCount,
      collection_enabled_count: enabledCount,
      collection_configured_count: configuredCount,
      collection_controller: primary.collection?.controller || '',
      collection_controller_enabled: primary.collection?.controller_enabled !== false,
      codex_global_compatible: globalMembers.length > 0,
      codex_global_enabled: globalMembers.length > 0 && globalEnabledCount === globalMembers.length,
      codex_global_status: collectionGlobalStatus,
      codex_global_members: globalMembers.map(member => member.filename),
      global_target_states: collectionTargetStates,
      search_text: members.map(member => [
        member.title,
        member.display_title,
        member.description,
        member.display_description,
        member.filename,
        ...(member.tags || [])
      ].join(' ')).join(' ')
    });
  });

  // Project-only skills are a read-only supplement in project mode. Keeping
  // them out of `skills` ensures imports, collections, and sync inputs remain
  // based solely on the global library.
  if (currentProjectPath) {
    const activeProject = projects.find(project => project.path === currentProjectPath);
    if (activeProject && !activeProject.error) {
      (activeProject.project_skills || []).forEach(skill => display.push(skill));
    }
  }
  displaySkillsByFilename = new Map(
    display.map(skill => [skill.filename, skill])
  );
  return display;
}

function getCardFilename(event) {
  const card = event.target.closest('.skill-card');
  return card?.dataset.filename || '';
}

function handleCardsGridClick(event) {
  const filename = getCardFilename(event);
  if (!filename) return;
  const displaySkill = displaySkillsByFilename.get(filename);
  const globalAction = event.target.closest('.js-codex-global-action');
  if (globalAction && displaySkill) {
    event.stopPropagation();
    handleCodexGlobalButton(displaySkill, globalAction);
    return;
  }
  if (displaySkill?.is_collection) {
    if (event.target.closest('label, input, a')) return;
    event.stopPropagation();
    openCollectionModal(displaySkill.collection_id);
    return;
  }
  if (event.target.closest('.js-edit-skill')) {
    event.stopPropagation();
    openEditorModal(filename);
    return;
  }
  if (event.target.closest('.js-delete-skill')) {
    event.stopPropagation();
    handleDeleteSkill(filename);
    return;
  }
  if (event.target.closest('button, label, input, a')) return;
  openSkillViewer(filename);
}

function handleCardsGridChange(event) {
  const filename = getCardFilename(event);
  if (!event.target.matches('.js-toggle-skill')) return;
  const displaySkill = displaySkillsByFilename.get(filename);
  if (displaySkill?.is_collection) {
    handleToggleCollectionMount(displaySkill, event.target.checked);
  } else if (filename) {
    handleToggleSkill(filename, event.target.checked);
  }
}

function updateAIConfigurationIndicators() {
  const isZh = currentLanguage === 'zh';
  const status = document.getElementById('api-config-status');
  const summary = document.getElementById('api-config-summary');
  const importSummary = document.getElementById('import-mode-summary');
  const keyInput = document.getElementById('settings-apikey');
  const toggle = document.getElementById('settings-ai-import-optimization');
  const navAiStatus = document.getElementById('nav-ai-status');

  if (status) {
    status.className = `config-status ${hasAiKey ? 'ready' : 'neutral'}`;
    status.textContent = hasAiKey
      ? `${isZh ? '已配置' : 'Configured'} ${apiKeyHint}`
      : (isZh ? '未配置 API Key' : 'API Key not configured');
  }
  if (summary) {
    summary.className = `service-status ${hasAiKey ? 'ready' : 'neutral'}`;
    summary.textContent = hasAiKey
      ? `${isZh ? 'AI 已配置' : 'AI configured'} ${apiKeyHint}`
      : (isZh ? 'AI 未配置' : 'AI not configured');
  }
  if (navAiStatus) {
    navAiStatus.classList.toggle('ready', hasAiKey);
    navAiStatus.title = hasAiKey
      ? (isZh ? 'AI 已配置' : 'AI configured')
      : (isZh ? 'AI 未配置' : 'AI not configured');
  }
  if (importSummary) {
    const usingAi = aiImportOptimization && hasAiKey;
    importSummary.className = `service-status ${usingAi ? 'ai' : 'local'}`;
    importSummary.textContent = usingAi
      ? (isZh ? '本地 + AI' : 'Local + AI')
      : (isZh ? '本地体检' : 'Local checks');
    importSummary.title = aiImportOptimization && !hasAiKey
      ? (isZh ? 'AI 优化已开启，但未配置 API Key；导入时自动使用本地结果。' : 'AI optimization is enabled without an API key; imports automatically use local results.')
      : '';
  }
  if (keyInput) {
    keyInput.placeholder = hasAiKey
      ? (isZh ? `已配置 ${apiKeyHint}；输入新 Key 可替换` : `Configured ${apiKeyHint}; enter a new key to replace`)
      : 'sk-...';
  }
  if (toggle) toggle.checked = aiImportOptimization;
}

function handleCardsGridKeydown(event) {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  const filename = getCardFilename(event);
  if (!filename || event.target.closest('button, label, input, a')) return;
  event.preventDefault();
  const displaySkill = displaySkillsByFilename.get(filename);
  if (displaySkill?.is_collection) {
    openCollectionModal(displaySkill.collection_id);
  } else {
    openSkillViewer(filename);
  }
}

cardsGrid.addEventListener('click', handleCardsGridClick);
cardsGrid.addEventListener('change', handleCardsGridChange);
cardsGrid.addEventListener('keydown', handleCardsGridKeydown);

// Get canonical category name (e.g. 'Development', 'Workflow', 'Uncategorized', or raw custom string)
function getCanonicalCategory(skill) {
  let cat = skill.category;

  if (!cat) {
    cat = skill.is_dir ? 'Workflow' : 'Uncategorized';
  }

  // Normalize known Chinese categories to canonical English keys
  if (cat === '编程开发') return 'Development';
  if (cat === '工作流程') return 'Workflow';
  if (cat === '工作流') return 'Workflow';
  if (cat === '工程效率') return 'Engineering Efficiency';
  if (cat === '工程质量') return 'Engineering Quality';
  if (cat === '团队协作') return 'Team Collaboration';
  if (cat === '前端开发') return 'Frontend Development';
  if (cat === '代码分析') return 'Code Analysis';
  if (cat === '文本优化') return 'Text Optimization';
  if (cat === '安全工程') return 'Security Engineering';
  if (cat === '未分类') return 'Uncategorized';

  return cat;
}

// Translate canonical category to current language for UI
function getLocalizedCategory(canonicalCat) {
  return categoryTranslations[currentLanguage]?.[canonicalCat] || canonicalCat;
}

function getSkillListIcon(skill) {
  if (skill.is_collection) return 'layers-3';
  if (skill.project_only) return 'file-lock-2';
  const icons = {
    Development: 'code-2',
    Workflow: 'git-branch',
    'Engineering Efficiency': 'gauge',
    'Engineering Quality': 'shield-check',
    'Team Collaboration': 'users',
    'Frontend Development': 'monitor-smartphone',
    'Code Analysis': 'scan-search',
    'Text Optimization': 'file-text',
    'Security Engineering': 'shield'
  };
  return icons[getCanonicalCategory(skill)] || 'file';
}

// Render dynamic category pills
function renderCategoryFilterBar() {
  if (!categoryFilterBar) return;
  
  // Extract all unique canonical categories from currently loaded skills
  const categoriesSet = new Set();
  buildDisplaySkills().forEach(skill => {
    categoriesSet.add(getCanonicalCategory(skill));
  });
  
  const uniqueCanonicalCategories = Array.from(categoriesSet).sort();
  
  const allLabel = currentLanguage === 'zh' ? '全部' : 'All';
  const visibleLimit = window.innerWidth <= 820 ? 3 : window.innerWidth <= 1060 ? 4 : 7;
  let visibleCategories = uniqueCanonicalCategories.slice(0, visibleLimit);
  if (activeCategoryFilter && !visibleCategories.includes(activeCategoryFilter)) {
    visibleCategories = [...visibleCategories.slice(0, Math.max(0, visibleLimit - 1)), activeCategoryFilter];
  }
  const hiddenCategories = uniqueCanonicalCategories.filter(category => !visibleCategories.includes(category));
  const renderPill = canonicalCat => {
    const localizedLabel = getLocalizedCategory(canonicalCat);
    const isActive = activeCategoryFilter === canonicalCat;
    return `<button class="category-pill ${isActive ? 'active' : ''}" onclick="handleSelectCategory('${canonicalCat.replace(/'/g, "\\'")}')">${escapeHtml(localizedLabel)}</button>`;
  };
  let html = `<button class="category-pill ${activeCategoryFilter === null ? 'active' : ''}" onclick="handleSelectCategory(null)">${allLabel}</button>`;
  html += visibleCategories.map(renderPill).join('');
  if (hiddenCategories.length) {
    const hiddenActive = hiddenCategories.includes(activeCategoryFilter);
    html += `
      <details class="category-more ${hiddenActive ? 'active' : ''}">
        <summary>${currentLanguage === 'zh' ? '更多' : 'More'} <i data-lucide="chevron-down" aria-hidden="true"></i></summary>
        <div class="category-more-menu">${hiddenCategories.map(renderPill).join('')}</div>
      </details>`;
  }
  
  categoryFilterBar.innerHTML = html;
  lucide.createIcons();
}

// Handle category select
window.handleSelectCategory = function(canonicalCat) {
  document.querySelector('.category-more')?.removeAttribute('open');
  activeCategoryFilter = canonicalCat;
  renderCategoryFilterBar();
  renderSkillsGrid();
};

window.addEventListener('resize', () => {
  clearTimeout(categoryResizeTimer);
  categoryResizeTimer = setTimeout(renderCategoryFilterBar, 120);
});

// COLLECTION_PROJECT_STATE_HELPER_START
function resolveCollectionProjectState(
  collectionMembers,
  statusMap,
  enabledSkills,
  managedSkills = new Set(),
  detachedSkills = new Set()
) {
  const includeOwnership = arguments.length >= 4;
  const members = Array.isArray(collectionMembers) ? collectionMembers : [];
  const activeMembers = members.filter(
    member => member.collection?.effective_enabled
  );
  // A fully disabled collection still needs all physical member states so the
  // UI can distinguish "not installed" from files that are genuinely pending removal.
  const observedMembers = activeMembers.length ? activeMembers : members;
  const memberStatuses = observedMembers.map(
    member => statusMap[member.filename] || 'unloaded'
  );
  let physicalStatus = 'unloaded';
  if (memberStatuses.length && memberStatuses.every(status => status === 'synced')) {
    physicalStatus = 'synced';
  } else if (
    memberStatuses.some(status => status === 'synced' || status === 'out_of_sync')
  ) {
    physicalStatus = 'out_of_sync';
  }
  const state = {
    physicalStatus,
    isLocallyEnabled: activeMembers.length > 0 && activeMembers.every(
      member => enabledSkills.has(member.filename)
    )
  };
  if (includeOwnership) {
    state.isManaged = observedMembers.some(member => managedSkills.has(member.filename));
    state.isDetached = observedMembers.some(member => detachedSkills.has(member.filename));
  }
  return state;
}
// COLLECTION_PROJECT_STATE_HELPER_END

function renderSkillsGrid() {
  const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
  let filtered = buildDisplaySkills();
  if (navSkillCount) navSkillCount.textContent = filtered.length;
  
  // Filter by Search Query
  if (query) {
    filtered = filtered.filter(s => {
      const text = [
        s.title,
        s.description,
        s.filename,
        s.search_text || '',
        ...(s.tags || [])
      ].join(' ').toLowerCase();
      return text.includes(query);
    });
  }
  
  // Filter by Category
  if (activeCategoryFilter) {
    filtered = filtered.filter(s => {
      return getCanonicalCategory(s) === activeCategoryFilter;
    });
  }

  cardsGrid.innerHTML = '';
  if (filtered.length === 0) {
    if (skills.length === 0 && !query && !activeCategoryFilter) {
      cardsGrid.innerHTML = `
        <div class="empty-state first-run-empty" style="grid-column:1/-1;">
          <div class="empty-state-icon">🧭</div>
          <h4>${currentLanguage === 'zh' ? '从第一个技能开始' : 'Start with your first skill'}</h4>
          <p>${currentLanguage === 'zh' ? '导入已有 Skill，或创建一份自己的项目规范；之后关联项目并预览同步变更。' : 'Import an existing Skill or create your own guideline, then link a project and preview the sync.'}</p>
          <div class="first-run-steps">
            <span>1. ${currentLanguage === 'zh' ? '准备技能' : 'Prepare skills'}</span>
            <span>2. ${currentLanguage === 'zh' ? '关联项目' : 'Link a project'}</span>
            <span>3. ${currentLanguage === 'zh' ? '预览并同步' : 'Preview and sync'}</span>
          </div>
          <div class="first-run-actions">
            <button class="btn btn-primary" onclick="handleImportSkill()">${currentLanguage === 'zh' ? '开始导入' : 'Import a Skill'}</button>
            <button class="btn btn-secondary" onclick="handleCreateSkill()">${currentLanguage === 'zh' ? '新建技能' : 'Create a Skill'}</button>
          </div>
        </div>`;
      return;
    }
    cardsGrid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1;">
        <div class="empty-state-icon">🔍</div>
        <h4>${currentLanguage === 'zh' ? '未找到匹配的技能' : 'No matching skills found'}</h4>
        <p>${currentLanguage === 'zh' ? '请更换关键词或新建技能' : 'Change keywords or create a new skill'}</p>
      </div>`;
    return;
  }

  const activeProj = currentProjectPath ? projects.find(p => p.path === currentProjectPath) : null;
  const statusMap = activeProj ? (activeProj.skills_status || {}) : {};
  const managedSkills = new Set(activeProj ? (activeProj.managed_skills || []) : []);
  const detachedSkills = new Set(activeProj ? (activeProj.detached_skills || []) : []);
  const fragment = document.createDocumentFragment();

  filtered.forEach(skill => {
    const card = document.createElement('div');
    card.className = `skill-card skill-row${skill.is_collection ? ' collection-card' : ''}${skill.project_only ? ' project-only-card' : ''}`;
    card.dataset.filename = skill.filename;

    // Keep semantic tags local; list icons come from the shared Lucide system.
    const smart = getSmartEmojiAndTags(skill);
    const resolvedTags = smart.tags;

    let statusHTML = '';
    let isChecked = false;

    if (skill.project_only) {
      statusHTML = `<span class="status-badge library"><span class="status-dot"></span>${currentLanguage === 'zh' ? '项目独有 · 只读' : 'Project-only · Read-only'}</span>`;
    } else if (currentProjectPath && activeProj && !activeProj.error) {
      let physicalStatus = statusMap[skill.filename] || 'unloaded';
      let isLocallyEnabled = enabledSkills.has(skill.filename);
      let isManaged = managedSkills.has(skill.filename);
      let isDetached = detachedSkills.has(skill.filename);
      if (skill.is_collection) {
        const collectionState = resolveCollectionProjectState(
          skill.collection_members,
          statusMap,
          enabledSkills,
          managedSkills,
          detachedSkills
        );
        isLocallyEnabled = collectionState.isLocallyEnabled;
        physicalStatus = collectionState.physicalStatus;
        isManaged = collectionState.isManaged;
        isDetached = collectionState.isDetached;
      }

      if (isLocallyEnabled) {
        isChecked = true;
        if (physicalStatus === 'synced') {
          statusHTML = `<span class="status-badge synced"><span class="status-dot"></span>${locales[currentLanguage].statusSynced}</span>`;
        } else if (physicalStatus === 'out_of_sync') {
          statusHTML = `<span class="status-badge out-of-sync"><span class="status-dot"></span>${locales[currentLanguage].statusUpdated}</span>`;
        } else {
          statusHTML = `<span class="status-badge pending-mount"><span class="status-dot"></span>${locales[currentLanguage].statusPendingMount}</span>`;
        }
      } else {
        isChecked = false;
        if (isDetached && (physicalStatus === 'synced' || physicalStatus === 'out_of_sync')) {
          const retainedHint = currentLanguage === 'zh'
            ? '该项目副本曾被修改；SkillHub 已停止管理并保留它。'
            : 'This project copy was modified; SkillHub stopped managing it and retained it.';
          statusHTML = `<span class="status-badge library" title="${escapeHtml(retainedHint)}"><span class="status-dot"></span>${locales[currentLanguage].statusProjectCustom}</span>`;
        } else if (physicalStatus === 'synced' || physicalStatus === 'out_of_sync') {
          const removalHint = currentLanguage === 'zh'
            ? (isManaged
              ? '已取消选择；项目副本将在确认同步后备份并移除。'
              : '检测到未登记的项目副本；同步预览会显示内容差异，确认后备份并移除。')
            : (isManaged
              ? 'Deselected; the project copy will be backed up and removed after sync confirmation.'
              : 'An unregistered project copy was found; sync preview will show content differences before backup and removal.');
          statusHTML = `<span class="status-badge pending-unmount" title="${escapeHtml(removalHint)}"><span class="status-dot"></span>${locales[currentLanguage].statusPendingUnmount}</span>`;
        } else {
          statusHTML = `<span class="status-badge unloaded"><span class="status-dot"></span>${locales[currentLanguage].statusUnloaded}</span>`;
        }
      }
    } else {
      const globalState = skill.codex_global_status || 'unsupported';
      const globalButton = {
        enabled: {
          icon: 'circle-check',
          label: currentLanguage === 'zh' ? '已全局' : 'Global',
          title: currentLanguage === 'zh' ? '点击管理这个 Skill 的全局目标' : 'Manage this Skill\'s global targets'
        },
        outdated: {
          icon: 'refresh-cw',
          label: currentLanguage === 'zh' ? '更新全局' : 'Update',
          title: currentLanguage === 'zh' ? '源 Skill 已更新，点击刷新所选目标' : 'Source changed; refresh selected targets'
        },
        partial: {
          icon: 'circle-dot-dashed',
          label: currentLanguage === 'zh' ? '部分全局' : 'Partial',
          title: currentLanguage === 'zh' ? '只有部分 Skill 或目标已启用，点击补齐' : 'Only some Skills or targets are enabled; click to complete'
        },
        conflict: {
          icon: 'triangle-alert',
          label: currentLanguage === 'zh' ? '名称冲突' : 'Conflict',
          title: currentLanguage === 'zh' ? '至少一个目标存在同名冲突，无法覆盖' : 'At least one selected target has a name conflict'
        },
        disabled: {
          icon: 'globe-2',
          label: currentLanguage === 'zh' ? '全局启用' : 'Enable',
          title: currentLanguage === 'zh' ? '为这个 Skill 选择要同步到的 Agent' : 'Choose the agents for this Skill'
        },
        unsupported: {
          icon: 'minus',
          label: currentLanguage === 'zh' ? '不可启用' : 'Unavailable',
          title: currentLanguage === 'zh' ? '该条目不是可执行 Skill' : 'This entry is not an executable Skill'
        }
      }[globalState] || {
        icon: 'minus',
        label: currentLanguage === 'zh' ? '不可启用' : 'Unavailable',
        title: currentLanguage === 'zh' ? '全局目标路径无效' : 'A global target path is invalid'
      };
      statusHTML = `<button type="button" class="codex-global-button ${escapeHtml(globalState)} js-codex-global-action" title="${escapeHtml(globalButton.title)}" aria-label="${escapeHtml(globalButton.title)}" ${['conflict', 'unsupported'].includes(globalState) ? 'disabled' : ''}>
        <i data-lucide="${globalButton.icon}"></i><span>${escapeHtml(globalButton.label)}</span>
      </button>`;
    }

    // Display translations are metadata-only; the source SKILL.md stays intact.
    const resolvedTitle = skill.display_title || skill.title;
    let resolvedDesc = skill.display_description || skill.description;
    if (skill.description === '此技能暂无详细描述信息。') {
      resolvedDesc = locales[currentLanguage].defaultDesc;
    }

    // Split Chinese and English parts for clean layout
    let mainTitle = resolvedTitle;
    let subTitle = '';
    const parenMatch = resolvedTitle.match(/^([^()（）]+)[(（]([^)）]+)[)）]/);
    if (parenMatch) {
      mainTitle = parenMatch[1].trim();
      subTitle = parenMatch[2].trim();
    }

    // Translate Tags
    const translatedTags = resolvedTags.map(t => tagTranslations[currentLanguage]?.[t] || t);
    const tagsHTML = translatedTags.map(t => `<span class="badge">${escapeHtml(t)}</span>`).join('');
    const safeTitle = escapeHtml(resolvedTitle);
    const safeMainTitle = escapeHtml(mainTitle);
    const safeSubTitle = escapeHtml(subTitle);
    const safeDesc = escapeHtml(resolvedDesc);
    const displayFilename = skill.is_collection
      ? `${skill.collection_child_count} ${currentLanguage === 'zh' ? '个子技能' : 'child skills'}`
      : (skill.display_filename || skill.filename);
    const safeFilename = escapeHtml(displayFilename);
    const cardTitle = skill.is_collection
      ? currentProjectPath
        ? (currentLanguage === 'zh' ? `点击管理 ${resolvedTitle} 的子技能` : `Manage child skills in ${resolvedTitle}`)
        : (currentLanguage === 'zh' ? `点击查看 ${resolvedTitle} 的子技能` : `View child skills in ${resolvedTitle}`)
      : skill.project_only
        ? (currentLanguage === 'zh' ? `只读查看项目 Skill：${resolvedTitle}` : `View project Skill read-only: ${resolvedTitle}`)
        : (currentLanguage === 'zh' ? `点击查看 ${resolvedTitle} 的 Markdown 文档` : `Click to view the Markdown document for ${resolvedTitle}`);
    const localizedCategory = getLocalizedCategory(getCanonicalCategory(skill));
    const collectionActionLabel = currentProjectPath
      ? (currentLanguage === 'zh' ? '管理子技能' : 'Manage child skills')
      : (currentLanguage === 'zh' ? '查看子技能' : 'View child skills');
    const actionButtons = skill.project_only
      ? ''
      : skill.is_collection
      ? `
          <button type="button" class="row-action-button js-edit-skill" title="${collectionActionLabel}" aria-label="${collectionActionLabel}">
            <i data-lucide="list-tree"></i>
          </button>`
      : `
          <button type="button" class="row-action-button js-edit-skill" title="${escapeHtml(locales[currentLanguage].btnEditSkill)}" aria-label="${escapeHtml(locales[currentLanguage].btnEditSkill)}">
            <i data-lucide="pencil"></i>
          </button>
          <button type="button" class="row-action-button danger js-delete-skill" title="${currentLanguage === 'zh' ? '移至回收区' : 'Move to trash'}" aria-label="${currentLanguage === 'zh' ? '移至回收区' : 'Move to trash'}">
            <i data-lucide="trash-2"></i>
          </button>`;
    card.innerHTML = `
      <div class="skill-row-primary">
        <div class="skill-emoji" aria-hidden="true"><i data-lucide="${getSkillListIcon(skill)}"></i></div>
        <div class="skill-info">
          <div class="skill-title-line">
            <h4 class="skill-title" title="${safeTitle}">${safeMainTitle}</h4>
            ${subTitle ? `<span class="skill-subtitle" title="${safeSubTitle}">${safeSubTitle}</span>` : ''}
          </div>
          <span class="skill-file" title="${safeFilename}">${skill.is_collection ? '<i data-lucide="layers-3"></i>' : ''}${safeFilename}</span>
        </div>
      </div>
      <p class="skill-row-description" title="${safeDesc}">${safeDesc}</p>
      <div class="skill-row-category">
        <span>${escapeHtml(localizedCategory)}</span>
        <div class="card-tags">${tagsHTML}</div>
      </div>
      <div class="skill-row-status">${statusHTML}</div>
      <div class="skill-row-actions">
        ${currentProjectPath && activeProj && !activeProj.error && !skill.project_only ? `
          <label class="switch row-mount-toggle" title="${locales[currentLanguage].toggleLabel}">
            <input type="checkbox" class="js-toggle-skill" ${isChecked ? 'checked' : ''}>
            <span class="slider"></span>
          </label>` : ''}
        <div class="row-secondary-actions">${actionButtons}</div>
      </div>`;
    card.title = cardTitle;
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    card.setAttribute('aria-label', cardTitle);
    fragment.appendChild(card);
  });
  cardsGrid.appendChild(fragment);
  lucide.createIcons();
}

function globalTargetIcon(targetId) {
  return {
    codex: 'square-terminal',
    claude_code: 'braces',
    cursor: 'mouse-pointer-2',
    cline: 'bot',
    opencode: 'terminal',
    windsurf: 'waves',
    antigravity: 'orbit',
    vscode: 'code-2',
    claude_desktop: 'package',
  }[targetId] || 'folder';
}

function globalTargetStateLabel(target) {
  if (target.available === false || target.status === 'unavailable') {
    return currentLanguage === 'zh' ? '未检测到' : 'Not detected';
  }
  if (target.status === 'conflict') return currentLanguage === 'zh' ? '名称冲突' : 'Conflict';
  if (target.status === 'outdated') return currentLanguage === 'zh' ? '需要更新' : 'Update needed';
  if (target.status === 'partial') return currentLanguage === 'zh' ? '部分成员' : 'Some members';
  if (target.enabled) {
    if (target.requires_manual_install) return currentLanguage === 'zh' ? 'ZIP 已生成' : 'ZIP ready';
    return currentLanguage === 'zh' ? '已启用' : 'Enabled';
  }
  return currentLanguage === 'zh' ? '未启用' : 'Not enabled';
}

function openGlobalTargetModal(skill) {
  if (!skill || !globalTargetModal || !skillGlobalTargets) return;
  pendingGlobalTargetSkill = skill;
  const title = skill.display_title || skill.title || skill.filename;
  document.getElementById('global-target-modal-title').textContent = currentLanguage === 'zh'
    ? '选择全局目标'
    : 'Choose global targets';
  document.getElementById('global-target-modal-subtitle').textContent = title;
  document.getElementById('global-target-modal-intro').textContent = currentLanguage === 'zh'
    ? '这个 Skill 可以独立选择要同步到的 Agent；未检测到现有 Skill 目录的客户端不可选择，也不会自动创建目录。'
    : 'Choose the agents for this Skill. Clients without an existing Skill directory cannot be selected, and their directories will not be created.';
  document.getElementById('global-target-modal-note').textContent = currentLanguage === 'zh'
    ? '不勾选任何目标将移除这个 Skill 的全部全局入口。Claude Desktop 选项只生成上传 ZIP，不代表已经上传到账号。'
    : 'Selecting no targets removes every managed global entry for this Skill. Claude Desktop only exports an upload ZIP.';
  document.getElementById('global-target-modal-cancel').textContent = currentLanguage === 'zh' ? '取消' : 'Cancel';
  document.querySelector('#global-target-modal-apply span').textContent = currentLanguage === 'zh' ? '应用选择' : 'Apply selection';

  const states = Array.isArray(skill.global_target_states) ? skill.global_target_states : [];
  const hasExistingSelection = states.some(target => target.enabled || target.status === 'partial');
  skillGlobalTargets.innerHTML = globalSkillTargetOptions.map(option => {
    const target = states.find(item => item.id === option.id) || {
      ...option, enabled: false, status: 'disabled'
    };
    const selected = hasExistingSelection
      ? (target.enabled || target.status === 'partial')
      : globalSkillTargets.includes(option.id);
    const conflict = target.status === 'conflict';
    const unavailable = option.available === false
      || target.available === false
      || target.status === 'unavailable';
    const blocked = conflict || unavailable;
    const secondary = option.requires_manual_install
      ? (currentLanguage === 'zh' ? '生成 Claude 上传 ZIP' : 'Create Claude upload ZIP')
      : option.path;
    return `
      <label class="global-target-option ${conflict ? 'conflict' : ''} ${unavailable ? 'unavailable' : ''}" data-target="${escapeHtml(option.id)}" aria-disabled="${blocked ? 'true' : 'false'}">
        <input type="checkbox" value="${escapeHtml(option.id)}" ${selected && !blocked ? 'checked' : ''} ${blocked ? 'disabled' : ''}>
        <span class="global-target-icon"><i data-lucide="${globalTargetIcon(option.id)}"></i></span>
        <span class="global-target-copy">
          <strong>${escapeHtml(option.label)}</strong>
          <small title="${escapeHtml(secondary)}">${escapeHtml(secondary)}</small>
          <span class="global-target-state ${escapeHtml(target.status || 'disabled')}">${escapeHtml(globalTargetStateLabel(target))}</span>
        </span>
        <span class="global-target-check"><i data-lucide="${conflict ? 'triangle-alert' : unavailable ? 'circle-off' : 'check'}"></i></span>
      </label>`;
  }).join('');
  activateModal(globalTargetModal, skillGlobalTargets.querySelector('input:not([disabled])'));
  lucide.createIcons();
}

function closeGlobalTargetModal() {
  deactivateModal(globalTargetModal);
  pendingGlobalTargetSkill = null;
}

async function applySkillGlobalTargets() {
  const skill = pendingGlobalTargetSkill;
  if (!skill) return;
  const targetIds = Array.from(
    skillGlobalTargets.querySelectorAll('input[type="checkbox"]:checked')
  ).map(input => input.value);
  const applyButton = document.getElementById('global-target-modal-apply');
  applyButton.disabled = true;
  try {
    const result = skill.is_collection
      ? await window.pywebview.api.set_skills_global_targets(
          skill.codex_global_members || [], targetIds
        )
      : await window.pywebview.api.set_skill_global_targets(skill.filename, targetIds);
    if (result.error) throw new Error(result.error);
    deactivateModal(globalTargetModal);
    pendingGlobalTargetSkill = null;
    await fetchSkills();
    const manualNote = targetIds.includes('claude_desktop')
      ? (currentLanguage === 'zh' ? '；Claude Desktop ZIP 已生成，仍需手动上传' : '; Claude Desktop ZIP exported for manual upload')
      : '';
    showToast(
      (currentLanguage === 'zh'
        ? `已应用 ${targetIds.length} 个全局目标`
        : `Applied ${targetIds.length} global targets`) + manualNote,
      'success'
    );
  } catch (error) {
    showToast(
      (currentLanguage === 'zh' ? '全局目标更新失败: ' : 'Failed to update global targets: ') + error,
      'error'
    );
  } finally {
    applyButton.disabled = false;
  }
}

function handleCodexGlobalButton(skill) {
  openGlobalTargetModal(skill);
}

// ------------------------------------------
// Event Handlers
// ------------------------------------------

async function handlePickProject() {
  try {
    const result = await window.pywebview.api.add_project_via_dialog();
    if (!result) return;
    if (result.error) {
      showToast(currentLanguage === 'zh' ? '该项目已关联' : 'This project is already linked', 'warning');
      return;
    }
    showToast(locales[currentLanguage].toastAssocSuccess + result.name, 'success');
    currentProjectPath = result.path;
    await fetchProjects();
    handleSelectProject(result.path);
  } catch (e) {
    showToast((currentLanguage === 'zh' ? '关联项目失败: ' : 'Failed to link project: ') + e, 'error');
  }
}

async function handleCreateSkill() {
  const filename = await showCustomDialog({
    title: currentLanguage === 'zh' ? '新建技能' : 'New Skill',
    message: currentLanguage === 'zh'
      ? '输入技能名称即可，文件名会自动补齐 .md；创建后可继续编辑适用场景和具体规则。'
      : 'Enter a skill name. The .md extension is added automatically, and you can edit its triggers and rules next.',
    emoji: '💡',
    isPrompt: true,
    placeholder: currentLanguage === 'zh' ? '例如：代码安全规范' : 'e.g. Code Safety'
  });
  if (!filename) return;
  try {
    const result = await window.pywebview.api.create_skill(filename);
    if (result.error) {
      showToast(currentLanguage === 'zh' ? result.error : 'File already exists', 'warning');
      return;
    }
    showToast(locales[currentLanguage].toastCreateSuccess + result.filename, 'success');
    await fetchSkills();
    openEditorModal(result.filename);
  } catch (e) {
    showToast((currentLanguage === 'zh' ? '创建失败: ' : 'Failed to create skill: ') + e, 'error');
  }
}

function handleSelectProject(path) {
  if (currentProjectPath === path) {
    currentProjectPath = null;
    pendingSyncRequestId++;
    clearTimeout(pendingSyncTimer);
    pendingSyncSummary = null;
    enabledSkills.clear();
    currentProjectTitle.textContent = locales[currentLanguage].noProjectTitle;
    currentProjectDesc.textContent = locales[currentLanguage].noProjectDesc;
    syncBtn.setAttribute('disabled', 'true');
    undoSyncBtn.setAttribute('disabled', 'true');
    syncBtn.classList.remove('pulsing-btn', 'active');
    renderProjectsList();
    renderCategoryFilterBar();
    renderSkillsGrid();
    updateStatistics();
    lucide.createIcons();
    showToast(locales[currentLanguage].exitProjectMode, 'success');
    return;
  }

  const proj = projects.find(p => p.path === path);
  if (!proj) return;
  if (proj.error) showToast(currentLanguage === 'zh' ? `项目路径无法访问: ${proj.error}` : `Project path inaccessible: ${proj.error}`, 'warning');
  currentProjectPath = path;
  _loadProjectState(proj);
}

// Reload the currently selected project's data without toggling selection
function refreshCurrentProject() {
  if (!currentProjectPath) return;
  const proj = projects.find(p => p.path === currentProjectPath);
  if (!proj) return;
  _loadProjectState(proj);
}

function _loadProjectState(proj) {
  enabledSkills.clear();
  if (Array.isArray(proj.enabled_skills)) {
    proj.enabled_skills.forEach(filename => enabledSkills.add(filename));
  } else {
    Object.entries(proj.skills_status || {}).forEach(([fname, status]) => {
      if (status === 'synced' || status === 'out_of_sync') enabledSkills.add(fname);
    });
  }
  currentProjectTitle.textContent = proj.name;
  currentProjectDesc.innerHTML = `<i data-lucide="folder" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:4px;"></i>${escapeHtml(proj.path)}`;
  syncBtn.removeAttribute('disabled');
  syncBtn.classList.add('pulsing-btn');
  undoSyncBtn.disabled = !proj.can_undo_sync;
  renderProjectsList();
  renderCategoryFilterBar();
  renderSkillsGrid();
  updateStatistics();
  queuePendingSyncSummary();
  lucide.createIcons();
}

function handleToggleSkill(filename, isEnabled) {
  if (isEnabled) enabledSkills.add(filename);
  else enabledSkills.delete(filename);
  syncBtn.classList.add('active');
  renderSkillsGrid();
  queuePendingSyncSummary();
}

function handleToggleCollectionMount(collectionSkill, isEnabled) {
  collectionSkill.collection_members
    .filter(member => member.collection?.effective_enabled)
    .forEach(member => {
      if (isEnabled) enabledSkills.add(member.filename);
      else enabledSkills.delete(member.filename);
    });
  syncBtn.classList.add('active');
  renderSkillsGrid();
  queuePendingSyncSummary();
}

function getCollectionDisplaySkill(collectionId) {
  return buildDisplaySkills().find(
    skill => skill.is_collection && skill.collection_id === collectionId
  );
}

function openCollectionModal(collectionId) {
  const collectionSkill = getCollectionDisplaySkill(collectionId);
  if (!collectionSkill) return;
  const readOnly = !currentProjectPath;
  activeCollectionId = collectionId;
  collectionModalTitle.textContent = collectionSkill.title;
  const hasPrimary = collectionSkill.collection_members.some(
    member => member.filename === collectionId
  );
  const controller = collectionSkill.collection_controller;
  const controllerEnabled = collectionSkill.collection_controller_enabled;
  const childCount = collectionSkill.collection_child_count;
  collectionModalSummary.textContent = currentLanguage === 'zh'
    ? `${hasPrimary ? '1 个主控 + ' : ''}${childCount} 个子技能；${readOnly ? '可分别发布到所选全局目标' : '主控关闭时整组暂停'}`
    : `${hasPrimary ? '1 controller + ' : ''}${childCount} child skills; ${readOnly ? 'each can publish to selected global targets' : 'the controller pauses the whole collection'}`;
  collectionModalHint.textContent = readOnly
    ? (currentLanguage === 'zh'
      ? '这里可以为每个子 Skill 单独选择全局目标，与项目启用状态互不影响。'
      : 'Each child Skill can choose its own global targets independently of project enablement.')
    : currentLanguage === 'zh'
      ? (controller && !controllerEnabled
        ? '主控已关闭：子技能选择已保留，但不会生效；下次同步会从项目移除整组。'
        : '停用不会删除文件；项目将在下次同步时应用变更。')
      : (controller && !controllerEnabled
        ? 'Controller is off: child choices are preserved but inactive; the next sync removes the collection.'
        : 'Disabling keeps source files; the next sync applies the change to projects.');

  const orderedMembers = [...collectionSkill.collection_members].sort((left, right) => {
    if (left.collection?.is_controller) return -1;
    if (right.collection?.is_controller) return 1;
    return 0;
  });
  collectionMembersList.innerHTML = orderedMembers.map(member => {
    const displayFilename = member.display_filename || member.filename;
    const title = member.display_title || member.title;
    const description = member.display_description || member.description;
    const enabled = Boolean(member.collection?.enabled);
    const effectiveEnabled = Boolean(member.collection?.effective_enabled);
    const isController = Boolean(member.collection?.is_controller);
    const pausedByController = Boolean(controller && !controllerEnabled && !isController);
    const stateText = isController
      ? (enabled
        ? (currentLanguage === 'zh' ? '主控开启' : 'Controller on')
        : (currentLanguage === 'zh' ? '主控关闭' : 'Controller off'))
      : pausedByController && enabled
        ? (currentLanguage === 'zh' ? '选择已保留' : 'Choice preserved')
        : effectiveEnabled
          ? (currentLanguage === 'zh' ? '启用' : 'On')
          : (currentLanguage === 'zh' ? '停用' : 'Off');
    const smart = getSmartEmojiAndTags(member);
    const globalState = member.codex_global_status || 'disabled';
    const globalEnabled = member.codex_global_enabled;
    const globalActionLabel = globalState === 'conflict'
      ? (currentLanguage === 'zh' ? '名称冲突' : 'Conflict')
      : globalState === 'outdated'
        ? (currentLanguage === 'zh' ? '更新' : 'Update')
        : globalState === 'partial'
          ? (currentLanguage === 'zh' ? '补齐目标' : 'Complete')
        : globalEnabled
          ? (currentLanguage === 'zh' ? '已全局' : 'Global')
          : (currentLanguage === 'zh' ? '全局启用' : 'Enable');
    const globalActionIcon = globalState === 'conflict'
      ? 'triangle-alert'
      : globalState === 'outdated'
        ? 'refresh-cw'
        : globalState === 'partial'
          ? 'circle-dot-dashed'
        : globalEnabled ? 'circle-check' : 'globe-2';
    return `
      <div class="collection-member ${!readOnly && effectiveEnabled ? 'enabled' : ''} ${!readOnly && pausedByController ? 'controller-paused' : ''} ${isController ? 'collection-controller' : ''}" data-filename="${escapeHtml(member.filename)}">
        <div class="collection-member-main">
          <span class="collection-member-emoji">${escapeHtml(smart.emoji)}</span>
          <div class="collection-member-copy">
            <div class="collection-member-title">${escapeHtml(title)}${isController ? `<span class="controller-badge">${currentLanguage === 'zh' ? '主控' : 'Controller'}</span>` : ''}</div>
            <div class="collection-member-description">${escapeHtml(description)}</div>
            <div class="collection-member-file">${escapeHtml(displayFilename)}</div>
          </div>
        </div>
        <div class="collection-member-actions">
          <button type="button" class="btn btn-secondary btn-icon js-view-collection-member" data-filename="${escapeHtml(member.filename)}" title="${currentLanguage === 'zh' ? '查看文档' : 'View docs'}">
            <i data-lucide="eye" style="width:14px;height:14px;"></i>
          </button>
          ${readOnly ? `
            <button type="button" class="codex-global-button compact ${escapeHtml(globalState)} js-collection-global-action" data-filename="${escapeHtml(member.filename)}" data-state="${escapeHtml(globalState)}" ${globalState === 'conflict' ? 'disabled' : ''}>
              <i data-lucide="${globalActionIcon}"></i><span>${escapeHtml(globalActionLabel)}</span>
            </button>` : `
            <span class="collection-member-state">${stateText}</span>
            <label class="switch">
              <input type="checkbox" class="js-collection-member-toggle" data-filename="${escapeHtml(member.filename)}" ${enabled ? 'checked' : ''} ${pausedByController ? 'disabled' : ''}>
              <span class="slider"></span>
            </label>`}
        </div>
      </div>`;
  }).join('');
  activateModal(
    collectionModal,
    collectionModal.querySelector(
      readOnly
        ? '.js-collection-global-action:not([disabled])'
        : '.js-collection-member-toggle:not([disabled])'
    )
  );
  lucide.createIcons();
}

function closeCollectionModal() {
  deactivateModal(collectionModal);
  activeCollectionId = null;
}

collectionMembersList.addEventListener('change', async event => {
  if (!event.target.matches('.js-collection-member-toggle')) return;
  if (!currentProjectPath) {
    const collectionId = activeCollectionId;
    if (collectionId) openCollectionModal(collectionId);
    showToast(
      currentLanguage === 'zh'
        ? '请先选择目标项目，再调整子技能状态。'
        : 'Select a target project before changing child skill state.',
      'warning'
    );
    return;
  }
  const input = event.target;
  const filename = input.dataset.filename;
  const enabled = input.checked;
  const collectionBefore = getCollectionDisplaySkill(activeCollectionId);
  const memberBefore = collectionBefore?.collection_members?.find(
    item => item.filename === filename
  );
  input.disabled = true;
  try {
    const result = await window.pywebview.api.set_collection_member_enabled(
      activeCollectionId,
      filename,
      enabled
    );
    if (result.error) throw new Error(result.error);
    if (!enabled && !memberBefore?.collection?.is_controller) {
      enabledSkills.delete(filename);
    }
    await fetchSkills();
    if (currentProjectPath) {
      syncBtn.classList.add('active');
      queuePendingSyncSummary();
    }
    const collectionId = activeCollectionId;
    if (collectionId) openCollectionModal(collectionId);
    const member = getCollectionDisplaySkill(collectionId)?.collection_members?.find(
      item => item.filename === filename
    );
    const displayFilename = member?.display_filename || filename;
    showToast(
      currentLanguage === 'zh'
        ? `${displayFilename} 已${enabled ? '启用' : '停用'}`
        : `${displayFilename} ${enabled ? 'enabled' : 'disabled'}`,
      'success'
    );
  } catch (error) {
    input.checked = !enabled;
    input.disabled = false;
    showToast(
      (currentLanguage === 'zh' ? '更新子技能失败: ' : 'Failed to update child skill: ') + error,
      'error'
    );
  }
});

collectionMembersList.addEventListener('click', event => {
  const globalButton = event.target.closest('.js-collection-global-action');
  if (globalButton) {
    const filename = globalButton.dataset.filename;
    const member = getCollectionDisplaySkill(activeCollectionId)?.collection_members?.find(
      item => item.filename === filename
    );
    closeCollectionModal();
    if (member) openGlobalTargetModal(member);
    return;
  }
  const button = event.target.closest('.js-view-collection-member');
  if (!button) return;
  const filename = button.dataset.filename;
  closeCollectionModal();
  openSkillViewer(filename);
});

async function handleDeleteProject(event, path) {
  event.stopPropagation();
  const confirmed = await showCustomDialog({
    title: currentLanguage === 'zh' ? '解除关联' : 'Unlink Project',
    message: locales[currentLanguage].confirmRemove,
    emoji: '📂'
  });
  if (!confirmed) return;
  try {
    await window.pywebview.api.delete_project(path);
    showToast(locales[currentLanguage].toastRemoveSuccess, 'success');
    if (currentProjectPath === path) {
      currentProjectPath = null;
      pendingSyncRequestId++;
      clearTimeout(pendingSyncTimer);
      pendingSyncSummary = null;
      currentProjectTitle.textContent = locales[currentLanguage].noProjectTitle;
      currentProjectDesc.textContent = locales[currentLanguage].noProjectDesc;
      syncBtn.setAttribute('disabled', 'true');
      undoSyncBtn.setAttribute('disabled', 'true');
      syncBtn.classList.remove('pulsing-btn', 'active');
    }
    await fetchProjects();
    renderSkillsGrid();
    updateStatistics();
  } catch (e) {
    showToast((currentLanguage === 'zh' ? '移除失败: ' : 'Failed to remove: ') + e, 'error');
  }
}

async function handleSyncSkills() {
  if (!currentProjectPath) return;
  const originalHTML = syncBtn.innerHTML;
  let needsSyncAttention = syncBtn.classList.contains('active');
  const setBusy = label => {
    syncBtn.setAttribute('disabled', 'true');
    syncBtn.classList.remove('active');
    syncBtn.innerHTML = `<span class="loading-spinner"></span> ${label}`;
    lucide.createIcons();
  };
  const restoreButton = () => {
    syncBtn.innerHTML = originalHTML;
    if (currentProjectPath) syncBtn.removeAttribute('disabled');
    syncBtn.classList.add('pulsing-btn');
    if (needsSyncAttention) syncBtn.classList.add('active');
    else syncBtn.classList.remove('active');
    lucide.createIcons();
  };

  setBusy(locales[currentLanguage].checkingBtn);

  try {
    const selectedSkills = Array.from(enabledSkills);
    let preview = await window.pywebview.api.preview_sync(currentProjectPath, selectedSkills);
    if (preview.error) throw new Error(preview.error);

    const changedCount = preview.summary.add + (preview.summary.adopt || 0) + preview.summary.modify + preview.summary.delete + preview.summary.preserve + (preview.scope_conflict_count || 0);
    if (changedCount === 0) {
      needsSyncAttention = false;
      showToast(locales[currentLanguage].syncPreviewNoChanges, 'success');
      return;
    }

    restoreButton();
    const confirmed = await showStructuredReview(buildSyncReview(preview));
    if (!confirmed) return;

    let acceptedBundleFiles = false;
    if (preview.has_restricted_bundle_files) {
      acceptedBundleFiles = await showStructuredReview({
        title: currentLanguage === 'zh' ? '授权 Bundle 额外文件' : 'Authorize Extra Bundle Files',
        kicker: currentLanguage === 'zh' ? '额外写入范围' : 'Additional write scope',
        intro: currentLanguage === 'zh'
          ? '以下文件位于 README 和 .agent/skills 之外，将写入项目目录。'
          : 'These files are outside README and .agent/skills and will be written into the project.',
        metrics: [{ value: preview.restricted_bundle_files.length, label: currentLanguage === 'zh' ? '额外文件' : 'Extra files', tone: 'warning' }],
        sections: [{ title: currentLanguage === 'zh' ? '待授权路径' : 'Paths to authorize', items: preview.restricted_bundle_files }],
        confirmText: currentLanguage === 'zh' ? '授权这些文件' : 'Authorize Files',
        danger: true
      });
      if (!acceptedBundleFiles) return;
    }

    setBusy(locales[currentLanguage].syncingBtn);
    let result = await window.pywebview.api.sync_skills(
      currentProjectPath,
      selectedSkills,
      Boolean(preview.has_conflicts),
      preview.plan_token,
      Boolean(acceptedBundleFiles)
    );
    if (result.requires_confirmation) {
      preview = result.preview;
      restoreButton();
      const reconfirmed = await showStructuredReview(buildSyncReview(preview));
      if (!reconfirmed) return;
      acceptedBundleFiles = false;
      if (preview.has_restricted_bundle_files) {
        acceptedBundleFiles = await showStructuredReview({
          title: currentLanguage === 'zh' ? '重新授权 Bundle 额外文件' : 'Reauthorize Extra Bundle Files',
          kicker: currentLanguage === 'zh' ? '同步计划已变化' : 'Sync plan changed',
          intro: currentLanguage === 'zh' ? '磁盘状态已变化，请重新确认额外写入路径。' : 'Disk state changed; review the extra paths again.',
          metrics: [{ value: preview.restricted_bundle_files.length, label: currentLanguage === 'zh' ? '额外文件' : 'Extra files', tone: 'warning' }],
          sections: [{ title: currentLanguage === 'zh' ? '待授权路径' : 'Paths to authorize', items: preview.restricted_bundle_files }],
          confirmText: currentLanguage === 'zh' ? '授权这些文件' : 'Authorize Files',
          danger: true
        });
        if (!acceptedBundleFiles) return;
      }
      setBusy(locales[currentLanguage].syncingBtn);
      result = await window.pywebview.api.sync_skills(
        currentProjectPath,
        selectedSkills,
        true,
        preview.plan_token,
        Boolean(acceptedBundleFiles)
      );
    }
    if (result.requires_bundle_file_confirmation) {
      preview = result.preview;
      restoreButton();
      acceptedBundleFiles = await showCustomDialog({
        title: currentLanguage === 'zh' ? '授权 Bundle 额外文件' : 'Authorize Extra Bundle Files',
        message: preview.restricted_bundle_files.map(path => `• ${path}`).join('\n'),
        emoji: '⚠️',
        confirmText: currentLanguage === 'zh' ? '授权这些文件' : 'Authorize Files'
      });
      if (!acceptedBundleFiles) return;
      setBusy(locales[currentLanguage].syncingBtn);
      result = await window.pywebview.api.sync_skills(
        currentProjectPath,
        selectedSkills,
        Boolean(preview.has_conflicts),
        preview.plan_token,
        true
      );
    }
    if (result.error) throw new Error(result.error);
    needsSyncAttention = false;
    showToast(locales[currentLanguage].toastSyncSuccess + result.synced_count + (currentLanguage === 'zh' ? ' 项技能' : ' skills'), 'success');
    await fetchProjects();
    refreshCurrentProject();
  } catch (e) {
    needsSyncAttention = true;
    showToast(locales[currentLanguage].toastSyncFail + e, 'error');
  } finally {
    restoreButton();
    if (currentProjectPath) queuePendingSyncSummary();
  }
}

function formatImportPreview(preview) {
  const isZh = currentLanguage === 'zh';
  const kindLabels = {
    markdown: isZh ? 'Markdown 技能' : 'Markdown skill',
    standard: isZh ? '标准 SKILL.md 技能包' : 'Standard SKILL.md package',
    collection: isZh ? '标准技能集合' : 'Standard skill collection',
    bundle: isZh ? 'SkillHub 组合技能包' : 'SkillHub bundle'
  };
  const changeLabels = {
    added_frontmatter: isZh ? '已补充完整元数据' : 'Added complete metadata',
    completed_frontmatter: isZh ? '已补齐缺失元数据' : 'Completed missing metadata',
    normalized_metadata: isZh ? '已规范化元数据格式' : 'Normalized metadata',
    converted_to_utf8: isZh ? '已转换为 UTF-8' : 'Converted to UTF-8',
    completed_standard_skill_metadata: isZh ? '已补齐 SKILL.md 的 name/description' : 'Completed SKILL.md name/description',
    created_bundle_readme: isZh ? '已为组合技能创建 README.md' : 'Created bundle README.md',
    ai_optimized: isZh ? 'AI 已优化入口文档' : 'AI optimized the entry document'
  };
  const processingMode = preview.ai_used
    ? (isZh ? '本地规则体检 + AI 优化' : 'Local validation + AI optimization')
    : preview.ai_requested
      ? (isZh ? '本地规则体检（AI 已回退）' : 'Local validation (AI fallback)')
      : (isZh ? '本地规则体检（未调用 AI）' : 'Local validation (AI not called)');
  const compatibilityStatusLabels = {
    ready: isZh ? '直接兼容' : 'ready',
    adapted: isZh ? '由 SkillHub 适配' : 'adapted by SkillHub',
    warning: isZh ? '需审阅权限' : 'review permissions',
    error: isZh ? '暂不可发布' : 'not publishable'
  };
  const appendCompatibility = (compatibility, indent = '') => {
    const targets = Object.values(compatibility?.targets || {});
    targets.forEach(target => {
      const status = compatibilityStatusLabels[target.status] || target.status;
      const detail = isZh ? target.detail_zh : target.detail_en;
      lines.push(`${indent}• ${target.label}: ${status} — ${detail || ''}`);
    });
  };
  const lines = [
    `${isZh ? '来源' : 'Source'}: ${preview.source_name}`,
    `${isZh ? '类型' : 'Type'}: ${kindLabels[preview.kind] || preview.kind}`,
    `${isZh ? '处理方式' : 'Processing'}: ${processingMode}`
  ];
  if (preview.display_translation_used) {
    lines.push(
      `${isZh ? '界面说明' : 'UI description'}: ${
        isZh ? '已生成中英双语显示元数据（不修改源文件）' : 'Bilingual display metadata generated (source unchanged)'
      }`
    );
  } else if (preview.display_translation_requested) {
    lines.push(
      `${isZh ? '界面说明' : 'UI description'}: ${
        isZh ? '翻译未生成，将显示原始说明' : 'Translation unavailable; the original metadata will be shown'
      }`
    );
  }
  if (preview.kind === 'collection') {
    lines.push(
      `${isZh ? '集合内容' : 'Collection'}: ${preview.collection_count} ${
        isZh ? '个技能' : 'skills'
      }`,
      `${isZh ? '本次安装' : 'To install'}: ${preview.installable_count}`,
      `${isZh ? '更新' : 'Updates'}: ${preview.update_count || 0}`,
      `${isZh ? '冲突' : 'Conflicts'}: ${preview.conflict_count || 0}`,
      `${isZh ? '跳过重复' : 'Duplicates skipped'}: ${preview.duplicate_count}`
    );
    preview.collection_items?.forEach(item => {
      const statuses = {
        duplicate: isZh
          ? `跳过，与 ${item.duplicate_of} 内容相同`
          : `skip, identical to ${item.duplicate_of}`,
        update: isZh
          ? `更新 ${item.active_name}`
          : `update ${item.active_name}`,
        conflict: isZh
          ? `冲突：${item.active_name} 含本地修改`
          : `conflict: ${item.active_name} has local changes`,
        install: isZh
          ? `安装为 ${item.active_name}`
          : `install as ${item.active_name}`
      };
      const status = statuses[item.action] || statuses.install;
      lines.push(`• ${item.source_name}: ${status}`);
      if (item.display_language === currentLanguage && item.display_title) {
        lines.push(`  ${isZh ? '显示为' : 'Displayed as'}: ${item.display_title}`);
      }
      const compatibilityIssues = Object.values(
        item.compatibility?.targets || {}
      ).filter(target => target.status !== 'ready');
      compatibilityIssues.forEach(target => {
        const compatibilityStatus = compatibilityStatusLabels[target.status] || target.status;
        lines.push(`  ${isZh ? '兼容性' : 'Compatibility'} · ${target.label}: ${compatibilityStatus}`);
      });
    });
  } else {
    lines.splice(
      1,
      0,
      `${isZh ? '导入为' : 'Import as'}: ${preview.active_name}`
    );
    if (preview.display_language === currentLanguage && preview.display_title) {
      lines.push(
        `${isZh ? '显示为' : 'Displayed as'}: ${preview.display_title}`,
        `${isZh ? '说明' : 'Description'}: ${preview.display_description}`
      );
    }
  }
  if (preview.kind !== 'collection' && preview.compatibility?.targets) {
    lines.push('', isZh ? '客户端兼容性（本地规则）：' : 'Client compatibility (local rules):');
    appendCompatibility(preview.compatibility);
  }
  if (preview.replace_existing) {
    lines.push(
      `${isZh ? '应用方式' : 'Apply mode'}: ${
        isZh ? '原地更新，原文件会先归档' : 'Update in place after archiving the original'
      }`
    );
  }
  if (preview.changes?.length) {
    lines.push('', isZh ? '自动处理：' : 'Automatic changes:');
    preview.changes.forEach(code => lines.push(`• ${changeLabels[code] || code}`));
  }
  const ordinaryFindings = (preview.findings || []).filter(item => item.severity !== 'high');
  if (ordinaryFindings.length) {
    lines.push('', isZh ? `普通提示（${ordinaryFindings.length}）：` : `Standard findings (${ordinaryFindings.length}):`);
    ordinaryFindings.slice(0, 8).forEach(item => {
      lines.push(`• ${isZh ? item.message_zh : item.message_en}${item.path ? ` [${item.path}]` : ''}`);
    });
    if (ordinaryFindings.length > 8) {
      lines.push(isZh ? `…另有 ${ordinaryFindings.length - 8} 项` : `…and ${ordinaryFindings.length - 8} more`);
    }
  }
  if (preview.has_high_risk) {
    lines.push(
      '',
      isZh
        ? '检测到高风险项；普通导入确认后将单独展示并确认。'
        : 'High-risk findings were detected and will be shown in a separate confirmation.'
    );
  }
  if (preview.duplicate_of) {
    lines.push('', `${isZh ? '检测到完全重复' : 'Exact duplicate detected'}: ${preview.duplicate_of}`);
  }
  if (preview.ai_used) {
    lines.push(
      '',
      isZh
        ? 'AI 已改写入口文档；导入前还需要审阅并确认差异。'
        : 'AI rewrote the entry document; review and accept the diff before importing.'
    );
  }
  return lines.join('\n');
}

function formatAiImportDiff(preview) {
  const isZh = currentLanguage === 'zh';
  const sections = [];
  if (preview.kind === 'collection') {
    preview.collection_items?.forEach(item => {
      if (!item.ai_used) return;
      sections.push(
        `=== ${item.source_name} ===`,
        item.ai_diff || (isZh ? 'AI 未产生文本差异。' : 'AI produced no text difference.'),
        ''
      );
    });
  } else {
    sections.push(
      preview.ai_diff || (isZh ? 'AI 未产生文本差异。' : 'AI produced no text difference.')
    );
  }
  return [
    isZh
      ? '下面仅显示 AI 对暂存副本的改动。原版已经归档；确认后才会写入技能库。'
      : 'These are AI changes to the staged copy only. The upstream original is archived; nothing enters the library until you accept.',
    '',
    ...sections
  ].join('\n');
}

function buildImportReview(preview, title, confirmText) {
  const isZh = currentLanguage === 'zh';
  const findings = preview.findings || [];
  const highRiskCount = findings.filter(item => item.severity === 'high').length;
  const collectionCount = preview.kind === 'collection' ? (preview.collection_count || 0) : 1;
  return {
    title,
    kicker: isZh ? '导入前体检' : 'Pre-import review',
    intro: isZh
      ? `来源：${preview.source_name || '—'}。确认后才会写入全局技能库。`
      : `Source: ${preview.source_name || '—'}. Nothing is written to the global library until you confirm.`,
    metrics: [
      { value: collectionCount, label: isZh ? '扫描 Skill' : 'Skills scanned' },
      { value: preview.installable_count ?? (preview.can_import ? 1 : 0), label: isZh ? '可安装' : 'Installable', tone: 'success' },
      { value: findings.length, label: isZh ? '检查提示' : 'Findings', tone: findings.length ? 'warning' : 'success' },
      { value: highRiskCount + (preview.conflict_count || 0), label: isZh ? '需单独确认' : 'Need confirmation', tone: highRiskCount || preview.conflict_count ? 'danger' : '' }
    ],
    sections: [{
      title: isZh ? '体检与兼容性详情' : 'Validation and compatibility details',
      items: formatImportPreview(preview).split('\n').filter(Boolean)
    }],
    confirmText,
    danger: highRiskCount > 0
  };
}

function buildSyncReview(preview) {
  const isZh = currentLanguage === 'zh';
  const summary = preview.summary || {};
  return {
    title: locales[currentLanguage].syncPreviewTitle,
    kicker: isZh ? '项目同步计划' : 'Project sync plan',
    intro: isZh
      ? '以下计划来自当前磁盘状态。确认后才会写入项目，并保留可撤销记录。'
      : 'This plan reflects the current disk state. Files are written only after confirmation and an undo record is retained.',
    metrics: [
      { value: summary.add || 0, label: isZh ? '新增' : 'Add', tone: 'success' },
      { value: (summary.adopt || 0) + (summary.modify || 0), label: isZh ? '纳管 / 更新' : 'Adopt / update' },
      { value: summary.delete || 0, label: isZh ? '移除' : 'Remove', tone: summary.delete ? 'warning' : '' },
      { value: (preview.scope_conflict_count || 0) + (preview.has_conflicts ? 1 : 0), label: isZh ? '冲突信号' : 'Conflict signals', tone: preview.has_conflicts ? 'danger' : '' }
    ],
    sections: [{
      title: isZh ? '文件与作用域影响' : 'File and scope impact',
      items: formatSyncPreview(preview).split('\n').filter(Boolean)
    }],
    confirmText: locales[currentLanguage].syncApply,
    danger: Boolean(preview.has_conflicts)
  };
}

async function handleImportSkill() {
  const isZh = currentLanguage === 'zh';
  const selection = await showCustomDialog({
    title: isZh ? '导入技能' : 'Import Skill',
    message: isZh
      ? `基础导入始终使用本地规则。当前模式：${aiImportOptimization && hasAiKey ? '本地体检 + AI 优化' : '本地体检'}${aiDisplayTranslation && hasAiKey ? ' + 双语界面说明' : ''}。请选择 Markdown/ZIP 文件、单个技能文件夹，或包含 skills/*/SKILL.md 的技能集合。`
      : `Local validation always runs. Current mode: ${aiImportOptimization && hasAiKey ? 'Local + AI optimization' : 'Local validation'}${aiDisplayTranslation && hasAiKey ? ' + bilingual UI descriptions' : ''}. Select a Markdown/ZIP file, one skill folder, or a collection containing skills/*/SKILL.md.`,
    emoji: '📥',
    confirmText: isZh ? '选择文件' : 'Choose File',
    secondaryText: isZh ? '选择文件夹' : 'Choose Folder',
    secondaryValue: 'folder'
  });
  if (!selection) return;
  const importKind = selection === 'folder' ? 'folder' : 'file';
  let preview;
  try {
    preview = await window.pywebview.api.preview_skill_import_via_dialog(importKind);
  } catch (e) {
    showToast((isZh ? '导入分析失败: ' : 'Import analysis failed: ') + e, 'error');
    return;
  }
  if (!preview) return;
  if (preview.error) {
    showToast((isZh ? '导入分析失败: ' : 'Import analysis failed: ') + preview.error, 'error');
    return;
  }

  const importReview = buildImportReview(
    preview,
    preview.can_import ? (isZh ? '确认导入' : 'Confirm Import') : (isZh ? '无需重复导入' : 'Duplicate Skill'),
    preview.can_import ? (isZh ? '导入' : 'Import') : (isZh ? '关闭' : 'Close')
  );
  const confirmed = await showStructuredReview(importReview);
  if (!confirmed || !preview.can_import) {
    try {
      await window.pywebview.api.discard_skill_import(preview.token);
    } catch (_e) {
      // Staged previews are also cleaned automatically after 24 hours.
    }
    return;
  }

  let acceptedHighRisk = false;
  if (preview.has_high_risk) {
    const highRiskFindings = preview.findings.filter(item => item.severity === 'high');
    acceptedHighRisk = await showStructuredReview({
      title: isZh ? '单独确认高风险项' : 'Confirm High-Risk Findings',
      kicker: isZh ? '安全边界' : 'Security boundary',
      intro: isZh ? '这些项目需要独立确认，不会由普通导入确认自动放行。' : 'These findings require an explicit decision beyond the standard import confirmation.',
      metrics: [{ value: highRiskFindings.length, label: isZh ? '高风险项' : 'High-risk findings', tone: 'danger' }],
      sections: [{
        title: isZh ? '风险详情' : 'Risk details',
        items: highRiskFindings.map(item => `${isZh ? item.message_zh : item.message_en}${item.path ? ` [${item.path}]` : ''}`)
      }],
      confirmText: isZh ? '确认风险并继续' : 'Accept Risk and Continue',
      danger: true
    });
    if (!acceptedHighRisk) {
      await window.pywebview.api.discard_skill_import(preview.token);
      return;
    }
  }

  let acceptedCollectionConflicts = false;
  if ((preview.conflict_count || 0) > 0) {
    const conflicts = preview.collection_items.filter(item => item.action === 'conflict');
    acceptedCollectionConflicts = await showStructuredReview({
      title: isZh ? '确认覆盖集合冲突' : 'Confirm Collection Conflicts',
      kicker: isZh ? '本地修改冲突' : 'Local modification conflicts',
      intro: isZh ? '以下目标含本地修改；继续会先归档旧版本，再覆盖活动副本。' : 'These targets contain local edits. Continuing archives the old versions before replacing the active copies.',
      metrics: [{ value: conflicts.length, label: isZh ? '覆盖冲突' : 'Overwrite conflicts', tone: 'danger' }],
      sections: [{ title: isZh ? '冲突映射' : 'Conflict mapping', items: conflicts.map(item => `${item.source_name} → ${item.active_name}`) }],
      confirmText: isZh ? '覆盖本地修改' : 'Overwrite Local Changes',
      danger: true
    });
    if (!acceptedCollectionConflicts) {
      await window.pywebview.api.discard_skill_import(preview.token);
      return;
    }
  }

  let acceptedAiChanges = false;
  if (preview.ai_used) {
    acceptedAiChanges = await showStructuredReview({
      title: isZh ? '审阅 AI 改写差异' : 'Review AI Changes',
      kicker: isZh ? '暂存副本差异' : 'Staged-copy diff',
      intro: isZh ? 'AI 只改动暂存副本；上游原版已经归档。' : 'AI changed only the staged copy; the upstream original has been archived.',
      metrics: [{ value: preview.kind === 'collection' ? preview.collection_items.filter(item => item.ai_used).length : 1, label: isZh ? 'AI 改写文档' : 'AI-edited documents' }],
      sections: [{ title: isZh ? '文本差异' : 'Text diff', diff: formatAiImportDiff(preview) }],
      confirmText: isZh ? '接受改写并导入' : 'Accept Changes and Import'
    });
    if (!acceptedAiChanges) {
      try {
        await window.pywebview.api.discard_skill_import(preview.token);
      } catch (_e) {
        // Staged previews are also cleaned automatically after 24 hours.
      }
      return;
    }
  }

  try {
    const result = await window.pywebview.api.apply_skill_import(
      preview.token,
      Boolean(acceptedAiChanges),
      Boolean(acceptedHighRisk),
      Boolean(acceptedCollectionConflicts)
    );
    if (result.requires_high_risk_confirmation) {
      throw new Error(
        isZh
          ? '高风险扫描结果尚未获得独立确认。'
          : 'High-risk findings have not been independently accepted.'
      );
    }
    if (result.requires_ai_confirmation) {
      throw new Error(
        isZh
          ? 'AI 改写尚未获得明确确认。'
          : 'AI changes have not been explicitly accepted.'
      );
    }
    if (result.error) throw new Error(result.error);
    if (result.kind === 'collection') {
      const skipped = result.skipped_duplicates?.length || 0;
      showToast(
        isZh
          ? `已导入 ${result.filenames.length} 个技能${skipped ? `，跳过 ${skipped} 个重复项` : ''}`
          : `Imported ${result.filenames.length} skills${skipped ? `; skipped ${skipped} duplicate(s)` : ''}`,
        'success'
      );
    } else {
      showToast(
        isZh
          ? `已通过${result.ai_used ? '本地体检和 AI 优化' : '本地体检'}导入：${result.filename}`
          : `Imported with ${result.ai_used ? 'local validation and AI optimization' : 'local validation'}: ${result.filename}`,
        'success'
      );
    }
    await fetchSkills();
    if (currentProjectPath) {
      await fetchProjects();
      refreshCurrentProject();
    }
    if (result.kind !== 'collection' || result.filenames?.length === 1) {
      openEditorModal(result.filename);
    }
  } catch (e) {
    showToast((isZh ? '导入失败: ' : 'Import failed: ') + e, 'error');
  }
}

async function checkForUnregisteredSkills() {
  const isZh = currentLanguage === 'zh';
  let scan;
  try {
    scan = await window.pywebview.api.scan_unregistered_skills();
  } catch (e) {
    showToast((isZh ? '检查新增技能失败: ' : 'Failed to scan new skills: ') + e, 'error');
    return;
  }
  if (!scan || scan.error || !scan.skills?.length) return;

  const names = scan.skills.slice(0, 8).map(item => {
    const state = item.change_type === 'modified'
      ? (isZh ? '（内容已变化）' : ' (content changed)')
      : '';
    return `• ${item.filename}${state}`;
  });
  if (scan.skills.length > 8) {
    names.push(isZh ? `…另有 ${scan.skills.length - 8} 个` : `…and ${scan.skills.length - 8} more`);
  }
  const choice = await showCustomDialog({
    title: isZh ? `发现 ${scan.skills.length} 个待体检技能` : `${scan.skills.length} skills need validation`,
    message: [
      isZh
        ? '这些技能是新复制的，或登记后内容发生了变化：'
        : 'These skills are newly copied or changed since they were registered:',
      '',
      ...names,
      '',
      isZh
        ? '可以逐个体检并原地优化，也可以保留原样并登记。'
        : 'Validate and optimize them in place, or keep them unchanged and register them.'
    ].join('\n'),
    emoji: '🆕',
    confirmText: isZh ? '逐个体检' : 'Validate',
    secondaryText: isZh ? '全部保留原样' : 'Keep All',
    secondaryValue: 'keep-all'
  });
  if (!choice) return;
  if (choice === 'keep-all') {
    for (const item of scan.skills) {
      await window.pywebview.api.acknowledge_unregistered_skill(item.filename);
    }
    showToast(isZh ? '新增技能已登记并保留原样' : 'New skills registered unchanged', 'success');
    return;
  }

  for (const item of scan.skills) {
    let preview;
    try {
      preview = await window.pywebview.api.preview_unregistered_skill(item.filename);
    } catch (e) {
      showToast(`${item.filename}: ${e}`, 'error');
      continue;
    }
    if (!preview || preview.error) {
      showToast(`${item.filename}: ${preview?.error || 'Preview failed'}`, 'error');
      continue;
    }
    const apply = await showCustomDialog({
      title: isZh ? `体检：${item.filename}` : `Validate: ${item.filename}`,
      message: formatImportPreview(preview),
      emoji: preview.findings?.some(finding => finding.severity === 'high') ? '⚠️' : '📋',
      confirmText: isZh ? '应用优化' : 'Apply',
      secondaryText: isZh ? '保留原样' : 'Keep Original',
      secondaryValue: 'keep'
    });
    if (apply === true) {
      let acceptedHighRisk = false;
      if (preview.has_high_risk) {
        acceptedHighRisk = await showCustomDialog({
          title: isZh ? '单独确认高风险项' : 'Confirm High-Risk Findings',
          message: preview.findings
            .filter(finding => finding.severity === 'high')
            .map(finding => `• ${isZh ? finding.message_zh : finding.message_en}`)
            .join('\n'),
          emoji: '⚠️',
          confirmText: isZh ? '确认风险并继续' : 'Accept Risk and Continue'
        });
        if (!acceptedHighRisk) {
          await window.pywebview.api.discard_skill_import(preview.token);
          continue;
        }
      }
      let acceptedAiChanges = false;
      if (preview.ai_used) {
        acceptedAiChanges = await showCustomDialog({
          title: isZh ? '审阅 AI 改写差异' : 'Review AI Changes',
          message: formatAiImportDiff(preview),
          emoji: '✨',
          confirmText: isZh ? '接受改写并应用' : 'Accept Changes and Apply'
        });
        if (!acceptedAiChanges) {
          await window.pywebview.api.discard_skill_import(preview.token);
          continue;
        }
      }
      const result = await window.pywebview.api.apply_skill_import(
        preview.token,
        Boolean(acceptedAiChanges),
        Boolean(acceptedHighRisk)
      );
      if (result.error) {
        showToast(`${item.filename}: ${result.error}`, 'error');
      } else {
        showToast(
          isZh
            ? `已原地处理：${result.filename}`
            : `Processed in place: ${result.filename}`,
          'success'
        );
      }
    } else {
      await window.pywebview.api.discard_skill_import(preview.token);
      if (apply === 'keep') {
        await window.pywebview.api.acknowledge_unregistered_skill(item.filename);
      } else {
        break;
      }
    }
  }
  await fetchSkills();
  if (currentProjectPath) {
    await fetchProjects();
    refreshCurrentProject();
  }
}

function formatSyncPreview(preview) {
  const summary = preview.summary;
  const isZh = currentLanguage === 'zh';
  const countLine = isZh
    ? `新增 ${summary.add}  纳管 ${summary.adopt || 0}  修改 ${summary.modify}  删除 ${summary.delete}  保留 ${summary.preserve}`
    : `Add ${summary.add}  Adopt ${summary.adopt || 0}  Modify ${summary.modify}  Delete ${summary.delete}  Preserve ${summary.preserve}`;
  const lines = [locales[currentLanguage].syncPreviewIntro, countLine];
  if (preview.has_conflicts) {
    lines.push('', locales[currentLanguage].syncPreviewConflict);
  }
  if ((preview.scope_conflicts || []).length > 0) {
    lines.push(
      '',
      isZh
        ? '作用域重叠：以下 Skill 已在用户全局范围启用，项目同步后可能被同一 Agent 重复发现；SkillHub 不会自动删除任一作用域。'
        : 'Scope overlap: these Skills are already enabled in user scope and may be discovered twice after project sync. SkillHub does not remove either scope automatically.'
    );
    preview.scope_conflicts.forEach(item => {
      const targets = (item.global_targets || []).map(target => target.label).join(', ');
      lines.push(`!  ${item.filename}${targets ? ` → ${targets}` : ''}`);
    });
  }

  const labels = isZh
    ? { add: '新增', adopt: '纳管', modify: '修改', delete: '删除', preserve: '保留' }
    : { add: 'ADD', adopt: 'ADOPT', modify: 'MOD', delete: 'DEL', preserve: 'KEEP' };
  const reasonMessages = isZh
    ? {
        adopt_existing_copy: '项目中已有内容一致的副本，将只补充 SkillHub 所有权记录，不重写文件。',
        unmanaged_matching_copy: '项目中存在未登记但内容一致的旧副本；确认后将备份并移除。',
        unmanaged_modified_copy: '项目中存在未登记且内容不同的副本；确认后将备份并移除。',
        unmanaged_source_collision: '多个未启用 Skill 指向同一路径；需要明确确认后移除。',
        managed_modified_copy_preserved: '该副本已在项目中修改；本次同步会保留文件，并停止由 SkillHub 管理。'
      }
    : {
        adopt_existing_copy: 'An identical project copy already exists; SkillHub will record ownership without rewriting it.',
        unmanaged_matching_copy: 'An identical unregistered project copy exists; it will be backed up and removed after confirmation.',
        unmanaged_modified_copy: 'A modified unregistered project copy exists; it will be backed up and removed after confirmation.',
        unmanaged_source_collision: 'Multiple disabled Skills target this path; explicit confirmation is required before removal.',
        managed_modified_copy_preserved: 'This project copy was modified; sync will retain it and stop managing it.'
      };
  const visibleChanges = preview.changes.filter(item => item.action !== 'unchanged');
  visibleChanges.slice(0, 14).forEach(item => {
    const conflict = item.conflict ? ' !' : '';
    lines.push(`${labels[item.action] || item.action}${conflict}  ${item.path}`);
    if (reasonMessages[item.reason_code]) {
      lines.push(`   ${reasonMessages[item.reason_code]}`);
    }
  });
  if (visibleChanges.length > 14) {
    const remaining = visibleChanges.length - 14;
    lines.push(isZh ? `…另有 ${remaining} 项` : `...and ${remaining} more`);
  }
  return lines.join('\n');
}

async function handleUndoSync() {
  if (!currentProjectPath || undoSyncBtn.disabled) return;
  const confirmed = await showCustomDialog({
    title: locales[currentLanguage].undoSyncTitle,
    message: locales[currentLanguage].undoSyncMessage,
    emoji: '↶',
    confirmText: locales[currentLanguage].undoSyncConfirm
  });
  if (!confirmed) return;

  undoSyncBtn.disabled = true;
  syncBtn.disabled = true;
  try {
    const result = await window.pywebview.api.undo_last_sync(currentProjectPath);
    if (result.error) throw new Error(result.error);
    if (result.skipped_count > 0) {
      showToast(locales[currentLanguage].toastUndoPartial + result.skipped.join(', '), 'warning');
    } else {
      showToast(locales[currentLanguage].toastUndoSuccess, 'success');
    }
    await fetchProjects();
    refreshCurrentProject();
  } catch (e) {
    showToast(locales[currentLanguage].toastUndoFail + e, 'error');
  } finally {
    if (currentProjectPath) {
      syncBtn.disabled = false;
      const project = projects.find(item => item.path === currentProjectPath);
      undoSyncBtn.disabled = !project?.can_undo_sync;
    }
    lucide.createIcons();
  }
}

function handleSearch() {
  clearTimeout(searchRenderTimer);
  searchRenderTimer = setTimeout(renderSkillsGrid, 120);
}

// ------------------------------------------
// Editor Modal
// ------------------------------------------

function isDefaultSkillCategory(category) {
  return ['未分类', 'Uncategorized'].includes(String(category || '').trim());
}

function getSkillCategorySelectValue(category) {
  const normalized = String(category || '').trim();
  return isDefaultSkillCategory(normalized) ? '' : normalized;
}

function populateSkillCategoryOptions(selectedCategory = '') {
  const normalizedSelection = getSkillCategorySelectValue(selectedCategory);
  const categories = Array.from(new Set([
    ...skills.map(skill => String(skill.category || '').trim()),
    ...pendingEditorCategories,
    normalizedSelection,
  ].filter(category => category && !isDefaultSkillCategory(category))))
    .sort((left, right) => left.localeCompare(right, currentLanguage));
  skillCategorySelect.innerHTML = [
    `<option value="">${escapeHtml(locales[currentLanguage].editCategoryUncategorized)}</option>`,
    ...categories.map(category => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`),
  ].join('');
  skillCategorySelect.value = normalizedSelection;
  updateSkillCategoryDeleteButton();
}

function updateSkillCategoryDeleteButton() {
  const category = getSkillCategorySelectValue(skillCategorySelect.value);
  skillCategoryDelete.disabled = skillCategorySelect.disabled || !category;
  skillCategoryDelete.title = category
    ? `${locales[currentLanguage].editCategoryDelete}: ${category}`
    : locales[currentLanguage].editCategoryDelete;
}

function syncActiveEditorBuffer() {
  if (activeEditorSource === 'openai') {
    if (openaiEditorMode === 'yaml') {
      editorOpenaiYamlContent = markdownTextarea.value;
      editorOpenaiYamlDirty = editorOpenaiYamlContent !== editorOpenaiYamlInitialContent;
    } else {
      editorOpenaiForm = collectOpenaiFormData();
    }
  } else {
    editorSkillContent = markdownTextarea.value;
  }
}

function getEditorSnapshot() {
  syncActiveEditorBuffer();
  return JSON.stringify({
    skillContent: editorSkillContent,
    category: getSkillCategorySelectValue(skillCategorySelect.value),
    openaiYaml: editorOpenaiYamlContent,
    openaiForm: editorOpenaiForm,
    createOpenaiYaml: editorOpenaiYamlCreateRequested
  });
}

function updateEditorDirtyState() {
  const dirty = Boolean(
    !isViewingSkill
    && editorInitialSnapshot !== null
    && getEditorSnapshot() !== editorInitialSnapshot
  );
  if (editorDirtyIndicator) {
    editorDirtyIndicator.hidden = !dirty;
    editorDirtyIndicator.textContent = currentLanguage === 'zh' ? '未保存' : 'Unsaved';
  }
  return dirty;
}

function getEditorContentWithCategory() {
  const skillSource = activeEditorSource === 'skill'
    ? markdownTextarea.value
    : editorSkillContent;
  const selectedCategory = skillCategorySelect.value.trim();
  if (selectedCategory === getSkillCategorySelectValue(loadedEditorCategory)) {
    return skillSource;
  }
  return setMarkdownFrontmatterCategory(skillSource, selectedCategory);
}

function refreshEditorSourceUi() {
  const t = locales[currentLanguage];
  const isOpenai = activeEditorSource === 'openai';
  const isOpenaiForm = isOpenai && openaiEditorMode === 'form';
  editorSourceSkill.classList.toggle('active', !isOpenai);
  editorSourceSkill.setAttribute('aria-selected', String(!isOpenai));
  editorSourceOpenai.classList.toggle('active', isOpenai);
  editorSourceOpenai.setAttribute('aria-selected', String(isOpenai));
  editorSourceOpenai.disabled = !editorOpenaiYamlSupported;
  editorOpenaiState.textContent = editorOpenaiYamlSupported
    ? (editorOpenaiYamlExists ? t.editOpenaiExisting : t.editOpenaiNew)
    : t.editOpenaiUnsupported;
  editorSourceHint.textContent = isOpenai
    ? t.editSourceOpenaiHint
    : t.editSourceSkillHint;
  skillMetadataBar.hidden = isViewingSkill || isOpenai;
  editorOpenaiHint.hidden = isViewingSkill || !isOpenai;
  editorOpenaiModeForm.classList.toggle('active', openaiEditorMode === 'form');
  editorOpenaiModeYaml.classList.toggle('active', openaiEditorMode === 'yaml');
  openaiFormEditor.hidden = !isOpenaiForm;
  markdownTextarea.hidden = isOpenaiForm;
  modalTabPreview.disabled = isOpenai;
  modalTabPreview.title = isOpenai
    ? (currentLanguage === 'zh' ? 'OpenAI 配置不提供 Markdown 预览' : 'OpenAI configuration does not have a Markdown preview')
    : '';
}

function switchEditorSource(source) {
  if (isViewingSkill || !['skill', 'openai'].includes(source)) return;
  if (source === 'openai' && !editorOpenaiYamlSupported) return;
  if (source === activeEditorSource) return;
  syncActiveEditorBuffer();
  activeEditorSource = source;
  if (source === 'openai') {
    if (!editorOpenaiYamlExists) editorOpenaiYamlCreateRequested = true;
    if (modalBody.classList.contains('tab-preview')) switchModalTab('edit');
    if (openaiEditorMode === 'form') {
      populateOpenaiForm(editorOpenaiForm);
    } else {
      markdownTextarea.value = editorOpenaiYamlContent;
    }
    markdownTextarea.placeholder = 'interface:\n  display_name: "..."\npolicy:\n  allow_implicit_invocation: true';
  } else {
    markdownTextarea.value = editorSkillContent;
    markdownTextarea.placeholder = '# 输入技能内容…';
  }
  refreshEditorSourceUi();
  updateEditorDirtyState();
  (source === 'openai' && openaiEditorMode === 'form'
    ? openaiDisplayName
    : markdownTextarea).focus();
}

markdownTextarea.addEventListener('input', syncActiveEditorBuffer);

function collectOpenaiFormData() {
  const implicit = document.querySelector('input[name="openai-implicit"]:checked');
  const tools = Array.from(openaiToolsList.querySelectorAll('.openai-tool-card')).map(card => {
    const sourceIndex = Number.parseInt(card.dataset.sourceIndex || '', 10);
    const tool = {
      type: card.querySelector('[data-field="type"]')?.value || '',
      value: card.querySelector('[data-field="value"]')?.value || '',
      description: card.querySelector('[data-field="description"]')?.value || '',
      transport: card.querySelector('[data-field="transport"]')?.value || '',
      url: card.querySelector('[data-field="url"]')?.value || '',
    };
    if (Number.isInteger(sourceIndex)) tool._source_index = sourceIndex;
    return tool;
  });
  return {
    display_name: openaiDisplayName.value,
    short_description: openaiShortDescription.value,
    default_prompt: openaiDefaultPrompt.value,
    allow_implicit_invocation: implicit?.value !== 'false',
    tools,
  };
}

function populateOpenaiForm(form = {}) {
  editorOpenaiForm = {
    display_name: String(form.display_name || ''),
    short_description: String(form.short_description || ''),
    default_prompt: String(form.default_prompt || ''),
    allow_implicit_invocation: form.allow_implicit_invocation !== false,
    tools: Array.isArray(form.tools) ? form.tools.map(tool => ({ ...tool })) : [],
  };
  openaiDisplayName.value = editorOpenaiForm.display_name;
  openaiShortDescription.value = editorOpenaiForm.short_description;
  openaiDefaultPrompt.value = editorOpenaiForm.default_prompt;
  const implicitValue = editorOpenaiForm.allow_implicit_invocation ? 'true' : 'false';
  const implicitRadio = document.querySelector(`input[name="openai-implicit"][value="${implicitValue}"]`);
  if (implicitRadio) implicitRadio.checked = true;
  renderOpenaiToolDependencies();
}

function selectOptions(options, selectedValue) {
  const known = options.some(option => option.value === selectedValue);
  const values = known || !selectedValue
    ? options
    : [...options, { value: selectedValue, label: selectedValue }];
  return values.map(option => (
    `<option value="${escapeHtml(option.value)}"${option.value === selectedValue ? ' selected' : ''}>${escapeHtml(option.label)}</option>`
  )).join('');
}

function renderOpenaiToolDependencies() {
  if (!openaiToolsList || !openaiToolsEmpty) return;
  const t = locales[currentLanguage];
  const tools = Array.isArray(editorOpenaiForm.tools) ? editorOpenaiForm.tools : [];
  openaiToolsList.innerHTML = tools.map((tool, index) => {
    const sourceIndex = Number.isInteger(tool._source_index) ? String(tool._source_index) : '';
    const typeOptions = selectOptions([{ value: 'mcp', label: 'MCP' }], String(tool.type || 'mcp'));
    const transportOptions = selectOptions([
      { value: '', label: currentLanguage === 'zh' ? '未指定' : 'Not specified' },
      { value: 'streamable_http', label: 'streamable_http' },
    ], String(tool.transport || ''));
    return `
      <div class="openai-tool-card" data-tool-index="${index}" data-source-index="${escapeHtml(sourceIndex)}">
        <div class="openai-tool-card-header">
          <strong>${escapeHtml(t.openaiToolTitle)} ${index + 1}</strong>
          <button type="button" class="btn btn-secondary openai-tool-remove" title="${escapeHtml(t.openaiToolRemove)}" onclick="removeOpenaiToolDependency(${index})">
            <i data-lucide="trash-2" aria-hidden="true"></i>
          </button>
        </div>
        <div class="openai-tool-grid">
          <div class="openai-tool-field">
            <label>${escapeHtml(t.openaiToolType)}</label>
            <select class="openai-tool-select" data-field="type">${typeOptions}</select>
          </div>
          <div class="openai-tool-field">
            <label>${escapeHtml(t.openaiToolValue)}</label>
            <input class="openai-tool-input" data-field="value" value="${escapeHtml(tool.value || '')}" placeholder="openaiDeveloperDocs">
          </div>
          <div class="openai-tool-field">
            <label>${escapeHtml(t.openaiToolDescription)}</label>
            <input class="openai-tool-input" data-field="description" value="${escapeHtml(tool.description || '')}">
          </div>
          <div class="openai-tool-field">
            <label>${escapeHtml(t.openaiToolTransport)}</label>
            <select class="openai-tool-select" data-field="transport">${transportOptions}</select>
          </div>
          <div class="openai-tool-field wide">
            <label>${escapeHtml(t.openaiToolUrl)}</label>
            <input class="openai-tool-input" data-field="url" value="${escapeHtml(tool.url || '')}" placeholder="https://example.com/mcp">
          </div>
        </div>
      </div>`;
  }).join('');
  openaiToolsEmpty.hidden = tools.length > 0;
  lucide.createIcons();
}

function markOpenaiFormDirty() {
  if (activeEditorSource !== 'openai' || openaiEditorMode !== 'form') return;
  editorOpenaiForm = collectOpenaiFormData();
  editorOpenaiFormDirty = true;
}

openaiFormEditor.addEventListener('input', markOpenaiFormDirty);
openaiFormEditor.addEventListener('change', markOpenaiFormDirty);

function addOpenaiToolDependency() {
  editorOpenaiForm = collectOpenaiFormData();
  editorOpenaiForm.tools.push({
    type: 'mcp',
    value: '',
    description: '',
    transport: '',
    url: '',
  });
  editorOpenaiFormDirty = true;
  renderOpenaiToolDependencies();
  updateEditorDirtyState();
  openaiToolsList.querySelector('.openai-tool-card:last-child [data-field="value"]')?.focus();
}

function removeOpenaiToolDependency(index) {
  editorOpenaiForm = collectOpenaiFormData();
  editorOpenaiForm.tools.splice(index, 1);
  editorOpenaiFormDirty = true;
  renderOpenaiToolDependencies();
  updateEditorDirtyState();
}

async function renderOpenaiFormToYaml() {
  editorOpenaiForm = collectOpenaiFormData();
  const result = await window.pywebview.api.render_openai_yaml_form(
    editorOpenaiYamlContent,
    editorOpenaiForm,
  );
  if (result.error) throw new Error(result.error);
  editorOpenaiYamlContent = result.content;
  editorOpenaiYamlDirty = editorOpenaiYamlContent !== editorOpenaiYamlInitialContent;
  editorOpenaiFormDirty = false;
  populateOpenaiForm(result.form || editorOpenaiForm);
}

async function switchOpenaiEditorMode(mode) {
  if (activeEditorSource !== 'openai' || !['form', 'yaml'].includes(mode)) return;
  if (mode === openaiEditorMode) return;
  try {
    if (mode === 'yaml') {
      if (editorOpenaiFormDirty) await renderOpenaiFormToYaml();
      markdownTextarea.value = editorOpenaiYamlContent;
    } else {
      syncActiveEditorBuffer();
      const result = await window.pywebview.api.parse_openai_yaml_form(editorOpenaiYamlContent);
      if (result.error) throw new Error(result.error);
      populateOpenaiForm(result.form || {});
      editorOpenaiFormDirty = false;
    }
    openaiEditorMode = mode;
    refreshEditorSourceUi();
    (mode === 'form' ? openaiDisplayName : markdownTextarea).focus();
  } catch (error) {
    showToast(
      (currentLanguage === 'zh' ? '无法切换编辑模式: ' : 'Could not switch editor mode: ') + (error.message || error),
      'error',
    );
  }
}

async function handleAddSkillCategory() {
  const t = locales[currentLanguage];
  const requestedCategory = await showCustomDialog({
    title: t.editCategoryAddTitle,
    message: t.editCategoryAddMessage,
    emoji: '🏷️',
    isPrompt: true,
    placeholder: t.editCategoryAddPlaceholder,
    confirmText: t.editCategoryAdd,
  });
  const normalized = String(requestedCategory || '').trim();
  if (!normalized) return;
  const knownCategories = [
    ...skills.map(skill => String(skill.category || '').trim()),
    ...pendingEditorCategories,
  ];
  const existing = knownCategories.find(category => (
    category.localeCompare(normalized, currentLanguage, { sensitivity: 'base' }) === 0
  ));
  const selectedCategory = getSkillCategorySelectValue(existing || normalized);
  if (selectedCategory) pendingEditorCategories.add(selectedCategory);
  populateSkillCategoryOptions(selectedCategory);
  skillCategorySelect.focus();
}

async function handleDeleteSkillCategory() {
  const t = locales[currentLanguage];
  const category = getSkillCategorySelectValue(skillCategorySelect.value);
  if (!category) return;

  try {
    const preview = await window.pywebview.api.preview_delete_skill_category(category);
    if (preview?.error) throw new Error(preview.error);
    if (!preview?.affected_count) {
      if (pendingEditorCategories.has(category)) {
        pendingEditorCategories.delete(category);
        populateSkillCategoryOptions('');
        showToast(t.editCategoryDeletePending, 'success');
        return;
      }
      showToast(t.editCategoryDeleteEmpty, 'warning');
      return;
    }

    const confirmed = await showCustomDialog({
      title: t.editCategoryDeleteTitle,
      message: currentLanguage === 'zh'
        ? `删除“${category}”后，${preview.affected_count} 个全局 Skill 将归入“未分类”。这会移除这些 Skill 文件 Frontmatter 中的 category 字段。`
        : `Deleting “${category}” will move ${preview.affected_count} global Skill(s) to “Uncategorized” by removing the category field from their Frontmatter.`,
      emoji: '🗑️',
      confirmText: t.editCategoryDelete,
    });
    if (!confirmed) return;

    skillCategoryDelete.disabled = true;
    const result = await window.pywebview.api.delete_skill_category(category);
    if (result?.error) throw new Error(result.error);
    pendingEditorCategories.delete(category);
    await fetchSkills();
    populateSkillCategoryOptions('');
    if (currentProjectPath) {
      await fetchProjects();
      refreshCurrentProject();
    }
    showToast(`${t.editCategoryDeleteSuccess} (${result.affected_count})`, 'success');
  } catch (e) {
    showToast(
      (currentLanguage === 'zh' ? '删除类别失败: ' : 'Failed to delete category: ') + (e.message || e),
      'error'
    );
  } finally {
    updateSkillCategoryDeleteButton();
    lucide.createIcons();
  }
}

skillCategorySelect.addEventListener('change', updateSkillCategoryDeleteButton);
editorModal.addEventListener('input', updateEditorDirtyState);
editorModal.addEventListener('change', updateEditorDirtyState);

function resetSkillModalForEditing() {
  isViewingSkill = false;
  markdownTextarea.readOnly = false;
  editorSourceBar.hidden = false;
  editorSourceBar.classList.remove('viewer-workbench');
  editorSourceSkill.parentElement.hidden = false;
  editorSourceHint.hidden = false;
  skillCategorySelect.disabled = false;
  updateSkillCategoryDeleteButton();
  modalSaveBtn.style.display = '';
  modalTabEdit.textContent = locales[currentLanguage].editModalTabSource;
  modalTabPreview.textContent = locales[currentLanguage].editModalTabPreview;
  modalCloseFooter.textContent = locales[currentLanguage].editModalCancel;
  refreshEditorSourceUi();
}

function resetSkillModalForViewing() {
  isViewingSkill = true;
  editingFilename = null;
  markdownTextarea.readOnly = true;
  editorSourceBar.hidden = false;
  editorSourceBar.classList.add('viewer-workbench');
  editorSourceSkill.parentElement.hidden = true;
  editorSourceHint.hidden = true;
  skillMetadataBar.hidden = true;
  editorOpenaiHint.hidden = true;
  skillCategorySelect.disabled = true;
  updateSkillCategoryDeleteButton();
  modalSaveBtn.style.display = 'none';
  modalTabEdit.textContent = locales[currentLanguage].viewModalTabSource;
  modalTabPreview.textContent = locales[currentLanguage].viewModalTabPreview;
  modalCloseFooter.textContent = locales[currentLanguage].viewModalClose;
}

async function openEditorModal(filename) {
  editorInitialSnapshot = null;
  if (editorDirtyIndicator) editorDirtyIndicator.hidden = true;
  activeEditorSource = 'skill';
  editorSkillContent = '';
  editorOpenaiYamlContent = '';
  editorOpenaiYamlInitialContent = '';
  editorOpenaiYamlExists = false;
  editorOpenaiYamlSupported = false;
  editorOpenaiYamlDirty = false;
  editorOpenaiYamlCreateRequested = false;
  openaiEditorMode = 'form';
  editorOpenaiForm = {};
  editorOpenaiFormDirty = false;
  editorOpenaiFormError = '';
  resetSkillModalForEditing();
  editingFilename = filename;
  modalBody.className = 'modal-body tab-edit';
  modalTabEdit.classList.add('active');
  modalTabPreview.classList.remove('active');
  const skill = skills.find(s => s.filename === filename);
  pendingEditorCategories = new Set();
  loadedEditorCategory = '';
  populateSkillCategoryOptions();
  skillCategorySelect.disabled = true;
  modalEmoji.textContent = skill ? skill.emoji : '📄';
  modalTitle.textContent = (currentLanguage === 'zh' ? `编辑技能: ` : 'Edit Skill: ') + (skill ? skill.title : filename);
  markdownTextarea.value = currentLanguage === 'zh' ? '加载中…' : 'Loading...';
  markdownTextarea.setAttribute('disabled', 'true');
  activateModal(editorModal, markdownTextarea);
  try {
    const data = await window.pywebview.api.get_skill_editor_data(filename);
    if (data.error) throw new Error(data.error);
    editorSkillContent = data.skill_content;
    editorOpenaiYamlContent = data.openai_yaml_content || '';
    editorOpenaiYamlInitialContent = editorOpenaiYamlContent;
    editorOpenaiYamlExists = data.openai_yaml_exists === true;
    editorOpenaiYamlSupported = data.openai_yaml_supported === true;
    editorOpenaiForm = data.openai_form || {};
    editorOpenaiFormError = data.openai_form_error || '';
    openaiEditorMode = editorOpenaiFormError ? 'yaml' : 'form';
    populateOpenaiForm(editorOpenaiForm);
    markdownTextarea.value = editorSkillContent;
    loadedEditorCategory = (
      getMarkdownFrontmatterCategory(editorSkillContent)
      || String(skill?.category || '').trim()
    );
    populateSkillCategoryOptions(loadedEditorCategory);
    refreshEditorSourceUi();
    editorInitialSnapshot = getEditorSnapshot();
    updateEditorDirtyState();
  } catch (e) {
    showToast((currentLanguage === 'zh' ? '加载失败: ' : 'Failed to load: ') + e, 'error');
    await closeEditorModal(true);
  } finally {
    markdownTextarea.removeAttribute('disabled');
    skillCategorySelect.disabled = false;
    if (editorModal.classList.contains('active')) markdownTextarea.focus();
  }
  lucide.createIcons();
}

async function openSkillViewer(filename) {
  const skill = displaySkillsByFilename.get(filename) || skills.find(s => s.filename === filename);
  if (!skill || !skillDrawer) return;
  activeDrawerFilename = filename;
  drawerReturnFocus = document.activeElement;
  const smart = getSmartEmojiAndTags(skill);
  const category = getLocalizedCategory(getCanonicalCategory(skill));
  const displayTitle = skill.display_title || skill.title || filename;
  skillDetailEmoji.textContent = smart.emoji;
  skillDetailTitle.textContent = displayTitle;
  skillDetailKind.textContent = skill.project_only
    ? (currentLanguage === 'zh' ? '项目 Skill · 只读' : 'Project Skill · Read-only')
    : (currentLanguage === 'zh' ? 'Skill 文档' : 'Skill document');
  skillDetailMeta.innerHTML = `
    <span><i data-lucide="folder"></i>${escapeHtml(skill.display_filename || filename)}</span>
    <span><i data-lucide="tag"></i>${escapeHtml(category)}</span>
    ${(smart.tags || []).slice(0, 3).map(tag => `<span class="detail-tag">${escapeHtml(tagTranslations[currentLanguage]?.[tag] || tag)}</span>`).join('')}`;
  skillDetailContent.innerHTML = `<div class="drawer-loading"><span class="loading-spinner"></span>${currentLanguage === 'zh' ? '加载文档…' : 'Loading document…'}</div>`;
  skillDrawer.removeAttribute('inert');
  skillDrawer.inert = false;
  skillDrawer.classList.add('active');
  skillDrawerBackdrop?.classList.add('active');
  skillDrawer.setAttribute('aria-hidden', 'false');
  document.body.classList.add('drawer-open');
  if (appContainer) {
    appContainer.setAttribute('inert', '');
    appContainer.inert = true;
  }
  setTimeout(() => skillDetailClose?.focus(), 0);
  skillDetailEdit.style.display = skill.project_only ? 'none' : '';
  skillDetailDelete.style.display = skill.project_only ? 'none' : '';
  const showCodexGlobalAction = (
    !currentProjectPath
    && !skill.project_only
    && skill.codex_global_compatible
  );
  skillDetailCodexGlobal.style.display = showCodexGlobalAction ? '' : 'none';
  skillDetailCodexGlobal.disabled = false;
  const detailGlobalNeedsUpdate = skill.codex_global_status === 'outdated';
  skillDetailCodexGlobal.innerHTML = detailGlobalNeedsUpdate
    ? `<i data-lucide="refresh-cw" aria-hidden="true"></i>${currentLanguage === 'zh' ? '更新全局目标' : 'Update global targets'}`
    : skill.codex_global_enabled
      ? `<i data-lucide="globe-2" aria-hidden="true"></i>${currentLanguage === 'zh' ? '管理全局目标' : 'Manage global targets'}`
      : `<i data-lucide="globe-2" aria-hidden="true"></i>${currentLanguage === 'zh' ? '发布到全局目标' : 'Publish to global targets'}`;
  skillDetailCodexGlobal.onclick = showCodexGlobalAction
    ? () => {
        closeSkillDrawer(false);
        openGlobalTargetModal(skill);
      }
    : null;
  skillDetailEdit.onclick = skill.project_only ? null : () => {
    closeSkillDrawer(false);
    openEditorModal(filename);
  };
  skillDetailDelete.onclick = skill.project_only ? null : () => {
    closeSkillDrawer(false);
    handleDeleteSkill(filename);
  };
  try {
    const data = skill.project_only
      ? await window.pywebview.api.get_project_skill_content(
          currentProjectPath,
          skill.project_relative_path
        )
      : await window.pywebview.api.get_skill_content(filename);
    if (data.error) throw new Error(data.error);
    if (activeDrawerFilename !== filename) return;
    skillDetailContent.innerHTML = renderMarkdown(data.content);
  } catch (e) {
    showToast((currentLanguage === 'zh' ? '加载失败: ' : 'Failed to load: ') + e, 'error');
    closeSkillDrawer();
  }
  lucide.createIcons();
}

function closeSkillDrawer(restoreFocus = true) {
  if (!skillDrawer) return;
  skillDrawer.classList.remove('active');
  skillDrawerBackdrop?.classList.remove('active');
  skillDrawer.setAttribute('aria-hidden', 'true');
  skillDrawer.setAttribute('inert', '');
  skillDrawer.inert = true;
  if (appContainer) {
    appContainer.removeAttribute('inert');
    appContainer.inert = false;
  }
  document.body.classList.remove('drawer-open');
  activeDrawerFilename = null;
  if (restoreFocus && drawerReturnFocus && document.contains(drawerReturnFocus)) {
    drawerReturnFocus.focus();
  }
  drawerReturnFocus = null;
}

async function closeEditorModal(force = false) {
  if (editorClosePending) return;
  if (!force && updateEditorDirtyState()) {
    editorClosePending = true;
    const discard = await showCustomDialog({
      title: currentLanguage === 'zh' ? '放弃未保存修改？' : 'Discard unsaved changes?',
      message: currentLanguage === 'zh'
        ? 'SKILL.md、分类或使用配置中的修改尚未保存。关闭后将无法恢复。'
        : 'Changes to SKILL.md, its category, or usage configuration have not been saved and cannot be recovered after closing.',
      emoji: '⚠️',
      confirmText: currentLanguage === 'zh' ? '放弃修改' : 'Discard changes'
    });
    editorClosePending = false;
    if (!discard) return;
  }
  deactivateModal(editorModal);
  editingFilename = null;
  isViewingSkill = false;
  loadedEditorCategory = '';
  pendingEditorCategories = new Set();
  activeEditorSource = 'skill';
  editorSkillContent = '';
  editorOpenaiYamlContent = '';
  editorOpenaiYamlInitialContent = '';
  editorOpenaiYamlExists = false;
  editorOpenaiYamlSupported = false;
  editorOpenaiYamlDirty = false;
  editorOpenaiYamlCreateRequested = false;
  openaiEditorMode = 'form';
  editorOpenaiForm = {};
  editorOpenaiFormDirty = false;
  editorOpenaiFormError = '';
  editorInitialSnapshot = null;
  if (editorDirtyIndicator) editorDirtyIndicator.hidden = true;
  populateSkillCategoryOptions();
  markdownTextarea.readOnly = false;
  markdownTextarea.hidden = false;
  openaiFormEditor.hidden = true;
  markdownTextarea.placeholder = '# 输入技能内容…';
  modalSaveBtn.style.display = '';
}

function switchModalTab(tab) {
  if (tab === 'edit') {
    modalTabEdit.classList.add('active');
    modalTabPreview.classList.remove('active');
    modalBody.className = 'modal-body tab-edit';
  } else {
    if (activeEditorSource === 'openai') return;
    modalTabEdit.classList.remove('active');
    modalTabPreview.classList.add('active');
    modalBody.className = 'modal-body tab-preview';
    markdownPreview.innerHTML = renderMarkdown(getEditorContentWithCategory());
  }
}

async function handleSaveSkill() {
  if (isViewingSkill) return;
  if (!editingFilename) return;
  try {
    syncActiveEditorBuffer();
    if (editorOpenaiFormDirty) await renderOpenaiFormToYaml();
    const skillContent = getEditorContentWithCategory();
    const result = await window.pywebview.api.save_skill_editor_data(editingFilename, {
      skill_content: skillContent,
      openai_yaml_content: editorOpenaiYamlContent,
      save_openai_yaml: (
        editorOpenaiYamlExists
        || editorOpenaiYamlDirty
        || editorOpenaiYamlCreateRequested
      ),
    });
    if (result.error) throw new Error(result.error);
    showToast(locales[currentLanguage].toastSaveSuccess, 'success');
    await closeEditorModal(true);
    await fetchSkills();
    await checkForUnregisteredSkills();
    if (currentProjectPath) {
      await fetchProjects();
      refreshCurrentProject();
    }
  } catch (e) {
    showToast((currentLanguage === 'zh' ? '保存失败: ' : 'Failed to save: ') + e, 'error');
  }
}

// ------------------------------------------
// Toast System
// ------------------------------------------

function showToast(message, type = 'success', options = {}) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
  toast.setAttribute('aria-atomic', 'true');
  let icon = 'check', iconClass = 'success';
  if (type === 'error') { icon = 'x'; iconClass = 'error'; }
  else if (type === 'warning') { icon = 'alert-triangle'; iconClass = 'warning'; }
  toast.innerHTML = `
    <div class="toast-icon ${iconClass}">
      <i data-lucide="${icon}" style="width:14px;height:14px;"></i>
    </div>
    <span class="toast-message">${escapeHtml(message)}</span>
    ${options.actionLabel ? `<button type="button" class="toast-action">${escapeHtml(options.actionLabel)}</button>` : ''}`;
  toastContainer.appendChild(toast);
  lucide.createIcons();
  setTimeout(() => toast.classList.add('show'), 10);
  let removed = false;
  const removeToast = () => {
    if (removed) return;
    removed = true;
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  };
  const action = toast.querySelector('.toast-action');
  if (action && options.onAction) {
    action.addEventListener('click', async () => {
      action.disabled = true;
      await options.onAction();
      removeToast();
    });
  }
  let remaining = options.duration || (options.actionLabel ? 8000 : 3500);
  let startedAt = Date.now();
  let removeTimer = null;
  const scheduleRemoval = () => {
    startedAt = Date.now();
    removeTimer = setTimeout(removeToast, remaining);
  };
  const pauseRemoval = () => {
    if (!removeTimer) return;
    clearTimeout(removeTimer);
    removeTimer = null;
    remaining = Math.max(500, remaining - (Date.now() - startedAt));
  };
  const resumeRemoval = () => {
    if (!removed && !removeTimer) scheduleRemoval();
  };
  toast.addEventListener('mouseenter', pauseRemoval);
  toast.addEventListener('mouseleave', resumeRemoval);
  toast.addEventListener('focusin', pauseRemoval);
  toast.addEventListener('focusout', resumeRemoval);
  scheduleRemoval();
}

async function handleChangeSkillsDir() {
  try {
    const result = await window.pywebview.api.change_skills_dir();
    if (!result) return;
    showToast(locales[currentLanguage].toastPathUpdate, 'success');
    skillsDirPath.textContent = result.skills_dir;
    skillsDirPath.title = result.skills_dir;
    await fetchSkills();
    await fetchProjects();
  } catch (e) {
    showToast((currentLanguage === 'zh' ? '更改全局技能库失败: ' : 'Failed to change skills directory: ') + e, 'error');
  }
}

async function handleRefreshSkills() {
  const icon = document.querySelector('#btn-refresh-skills i');
  if (icon) {
    icon.classList.add('spinning');
  }
  try {
    await fetchSkills();
    if (currentProjectPath) {
      await fetchProjects();
      
      const proj = projects.find(p => p.path === currentProjectPath);
      if (proj) {
        _loadProjectState(proj);
      }
    }
    showToast(locales[currentLanguage].toastRefreshSuccess, 'success');
  } catch (e) {
    showToast((currentLanguage === 'zh' ? '刷新技能库失败: ' : 'Failed to refresh skills: ') + e, 'error');
  } finally {
    if (icon) {
      setTimeout(() => {
        icon.classList.remove('spinning');
      }, 500);
    }
  }
}

// ------------------------------------------
// Settings Modal Handlers
// ------------------------------------------

const settingsModal = document.getElementById('settings-modal');
const settingsLanguage = document.getElementById('settings-language');
const settingsTheme = document.getElementById('settings-theme');
const settingsSkillsDir = document.getElementById('settings-skills-dir');
const settingsScanDir = document.getElementById('settings-scan-dir');
const settingsGlobalTargets = document.getElementById('settings-global-targets');

function scrollSettingsSection(sectionId) {
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  document.getElementById(sectionId)?.scrollIntoView({
    behavior: reducedMotion ? 'auto' : 'smooth',
    block: 'start'
  });
}

function syncGlobalTargetSettings() {
  settingsGlobalTargets?.querySelectorAll('.global-target-option').forEach(option => {
    const targetId = option.dataset.target;
    const input = option.querySelector('input[type="checkbox"]');
    const target = globalSkillTargetOptions.find(item => item.id === targetId);
    const available = !target || target.available !== false;
    if (input) {
      input.checked = available && globalSkillTargets.includes(targetId);
      input.disabled = !available;
    }
    option.classList.toggle('unavailable', !available);
    option.setAttribute('aria-disabled', available ? 'false' : 'true');
    const path = option.querySelector('.global-target-copy small');
    if (path && target && !target.requires_manual_install) {
      path.textContent = available
        ? target.path
        : `${target.path} · ${currentLanguage === 'zh' ? '未检测到' : 'Not detected'}`;
      path.title = target.path;
    }
  });
}

function syncSettingsChoiceControls() {
  document.querySelectorAll('[data-settings-choice]').forEach(group => {
    const target = group.dataset.settingsChoice === 'language'
      ? settingsLanguage
      : settingsTheme;
    group.querySelectorAll('.settings-choice').forEach(button => {
      const selected = button.dataset.value === target.value;
      button.classList.toggle('selected', selected);
      button.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
  });
}

document.querySelectorAll('[data-settings-choice]').forEach(group => {
  group.addEventListener('click', event => {
    const button = event.target.closest('.settings-choice');
    if (!button) return;
    const target = group.dataset.settingsChoice === 'language'
      ? settingsLanguage
      : settingsTheme;
    target.value = button.dataset.value;
    syncSettingsChoiceControls();
  });
});

function openSettingsModal() {
  settingsLanguage.value = currentLanguage;
  settingsTheme.value = currentTheme;
  syncSettingsChoiceControls();
  settingsSkillsDir.value = skillsDirPath.textContent;
  settingsScanDir.value = defaultScanDir;
  syncGlobalTargetSettings();
  document.getElementById('settings-aimodel').value = deepseekModel;
  document.getElementById('settings-apibase').value = apiBase;
  // API key field: leave empty placeholder — user must re-enter to change
  document.getElementById('settings-apikey').value = '';
  document.getElementById('settings-apikey').type = 'password';
  document.getElementById('settings-ai-import-optimization').checked = aiImportOptimization;
  document.getElementById('settings-ai-display-translation').checked = aiDisplayTranslation;
  updateAIConfigurationIndicators();

  const selectedLanguageChoice = document.querySelector(
    '[data-settings-choice="language"] .settings-choice.selected'
  );
  activateModal(settingsModal, selectedLanguageChoice);
  lucide.createIcons();
}

function closeSettingsModal() {
  deactivateModal(settingsModal);
}

async function handleSettingsPickSkillsDir() {
  try {
    const result = await window.pywebview.api.change_skills_dir();
    if (!result) return;
    settingsSkillsDir.value = result.skills_dir;
    showToast(locales[currentLanguage].toastPathUpdate, 'success');
  } catch (e) {
    showToast('Failed to select path: ' + e, 'error');
  }
}

async function handleSettingsPickScanDir() {
  try {
    const result = await window.pywebview.api.pick_default_scan_dir();
    if (!result) return;
    settingsScanDir.value = result.default_scan_dir;
    showToast(currentLanguage === 'zh' ? '默认扫描起点已更新' : 'Default projects path updated', 'success');
  } catch (e) {
    showToast('Failed to select path: ' + e, 'error');
  }
}

async function handleSaveSettings() {
  try {
    const settings = {
      skills_dir: settingsSkillsDir.value,
      language: settingsLanguage.value,
      theme: settingsTheme.value,
      default_scan_dir: settingsScanDir.value,
      ai_import_optimization: document.getElementById('settings-ai-import-optimization').checked,
      ai_display_translation: document.getElementById('settings-ai-display-translation').checked,
      global_skill_targets: Array.from(
        settingsGlobalTargets.querySelectorAll('input[type="checkbox"]:checked')
      ).map(input => input.value)
    };
    if (!settings.global_skill_targets.length) {
      showToast(
        currentLanguage === 'zh' ? '请至少选择一个全局启用目标' : 'Select at least one global target',
        'warning'
      );
      return;
    }
    const result = await window.pywebview.api.save_settings(settings);
    if (result.error) throw new Error(result.error);

    // Save AI config separately if API key, model, or base URL changed
    const apiKeyInput = document.getElementById('settings-apikey');
    const modelInput = document.getElementById('settings-aimodel');
    const apiBaseInput = document.getElementById('settings-apibase');
    const newModel = modelInput.value.trim() || deepseekModel;
    const newApiBase = apiBaseInput.value.trim() || apiBase;

    if (apiKeyInput.value.trim() || newApiBase !== apiBase || newModel !== deepseekModel) {
      const aiResult = await window.pywebview.api.save_ai_config(
        apiKeyInput.value.trim(),
        newModel,
        newApiBase
      );
      hasAiKey = Boolean(aiResult.has_ai_key);
      apiKeyHint = aiResult.api_key_hint || apiKeyHint;
    }
    deepseekModel = newModel;
    apiBase = newApiBase;

    currentLanguage = result.language;
    currentTheme = result.theme;
    defaultScanDir = result.default_scan_dir;
    aiImportOptimization = Boolean(result.ai_import_optimization);
    aiDisplayTranslation = Boolean(result.ai_display_translation);
    globalSkillTargets = result.global_skill_targets || ['codex'];
    globalSkillTargetOptions = result.global_skill_target_options || globalSkillTargetOptions;
    skillsDirPath.textContent = result.skills_dir;
    skillsDirPath.title = result.skills_dir;

    applyTheme(currentTheme);
    applyLanguage(currentLanguage);
    updateAIConfigurationIndicators();
    await Promise.all([fetchSkills(), fetchProjects()]);

    closeSettingsModal();
    showToast(locales[currentLanguage].toastSettingsSaved, 'success');
  } catch (e) {
    showToast('Failed to save settings: ' + e, 'error');
  }
}

// ------------------------------------------
// AI Chat Modal (with session management)
// ------------------------------------------

const aiModal = document.getElementById('ai-modal');
const aiChatMessages = document.getElementById('ai-chat-messages');
const aiChatInput = document.getElementById('ai-chat-input');
const aiSendBtn = document.getElementById('ai-send-btn');
const aiSkillPreview = document.getElementById('ai-skill-preview');
const aiSkillContent = document.getElementById('ai-skill-content');
const aiSessionList = document.getElementById('ai-session-list');
const agentStatusBadge = document.getElementById('agent-status-badge');
const agentPhase = document.getElementById('agent-phase');
const agentRunId = document.getElementById('agent-run-id');
const agentResumeButton = document.getElementById('agent-resume-button');
const agentTimeline = document.getElementById('agent-timeline');
const agentApprovalCard = document.getElementById('agent-approval-card');
const agentApprovalTool = document.getElementById('agent-approval-tool');
const agentApprovalArguments = document.getElementById('agent-approval-arguments');
const agentMemoryUsed = document.getElementById('agent-memory-used');
const agentMemoryEnabled = document.getElementById('agent-memory-enabled');
const agentMemoryOverview = document.getElementById('agent-memory-overview');
const agentPanelToggle = document.getElementById('agent-panel-toggle');
const aiCopyConversationButton = document.getElementById('ai-copy-conversation');
const aiChatInputHint = document.getElementById('ai-chat-input-hint');

let aiChatHistory = [];
let aiIsLoading = false;
let currentSessionId = null;
let allSessions = [];
let currentAgentRunId = null;
let currentAgentApprovalId = null;
let agentPanelCollapsed = false;

function updateAgentDialogControls() {
  const isZh = currentLanguage === 'zh';
  const t = locales[currentLanguage];
  const setText = (id, value) => {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  };
  const modalContainer = aiModal?.querySelector('.ai-modal-container');
  modalContainer?.classList.toggle('agent-panel-collapsed', agentPanelCollapsed);
  if (agentPanelToggle) {
    const label = agentPanelCollapsed
      ? (isZh ? '展开记录' : 'Show activity')
      : (isZh ? '收起记录' : 'Hide activity');
    const title = agentPanelCollapsed
      ? (isZh ? '展开执行记录' : 'Show Agent activity')
      : (isZh ? '收起执行记录' : 'Hide Agent activity');
    agentPanelToggle.innerHTML = `<i data-lucide="${
      agentPanelCollapsed ? 'panel-right-open' : 'panel-right-close'
    }"></i><span>${label}</span>`;
    agentPanelToggle.title = title;
    agentPanelToggle.setAttribute('aria-label', title);
    agentPanelToggle.setAttribute(
      'aria-expanded',
      agentPanelCollapsed ? 'false' : 'true'
    );
  }
  if (aiCopyConversationButton) {
    const label = isZh ? '复制对话' : 'Copy chat';
    aiCopyConversationButton.innerHTML = `<i data-lucide="copy"></i><span>${label}</span>`;
    aiCopyConversationButton.title = isZh ? '复制当前对话' : 'Copy current conversation';
    aiCopyConversationButton.setAttribute('aria-label', aiCopyConversationButton.title);
    aiCopyConversationButton.disabled = aiChatHistory.length === 0;
  }
  if (aiChatInputHint) {
    aiChatInputHint.textContent = isZh
      ? 'Enter 发送 · Shift+Enter 换行'
      : 'Enter to send · Shift+Enter for a new line';
  }
  if (aiChatInput) {
    aiChatInput.placeholder = isZh
      ? '描述 Skill 生命周期管理目标…'
      : 'Describe a Skill lifecycle goal…';
  }
  setText('ai-session-title-label', t.agentSessionList);
  setText('agent-empty-title', t.agentEmptyTitle);
  setText('agent-empty-description', t.agentEmptyDescription);
  setText('agent-suggestion-review', t.agentSuggestionReview);
  setText('agent-suggestion-review-note', t.agentSuggestionReviewNote);
  setText('agent-suggestion-audit', t.agentSuggestionAudit);
  setText('agent-suggestion-audit-note', t.agentSuggestionAuditNote);
  setText('agent-suggestion-extract', t.agentSuggestionExtract);
  setText('agent-suggestion-extract-note', t.agentSuggestionExtractNote);
  setText('agent-activity-title', isZh ? '执行记录' : 'Activity');
  setText('agent-current-phase-label', isZh ? '当前阶段' : 'Current phase');
  setText('agent-resume-label', isZh ? '恢复任务' : 'Resume run');
  setText('agent-approval-title', isZh ? '等待批准' : 'Approval required');
  setText('agent-reject-label', isZh ? '拒绝' : 'Reject');
  setText('agent-approve-label', isZh ? '批准并继续' : 'Approve and continue');
  setText('agent-timeline-title', isZh ? '工具时间线' : 'Tool timeline');
  setText('agent-memory-title', isZh ? '相关记忆' : 'Related memory');
  setText('agent-memory-view-all', isZh ? '查看全部' : 'View all');
  setText('ai-preview-title', isZh ? '📄 生成的技能预览' : '📄 Generated Skill preview');
  setText('ai-preview-copy-label', isZh ? '复制' : 'Copy');
  setText('ai-preview-regenerate-label', isZh ? '重新生成' : 'Regenerate');
  setText('ai-preview-save-label', isZh ? '保存' : 'Save');
  setText('agent-timeline-empty', isZh ? '运行后显示计划、工具调用、观察结果、批准和错误。' : 'Plans, tool calls, observations, approvals, and errors appear after a run starts.');
  setText('agent-memory-empty', isZh ? '本次尚未使用记忆。' : 'No memory has been used in this run.');
  setText('agent-memory-settings-label', isZh ? '记忆设置' : 'Memory settings');
  setText('agent-memory-enable-label', isZh ? '启用结构化记忆' : 'Enable structured memory');
  setText('agent-memory-clear-label', isZh ? '清理全部记忆' : 'Clear all memory');
  const sessionAddButton = document.querySelector('.ai-session-add');
  if (sessionAddButton) {
    sessionAddButton.title = isZh ? '新建会话' : 'New session';
    sessionAddButton.setAttribute('aria-label', sessionAddButton.title);
  }
  const activityPanel = document.getElementById('agent-activity-panel');
  activityPanel?.setAttribute('aria-label', isZh ? 'Agent 执行状态' : 'Agent activity status');
  if (agentStatusBadge?.classList.contains('idle')) {
    agentStatusBadge.textContent = isZh ? '空闲' : 'Idle';
    agentPhase.textContent = isZh ? '等待目标' : 'Waiting for a goal';
    agentRunId.textContent = isZh ? '尚未开始运行' : 'No run started';
  }
  if (aiSendBtn) {
    aiSendBtn.title = isZh ? '发送' : 'Send';
    aiSendBtn.setAttribute('aria-label', aiSendBtn.title);
  }
  lucide.createIcons();
}

function toggleAgentActivityPanel() {
  agentPanelCollapsed = !agentPanelCollapsed;
  try {
    localStorage.setItem(
      'skillhub.agentPanelCollapsed',
      agentPanelCollapsed ? '1' : '0'
    );
  } catch (_error) {
    // Panel state persistence is optional.
  }
  updateAgentDialogControls();
}

function resizeAgentChatInput() {
  if (!aiChatInput) return;
  aiChatInput.style.height = 'auto';
  aiChatInput.style.height = `${Math.min(aiChatInput.scrollHeight, 140)}px`;
}

aiChatInput?.addEventListener('input', resizeAgentChatInput);

async function openAIModal() {
  aiIsLoading = false;
  aiGeneratedSkill = null;
  aiSkillPreview.style.display = 'none';
  try {
    const savedPanelState = localStorage.getItem('skillhub.agentPanelCollapsed');
    agentPanelCollapsed = savedPanelState === null
      ? window.innerWidth <= 820
      : savedPanelState === '1';
  } catch (_error) {
    agentPanelCollapsed = false;
  }
  updateAgentDialogControls();
  activateModal(aiModal, aiChatInput);
  await loadSessionList(true);
  await refreshAgentMemory();
  lucide.createIcons();
  setTimeout(() => aiChatInput.focus(), 200);
}

async function closeAIModal() {
  deactivateModal(aiModal);
  await saveCurrentSession();
}

async function loadSessionList(selectSession = false) {
  try {
    allSessions = await window.pywebview.api.chat_list_sessions();
  } catch (e) {
    if (selectSession) allSessions = [];
  }
  renderSessionList();
  if (!selectSession) return;

  const preferredSession = allSessions.find(session => session.id === currentSessionId) || allSessions[0];
  if (preferredSession) {
    await switchToSession(preferredSession.id, false);
  } else {
    await createNewSession(false);
  }
}

function renderSessionList() {
  aiSessionList.innerHTML = '';
  allSessions.forEach(s => {
    const div = document.createElement('div');
    div.className = 'ai-session-item' + (s.id === currentSessionId ? ' active' : '');
    div.onclick = async () => { await switchToSession(s.id); };
    div.innerHTML = `
      <div class="ai-session-item-title">${escapeHtml(s.title || (currentLanguage === 'zh' ? '未命名' : 'Untitled'))}</div>
      <div class="ai-session-item-meta">${s.msg_count || 0} ${currentLanguage === 'zh' ? '条消息' : 'messages'}</div>
      <button class="ai-session-del" onclick="event.stopPropagation();deleteSession('${s.id}')" title="${currentLanguage === 'zh' ? '删除' : 'Delete'}">×</button>`;
    aiSessionList.appendChild(div);
  });
}

async function switchToSession(sid, saveBeforeSwitch = true) {
  if (sid === currentSessionId && aiChatHistory.length > 0) {
    renderSessionList();
    renderChatHistory();
    return;
  }
  if (saveBeforeSwitch) {
    await saveCurrentSession();
  }
  currentSessionId = sid;
  aiChatHistory = [];
  aiSkillPreview.style.display = 'none';
  aiGeneratedSkill = null;

  try {
    const r = await window.pywebview.api.chat_load_session(sid);
    if (r.session && r.session.messages) {
      aiChatHistory = r.session.messages;
    }
  } catch (e) { /* ignore */ }

  renderSessionList();
  renderChatHistory();
  await loadAgentRunForSession();
}

async function createNewSession(saveBeforeCreate = true) {
  if (saveBeforeCreate) {
    await saveCurrentSession();
  }
  currentSessionId = 's_' + Date.now();
  aiChatHistory = [];
  aiSkillPreview.style.display = 'none';
  aiGeneratedSkill = null;
  currentAgentRunId = null;
  currentAgentApprovalId = null;
  allSessions.unshift({
    id: currentSessionId,
    title: currentLanguage === 'zh' ? '新会话' : 'New Chat',
    msg_count: 0
  });
  renderSessionList();
  renderChatHistory();
  resetAgentRunPanel();
}

async function deleteSession(sid) {
  try { await window.pywebview.api.chat_delete_session(sid); } catch (e) {}
  allSessions = allSessions.filter(s => s.id !== sid);
  if (sid === currentSessionId) {
    currentSessionId = null;
    aiChatHistory = [];
  }
  renderSessionList();
  if (allSessions.length > 0 && !currentSessionId) {
    await switchToSession(allSessions[0].id, false);
  } else if (allSessions.length === 0) {
    await createNewSession(false);
  }
  renderChatHistory();
}

async function saveCurrentSession() {
  if (!currentSessionId || aiChatHistory.length === 0) return true;
  const title = aiChatHistory.find(m => m.role === 'user')?.content?.slice(0, 30)
    || (currentLanguage === 'zh' ? '未命名' : 'Untitled');
  const messages = aiChatHistory.map(message => ({ ...message }));
  try {
    const result = await window.pywebview.api.chat_save_session(
      currentSessionId,
      title,
      messages
    );
    if (result?.error) throw new Error(result.error);
    const existing = allSessions.find(session => session.id === currentSessionId);
    if (existing) {
      existing.title = title;
      existing.msg_count = messages.length;
    } else {
      allSessions.unshift({
        id: currentSessionId,
        title,
        msg_count: messages.length
      });
    }
    return true;
  } catch (e) {
    showToast(
      (currentLanguage === 'zh' ? '会话保存失败: ' : 'Failed to save chat: ') + (e.message || e),
      'error'
    );
    return false;
  }
}

function renderChatHistory() {
  aiChatMessages.innerHTML = '';
  if (aiChatHistory.length === 0) {
    aiChatMessages.innerHTML = getAgentEmptyStateMarkup();
    lucide.createIcons();
  } else {
    aiChatHistory.forEach(m => {
      appendChatBubble(m.role, m.content);
    });
  }
  aiChatMessages.scrollTop = aiChatHistory.length ? aiChatMessages.scrollHeight : 0;
  const generateButton = document.getElementById('ai-btn-generate');
  if (generateButton) generateButton.disabled = aiChatHistory.length === 0 || aiIsLoading;
  updateAgentDialogControls();
}

function getAgentEmptyStateMarkup() {
  const t = locales[currentLanguage];
  const suggestion = (icon, prompt, title, note) => `
    <button type="button" onclick="useAISuggestion(decodeURIComponent('${encodeURIComponent(prompt)}'))">
      <i data-lucide="${icon}" aria-hidden="true"></i>
      <span><strong>${escapeHtml(title)}</strong><small>${escapeHtml(note)}</small></span>
    </button>`;
  return `
    <div class="ai-chat-empty">
      <div class="ai-empty-mark"><i data-lucide="bot" aria-hidden="true"></i></div>
      <h4>${escapeHtml(t.agentEmptyTitle)}</h4>
      <p>${escapeHtml(t.agentEmptyDescription)}</p>
      <div class="ai-prompt-suggestions">
        ${suggestion('scan-search', t.agentPromptReview, t.agentSuggestionReview, t.agentSuggestionReviewNote)}
        ${suggestion('list-checks', t.agentPromptAudit, t.agentSuggestionAudit, t.agentSuggestionAuditNote)}
        ${suggestion('file-input', t.agentPromptExtract, t.agentSuggestionExtract, t.agentSuggestionExtractNote)}
      </div>
    </div>`;
}

// --- Chat interaction ---

function useAISuggestion(prompt) {
  if (!aiChatInput) return;
  aiChatInput.value = prompt;
  resizeAgentChatInput();
  aiChatInput.focus();
  aiChatInput.setSelectionRange(prompt.length, prompt.length);
}

function handleChatKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    sendAIMessage();
  }
}

function resetAgentRunPanel() {
  currentAgentRunId = null;
  currentAgentApprovalId = null;
  agentStatusBadge.textContent = currentLanguage === 'zh' ? '空闲' : 'Idle';
  agentStatusBadge.className = 'agent-status-badge idle';
  agentPhase.textContent = currentLanguage === 'zh' ? '等待目标' : 'Waiting for a goal';
  agentRunId.textContent = currentLanguage === 'zh' ? '尚未开始运行' : 'No run started';
  agentResumeButton.hidden = true;
  agentApprovalCard.hidden = true;
  agentTimeline.innerHTML = `<div class="agent-empty-note">${
    currentLanguage === 'zh'
      ? '运行后显示计划、工具调用、观察结果、批准和错误。'
      : 'Plans, tool calls, observations, approvals, and errors appear here.'
  }</div>`;
  agentMemoryUsed.innerHTML = `<div class="agent-empty-note">${
    currentLanguage === 'zh' ? '本次尚未使用记忆。' : 'No memory used in this run.'
  }</div>`;
}

function renderAgentWorkingState() {
  agentStatusBadge.textContent = currentLanguage === 'zh' ? '运行中' : 'Running';
  agentStatusBadge.className = 'agent-status-badge running';
  agentPhase.textContent = currentLanguage === 'zh' ? '分析目标并选择工具' : 'Analyzing goal and selecting tools';
  agentRunId.textContent = currentLanguage === 'zh' ? '正在创建运行记录…' : 'Creating run record…';
  agentResumeButton.hidden = true;
  agentApprovalCard.hidden = true;
  agentTimeline.innerHTML = `
    <div class="agent-timeline-item plan">
      <span class="agent-timeline-dot"></span>
      <div><strong>${currentLanguage === 'zh' ? '规划' : 'Plan'}</strong>
      <p>${currentLanguage === 'zh' ? '检索相关记忆并选择最小必要工具。' : 'Recall relevant memory and choose the minimum necessary tools.'}</p></div>
    </div>`;
}

function agentStatusLabel(status) {
  const labels = {
    running: currentLanguage === 'zh' ? '运行中' : 'Running',
    waiting_approval: currentLanguage === 'zh' ? '待批准' : 'Approval',
    completed: currentLanguage === 'zh' ? '已完成' : 'Completed',
    failed: currentLanguage === 'zh' ? '失败' : 'Failed',
    rejected: currentLanguage === 'zh' ? '已拒绝' : 'Rejected',
    max_steps: currentLanguage === 'zh' ? '已停止' : 'Stopped'
  };
  return labels[status] || status || (currentLanguage === 'zh' ? '空闲' : 'Idle');
}

function compactAgentText(value, maxLength = 140) {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  return text.length > maxLength
    ? `${text.slice(0, maxLength)}…`
    : text;
}

function formatAgentArgumentSummary(argumentsSummary) {
  const entries = Object.entries(argumentsSummary || {});
  if (!entries.length) return '';
  const visible = entries.slice(0, 3).map(([key, value]) => {
    if (value && typeof value === 'object') {
      if (Number.isInteger(value.count)) {
        return `${key}: ${value.count}`;
      }
      if (Number.isInteger(value.chars)) {
        return `${key}: ${value.chars} chars`;
      }
      return key;
    }
    return `${key}: ${compactAgentText(value, 56)}`;
  });
  if (entries.length > visible.length) {
    visible.push(`+${entries.length - visible.length}`);
  }
  return visible.join(' · ');
}

function formatAgentEvent(event) {
  const typeLabels = {
    plan: currentLanguage === 'zh' ? '规划' : 'Plan',
    tool_call: currentLanguage === 'zh' ? '工具调用' : 'Tool call',
    approval: currentLanguage === 'zh' ? '用户批准' : 'Approval',
    error: currentLanguage === 'zh' ? '错误' : 'Error',
    final: currentLanguage === 'zh' ? '最终回答' : 'Final'
  };
  let title = typeLabels[event.type] || event.type;
  if (event.tool) title += ` · ${event.tool}`;
  let detail = compactAgentText(event.summary || '', 180);
  if (event.type === 'tool_call') {
    const statusLabels = {
      ok: currentLanguage === 'zh' ? '成功' : 'Succeeded',
      error: currentLanguage === 'zh' ? '失败' : 'Failed',
      running: currentLanguage === 'zh' ? '执行中' : 'Running',
      waiting_approval: currentLanguage === 'zh' ? '等待批准' : 'Awaiting approval'
    };
    const segments = [statusLabels[event.status] || event.status || ''];
    const argumentText = formatAgentArgumentSummary(event.arguments);
    if (argumentText) segments.push(argumentText);
    if (event.result_summary) {
      segments.push(compactAgentText(event.result_summary, 150));
    }
    if (Number.isInteger(event.duration_ms)) {
      segments.push(`${event.duration_ms} ms`);
    }
    detail = segments.filter(Boolean).join(' · ');
  } else if (event.type === 'approval') {
    detail = compactAgentText(
      `${event.decision || ''}${event.reason ? ` · ${event.reason}` : ''}`,
      180
    );
  }
  return `
    <div class="agent-timeline-item ${escapeHtml(event.type || '')}">
      <span class="agent-timeline-dot"></span>
      <div>
        <strong>${escapeHtml(title)}</strong>
        <p>${escapeHtml(String(detail || ''))}</p>
      </div>
    </div>`;
}

function renderAgentRun(result) {
  if (!result || result.error) return;
  currentAgentRunId = result.run_id || currentAgentRunId;
  const status = result.status || 'idle';
  agentStatusBadge.textContent = agentStatusLabel(status);
  agentStatusBadge.className = `agent-status-badge ${status}`;
  agentPhase.textContent = result.phase || agentStatusLabel(status);
  agentRunId.textContent = currentAgentRunId
    ? `${currentAgentRunId.slice(0, 12)} · ${result.step_count || 0}/${result.max_steps || 32} steps`
    : (currentLanguage === 'zh' ? '尚未开始运行' : 'No run started');
  agentResumeButton.hidden = status !== 'running';
  const timeline = result.timeline || [];
  const maxVisibleTimelineEvents = 14;
  const visibleTimeline = timeline.slice(-maxVisibleTimelineEvents);
  const omittedTimelineCount = timeline.length - visibleTimeline.length;
  agentTimeline.innerHTML = timeline.length
    ? `${
        omittedTimelineCount > 0
          ? `<div class="agent-timeline-omitted">${
              currentLanguage === 'zh'
                ? `已省略较早的 ${omittedTimelineCount} 条记录`
                : `${omittedTimelineCount} earlier events omitted`
            }</div>`
          : ''
      }${visibleTimeline.map(formatAgentEvent).join('')}`
    : `<div class="agent-empty-note">${currentLanguage === 'zh' ? '暂无工具记录。' : 'No tool events.'}</div>`;

  const pending = result.pending_approval;
  currentAgentApprovalId = pending ? pending.approval_id || null : null;
  agentApprovalCard.hidden = !pending;
  if (pending) {
    agentApprovalTool.textContent = `${pending.tool} ${
      currentLanguage === 'zh' ? '将执行真实写操作，请核对参数摘要。' : 'will perform a real write. Review the summary.'
    }`;
    agentApprovalArguments.textContent = JSON.stringify(pending.arguments || {}, null, 2);
  }

  const memories = result.memory_used || [];
  agentMemoryUsed.innerHTML = memories.length
    ? memories.map(memory => `
        <div class="agent-memory-item">
          <span>${escapeHtml(memory.kind || 'memory')}</span>
          <p>${escapeHtml(memory.summary || '')}</p>
        </div>`).join('')
    : `<div class="agent-empty-note">${currentLanguage === 'zh' ? '本次未检索到相关记忆。' : 'No relevant memory recalled.'}</div>`;
  lucide.createIcons();
}

async function loadAgentRunForSession() {
  if (!currentSessionId) {
    resetAgentRunPanel();
    return;
  }
  try {
    const tasks = await window.pywebview.api.agent_list_tasks();
    const task = (tasks || []).find(item => item.session_id === currentSessionId);
    if (!task) {
      resetAgentRunPanel();
      return;
    }
    const result = await window.pywebview.api.agent_get_task(task.run_id);
    if (result && !result.error) renderAgentRun(result);
  } catch (_error) {
    resetAgentRunPanel();
  }
}

async function approveAgentAction() {
  if (!currentAgentRunId || !currentAgentApprovalId || aiIsLoading) return;
  aiIsLoading = true;
  aiSendBtn.disabled = true;
  agentPhase.textContent = currentLanguage === 'zh' ? '执行已批准操作…' : 'Applying approved action…';
  try {
    const result = await window.pywebview.api.agent_approve(
      currentAgentRunId,
      currentAgentApprovalId
    );
    if (result.error) throw new Error(result.error);
    renderAgentRun(result);
    if (result.final_answer) {
      appendChatBubble('ai', result.final_answer);
      aiChatHistory.push({ role: 'assistant', content: result.final_answer });
      await saveCurrentSession();
      await loadSessionList(false);
    }
    await Promise.all([fetchSkills(), fetchProjects()]);
  } catch (error) {
    appendChatBubble('ai', '❌ ' + (error.message || error));
  } finally {
    aiIsLoading = false;
    aiSendBtn.disabled = false;
  }
}

async function resumeAgentRun() {
  if (!currentAgentRunId || aiIsLoading) return;
  aiIsLoading = true;
  aiSendBtn.disabled = true;
  agentResumeButton.hidden = true;
  agentPhase.textContent = currentLanguage === 'zh' ? '正在恢复持久化任务…' : 'Resuming persisted task…';
  try {
    const result = await window.pywebview.api.agent_resume(currentAgentRunId);
    if (result.error) throw new Error(result.error);
    renderAgentRun(result);
    if (result.final_answer) {
      appendChatBubble('ai', result.final_answer);
      aiChatHistory.push({ role: 'assistant', content: result.final_answer });
      await saveCurrentSession();
      await loadSessionList(false);
    }
  } catch (error) {
    appendChatBubble('ai', '❌ ' + (error.message || error));
  } finally {
    aiIsLoading = false;
    aiSendBtn.disabled = false;
  }
}

async function rejectAgentAction() {
  if (!currentAgentRunId || aiIsLoading) return;
  const reason = await showCustomDialog({
    title: currentLanguage === 'zh' ? '拒绝写操作' : 'Reject write action',
    message: currentLanguage === 'zh'
      ? '可以填写拒绝原因；该操作不会修改文件。'
      : 'Optionally provide a reason. No file will be changed.',
    emoji: '🛡️',
    isPrompt: true,
    placeholder: currentLanguage === 'zh' ? '例如：先调整草案范围' : 'For example: revise the draft scope',
    confirmText: currentLanguage === 'zh' ? '拒绝操作' : 'Reject'
  });
  if (reason === null) return;
  aiIsLoading = true;
  aiSendBtn.disabled = true;
  try {
    const result = await window.pywebview.api.agent_reject(currentAgentRunId, reason || '');
    if (result.error) throw new Error(result.error);
    renderAgentRun(result);
    appendChatBubble('ai', result.final_answer);
    aiChatHistory.push({ role: 'assistant', content: result.final_answer });
    await saveCurrentSession();
    await loadSessionList(false);
  } catch (error) {
    appendChatBubble('ai', '❌ ' + (error.message || error));
  } finally {
    aiIsLoading = false;
    aiSendBtn.disabled = false;
  }
}

async function refreshAgentMemory() {
  try {
    const memory = await window.pywebview.api.agent_memory_view();
    agentMemoryEnabled.checked = Boolean(memory.enabled);
    const projects = memory.projects || [];
    const preferences = memory.preferences || [];
    const decisions = memory.decisions || [];
    agentMemoryOverview.innerHTML = `
      <div class="agent-memory-counts">
        <span>${currentLanguage === 'zh' ? '项目' : 'Projects'} ${projects.length}</span>
        <span>${currentLanguage === 'zh' ? '偏好' : 'Preferences'} ${preferences.length}</span>
        <span>${currentLanguage === 'zh' ? '决策' : 'Decisions'} ${decisions.length}</span>
      </div>
      ${[...projects, ...preferences, ...decisions].slice(-8).reverse().map(item => `
        <div class="agent-memory-item">
          <span>${escapeHtml(item.kind || 'memory')}</span>
          <p>${escapeHtml(item.summary || '')}</p>
        </div>`).join('')}`;
    lucide.createIcons();
  } catch (error) {
    agentMemoryOverview.textContent = String(error.message || error);
  }
}

async function showAgentMemoryManager() {
  await refreshAgentMemory();
  document.getElementById('agent-memory-manager').open = true;
}

async function toggleAgentMemory(enabled) {
  try {
    const result = await window.pywebview.api.agent_memory_set_enabled(Boolean(enabled));
    agentMemoryEnabled.checked = Boolean(result.enabled);
    showToast(
      result.enabled
        ? (currentLanguage === 'zh' ? '结构化记忆已启用' : 'Memory enabled')
        : (currentLanguage === 'zh' ? '结构化记忆已关闭' : 'Memory disabled'),
      'success'
    );
  } catch (error) {
    agentMemoryEnabled.checked = !enabled;
    showToast(String(error.message || error), 'error');
  }
}

async function clearAgentMemory() {
  const confirmed = await showCustomDialog({
    title: currentLanguage === 'zh' ? '清理结构化记忆' : 'Clear structured memory',
    message: currentLanguage === 'zh'
      ? '将删除项目记忆、用户偏好和决策记忆；聊天会话不会被删除。'
      : 'Project, preference, and decision memory will be removed. Chat sessions stay intact.',
    emoji: '🧹',
    confirmText: currentLanguage === 'zh' ? '清理记忆' : 'Clear memory'
  });
  if (!confirmed) return;
  try {
    const result = await window.pywebview.api.agent_memory_clear();
    if (result.error) throw new Error(result.error);
    await refreshAgentMemory();
    showToast(currentLanguage === 'zh' ? '结构化记忆已清理' : 'Memory cleared', 'success');
  } catch (error) {
    showToast(String(error.message || error), 'error');
  }
}

async function sendAIMessage() {
  const text = aiChatInput.value.trim();
  if (!text || aiIsLoading) return;

  const emptyEl = aiChatMessages.querySelector('.ai-chat-empty');
  if (emptyEl) emptyEl.remove();

  appendChatBubble('user', text);
  aiChatInput.value = '';
  resizeAgentChatInput();
  aiChatHistory.push({ role: 'user', content: text });

  const typingId = showTypingIndicator();
  aiIsLoading = true;
  aiSendBtn.setAttribute('disabled', 'true');
  renderAgentWorkingState();

  try {
    const result = await window.pywebview.api.agent_start(
      text,
      currentSessionId || '',
      currentProjectPath || ''
    );
    removeTypingIndicator(typingId);
    if (result.error) {
      appendChatBubble('ai', '❌ ' + result.error);
      agentStatusBadge.textContent = currentLanguage === 'zh' ? '失败' : 'Failed';
      agentStatusBadge.className = 'agent-status-badge failed';
      agentPhase.textContent = result.error;
      agentRunId.textContent = currentLanguage === 'zh' ? '未创建运行' : 'Run not created';
    } else {
      currentAgentRunId = result.run_id;
      renderAgentRun(result);
      if (result.final_answer) {
        appendChatBubble('ai', result.final_answer);
        aiChatHistory.push({ role: 'assistant', content: result.final_answer });
      } else if (result.status === 'waiting_approval') {
        appendChatBubble('ai', '需要你的批准才能继续执行右侧显示的写操作。');
      }
    }
    await saveCurrentSession();
    await loadSessionList(false);
  } catch (e) {
    removeTypingIndicator(typingId);
    appendChatBubble('ai', '❌ ' + (e.message || e));
    agentStatusBadge.textContent = currentLanguage === 'zh' ? '失败' : 'Failed';
    agentStatusBadge.className = 'agent-status-badge failed';
    agentPhase.textContent = String(e.message || e);
  } finally {
    aiIsLoading = false;
    aiSendBtn.removeAttribute('disabled');
    aiChatInput.focus();
  }
}

async function handleNewSession() {
  await createNewSession();
  aiChatInput.focus();
}

async function handleAIGenerateSkill() {
  if (aiChatHistory.length === 0 || aiIsLoading) return;
  const typingId = showTypingIndicator();
  aiIsLoading = true;
  const generateButton = document.getElementById('ai-btn-generate');
  if (generateButton) generateButton.disabled = true;
  try {
    const result = await window.pywebview.api.ai_chat(
      aiChatHistory.map(m => ({ role: m.role, content: m.content })),
      'generate'
    );
    removeTypingIndicator(typingId);
    if (result.error) {
      appendChatBubble('ai', '❌ ' + result.error);
    } else if (result.skill) {
      aiGeneratedSkill = result.skill;
      aiSkillContent.innerHTML = renderMarkdown(aiGeneratedSkill.content || '');
      enhanceChatCodeBlocks(aiSkillContent);
      aiSkillPreview.style.display = 'block';
      aiChatHistory.push({ role: 'assistant', content: '✅ 技能已生成，请在下方预览并保存' });
      appendChatBubble('ai', '✅ 技能已生成！你可以在下方预览，满意后点击 **保存**。');
      await saveCurrentSession();
      await loadSessionList(false);
    }
  } catch (e) {
    removeTypingIndicator(typingId);
    appendChatBubble('ai', '❌ ' + (e.message || e));
  } finally {
    aiIsLoading = false;
    if (generateButton) generateButton.disabled = aiChatHistory.length === 0;
  }
}

async function copyGeneratedSkillPreview(button) {
  if (!aiGeneratedSkill?.content) return;
  await copyAgentText(aiGeneratedSkill.content, button);
}

async function handleAISave() {
  if (!aiGeneratedSkill) return;
  let fname = (aiGeneratedSkill.title || 'ai_skill')
    .replace(/[\\/:*?"<>|]/g, '').replace(/\s+/g, '_').slice(0, 60);
  if (!fname) fname = 'ai_generated_skill';
  fname += '.md';
  try {
    const r = await window.pywebview.api.ai_save_skill({ filename: fname, content: aiGeneratedSkill.content });
    if (r.error) throw new Error(r.error);
    showToast((currentLanguage === 'zh' ? '✅ 已保存: ' : '✅ Saved: ') + r.filename, 'success');
    aiSkillPreview.style.display = 'none';
    aiGeneratedSkill = null;
    await fetchSkills();
    if (currentProjectPath) { await fetchProjects(); refreshCurrentProject(); }
  } catch (e) {
    showToast((currentLanguage === 'zh' ? '保存失败: ' : 'Failed: ') + e, 'error');
  }
}

async function handleAIRegenerate() {
  aiSkillPreview.style.display = 'none';
  aiGeneratedSkill = null;
  if (aiChatHistory.length > 0 && aiChatHistory[aiChatHistory.length - 1].role === 'assistant') {
    aiChatHistory.pop();
  }
  await handleAIGenerateSkill();
}

// --- Connection Test ---

async function handleAITestConnection() {
  const btn = document.getElementById('btn-test-connection');
  const resultDiv = document.getElementById('test-result');
  const origHTML = btn.innerHTML;

  btn.innerHTML = '<div class="loading-spinner" style="width:14px;height:14px;"></div>';
  btn.setAttribute('disabled', 'true');
  resultDiv.style.display = 'none';

  try {
    // Save the model and base URL first (they might have changed)
    const modelInput = document.getElementById('settings-aimodel');
    const apiKeyInput = document.getElementById('settings-apikey');
    const apiBaseInput = document.getElementById('settings-apibase');
    const newModel = modelInput.value.trim() || 'deepseek-chat';
    const newApiBase = apiBaseInput.value.trim() || 'https://api.deepseek.com/v1';

    const savedConfig = await window.pywebview.api.save_ai_config(
      apiKeyInput.value.trim(),
      newModel,
      newApiBase
    );
    hasAiKey = Boolean(savedConfig.has_ai_key);
    apiKeyHint = savedConfig.api_key_hint || apiKeyHint;
    deepseekModel = newModel;
    apiBase = newApiBase;

    const result = await window.pywebview.api.ai_test_connection();
    resultDiv.style.display = 'block';
    if (result.ok) {
      resultDiv.style.background = 'var(--green-soft)';
      resultDiv.style.color = 'var(--green)';
      resultDiv.textContent = (currentLanguage === 'zh'
        ? `✅ 连接成功！模型: ${result.model}，延迟: ${result.latency_ms}ms`
        : `✅ Connected! Model: ${result.model}, Latency: ${result.latency_ms}ms`);
      updateAIConfigurationIndicators();
    } else {
      resultDiv.style.background = 'var(--rose-soft)';
      resultDiv.style.color = 'var(--rose)';
      resultDiv.textContent = '❌ ' + result.error;
    }
  } catch (e) {
    resultDiv.style.display = 'block';
    resultDiv.style.background = 'var(--rose-soft)';
    resultDiv.style.color = 'var(--rose)';
    resultDiv.textContent = '❌ ' + e;
  } finally {
    btn.innerHTML = origHTML;
    btn.removeAttribute('disabled');
    lucide.createIcons();
  }
}

function toggleApiKeyVisibility() {
  const input = document.getElementById('settings-apikey');
  const icon = document.getElementById('apikey-eye-icon');
  if (input.type === 'password') {
    input.type = 'text';
    if (icon) icon.setAttribute('data-lucide', 'eye-off');
  } else {
    input.type = 'password';
    if (icon) icon.setAttribute('data-lucide', 'eye');
  }
  lucide.createIcons();
}

// --- Chat UI Helpers ---

async function writeClipboardText(text) {
  const value = String(text ?? '');
  if (!value) throw new Error('Nothing to copy');
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch (_error) {
      // file:// WebView contexts can reject the async Clipboard API.
    }
  }

  const activeElement = document.activeElement;
  const selection = window.getSelection();
  const savedRanges = [];
  if (selection) {
    for (let index = 0; index < selection.rangeCount; index += 1) {
      savedRanges.push(selection.getRangeAt(index).cloneRange());
    }
  }
  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.left = '-9999px';
  textarea.style.top = '0';
  document.body.appendChild(textarea);
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);
  let copied = false;
  try {
    copied = document.execCommand('copy');
  } finally {
    textarea.remove();
    if (activeElement?.focus) activeElement.focus({ preventScroll: true });
    if (selection && savedRanges.length) {
      selection.removeAllRanges();
      savedRanges.forEach(range => selection.addRange(range));
    }
  }
  if (!copied) throw new Error('Clipboard unavailable');
}

async function copyAgentText(text, button = null) {
  try {
    await writeClipboardText(text);
    if (button) {
      const previous = button.innerHTML;
      button.innerHTML = `<i data-lucide="check"></i><span>${
        currentLanguage === 'zh' ? '已复制' : 'Copied'
      }</span>`;
      button.classList.add('copied');
      lucide.createIcons();
      setTimeout(() => {
        if (!document.contains(button)) return;
        button.innerHTML = previous;
        button.classList.remove('copied');
        lucide.createIcons();
      }, 1400);
    } else {
      showToast(currentLanguage === 'zh' ? '已复制到剪贴板' : 'Copied to clipboard', 'success');
    }
    return true;
  } catch (_error) {
    showToast(
      currentLanguage === 'zh'
        ? '复制失败，请选中文本后按 Ctrl+C'
        : 'Copy failed. Select the text and press Ctrl+C.',
      'error'
    );
    return false;
  }
}

function enhanceChatCodeBlocks(contentRoot) {
  contentRoot.querySelectorAll('pre > code').forEach(code => {
    const pre = code.parentElement;
    if (!pre || pre.parentElement?.classList.contains('ai-chat-code-block')) return;
    const wrapper = document.createElement('div');
    wrapper.className = 'ai-chat-code-block';
    pre.before(wrapper);
    wrapper.appendChild(pre);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ai-code-copy-button';
    button.title = currentLanguage === 'zh' ? '复制代码' : 'Copy code';
    button.setAttribute('aria-label', button.title);
    button.innerHTML = `<i data-lucide="copy"></i><span>${
      currentLanguage === 'zh' ? '复制' : 'Copy'
    }</span>`;
    button.addEventListener('click', () => copyAgentText(code.textContent || '', button));
    wrapper.appendChild(button);
  });
}

async function copyCurrentAgentConversation() {
  const visibleMessages = Array.from(
    aiChatMessages.querySelectorAll('.ai-chat-bubble')
  ).map(bubble => ({
    role: bubble.agentMessageRole,
    content: bubble.agentMessageText,
  })).filter(message => message.role && message.content);
  const messages = visibleMessages.length ? visibleMessages : aiChatHistory;
  if (!messages.length) {
    showToast(currentLanguage === 'zh' ? '当前对话为空' : 'This conversation is empty', 'info');
    return;
  }
  const transcript = messages.map(message => {
    const role = message.role === 'user'
      ? (currentLanguage === 'zh' ? '用户' : 'User')
      : 'SkillOps Agent';
    return `## ${role}\n\n${message.content || ''}`;
  }).join('\n\n---\n\n');
  await copyAgentText(transcript);
}

function appendChatBubble(role, text) {
  const div = document.createElement('div');
  div.className = `ai-chat-bubble ai-chat-${role}`;
  div.agentMessageRole = role;
  div.agentMessageText = String(text ?? '');
  const content = document.createElement('div');
  content.className = 'ai-chat-bubble-content';
  content.innerHTML = renderMarkdown(text);
  div.appendChild(content);
  enhanceChatCodeBlocks(content);

  const actions = document.createElement('div');
  actions.className = 'ai-chat-bubble-actions';
  const copyButton = document.createElement('button');
  copyButton.type = 'button';
  copyButton.className = 'ai-chat-action-button';
  copyButton.title = currentLanguage === 'zh' ? '复制此消息' : 'Copy message';
  copyButton.setAttribute('aria-label', copyButton.title);
  copyButton.innerHTML = `<i data-lucide="copy"></i><span>${
    currentLanguage === 'zh' ? '复制' : 'Copy'
  }</span>`;
  copyButton.addEventListener('click', () => copyAgentText(text, copyButton));
  actions.appendChild(copyButton);
  div.appendChild(actions);

  aiChatMessages.appendChild(div);
  aiChatMessages.scrollTop = aiChatMessages.scrollHeight;
  queueMicrotask(updateAgentDialogControls);
  lucide.createIcons();
}

let _typingCounter = 0;
function showTypingIndicator() {
  const id = ++_typingCounter;
  const div = document.createElement('div');
  div.className = 'ai-chat-bubble ai-chat-ai';
  div.id = `typing-${id}`;
  div.innerHTML = '<div class="ai-chat-bubble-content"><div class="ai-typing"><span></span><span></span><span></span></div></div>';
  aiChatMessages.appendChild(div);
  aiChatMessages.scrollTop = aiChatMessages.scrollHeight;
  return id;
}

function removeTypingIndicator(id) {
  const el = document.getElementById(`typing-${id}`);
  if (el) el.remove();
}

// ------------------------------------------
// Structured Review and Custom Dialog Systems
// ------------------------------------------

function showStructuredReview({
  title,
  kicker = '',
  intro = '',
  metrics = [],
  sections = [],
  confirmText = '',
  footnote = '',
  danger = false
}) {
  if (reviewResolve) {
    reviewResolve(false);
    reviewResolve = null;
  }
  document.getElementById('review-title').textContent = title;
  document.getElementById('review-kicker').textContent = kicker || (currentLanguage === 'zh' ? '变更审阅' : 'Change review');
  const summaryElement = document.getElementById('review-summary');
  summaryElement.innerHTML = metrics.map(metric => `
    <div class="review-metric ${escapeHtml(metric.tone || '')}">
      <strong>${escapeHtml(String(metric.value ?? 0))}</strong>
      <span>${escapeHtml(metric.label || '')}</span>
    </div>`).join('');
  summaryElement.hidden = metrics.length === 0;

  const bodyElement = document.getElementById('review-body');
  const sectionMarkup = sections.map(section => {
    const body = section.diff !== undefined
      ? `<pre class="review-diff">${escapeHtml(String(section.diff || ''))}</pre>`
      : `<ul class="review-list">${(section.items || []).map(item => `<li>${escapeHtml(String(item))}</li>`).join('')}</ul>`;
    return `
      <section class="review-section">
        <div class="review-section-header">
          <strong>${escapeHtml(section.title || '')}</strong>
          ${section.meta ? `<span>${escapeHtml(section.meta)}</span>` : ''}
        </div>
        ${body}
      </section>`;
  }).join('');
  bodyElement.innerHTML = `${intro ? `<p class="review-intro">${escapeHtml(intro)}</p>` : ''}${sectionMarkup}`;

  const cancelButton = document.getElementById('review-cancel');
  const confirmButton = document.getElementById('review-confirm');
  cancelButton.textContent = currentLanguage === 'zh' ? '取消' : 'Cancel';
  confirmButton.textContent = confirmText || (currentLanguage === 'zh' ? '确认继续' : 'Confirm and continue');
  confirmButton.classList.toggle('review-confirm-danger', danger);
  document.getElementById('review-footnote').textContent = footnote || (
    currentLanguage === 'zh' ? '确认前请检查影响范围' : 'Review the impact before confirming'
  );
  lucide.createIcons();
  activateModal(reviewModal, confirmButton);
  return new Promise(resolve => {
    reviewResolve = resolve;
  });
}

function closeStructuredReview(result) {
  deactivateModal(reviewModal);
  const resolve = reviewResolve;
  reviewResolve = null;
  if (resolve) resolve(Boolean(result));
}

let dialogResolve = null;

function showCustomDialog({
  title,
  message,
  emoji = '💬',
  isPrompt = false,
  placeholder = '',
  defaultValue = '',
  confirmText = '',
  secondaryText = '',
  secondaryValue = 'secondary'
}) {
  return new Promise((resolve) => {
    dialogResolve = resolve;
    
    document.getElementById('dialog-title').textContent = title;
    document.getElementById('dialog-message').textContent = message;
    document.getElementById('dialog-emoji').textContent = emoji;
    
    const inputContainer = document.getElementById('dialog-input-container');
    const inputEl = document.getElementById('dialog-input');
    
    if (isPrompt) {
      inputContainer.style.display = 'block';
      inputEl.value = defaultValue;
      inputEl.placeholder = placeholder;
    } else {
      inputContainer.style.display = 'none';
    }
    
    document.getElementById('dialog-btn-cancel').textContent = locales[currentLanguage].editModalCancel || 'Cancel';
    document.getElementById('dialog-btn-confirm').textContent = confirmText || (currentLanguage === 'zh' ? '确定' : 'Confirm');
    const secondaryBtn = document.getElementById('dialog-btn-secondary');
    secondaryBtn.style.display = secondaryText ? 'inline-flex' : 'none';
    secondaryBtn.textContent = secondaryText;
    secondaryBtn.onclick = () => {
      const resolve = dialogResolve;
      dialogResolve = null;
      const modal = document.getElementById('dialog-modal');
      if (modal) deactivateModal(modal);
      if (resolve) resolve(secondaryValue);
    };
    
    const confirmBtn = document.getElementById('dialog-btn-confirm');
    confirmBtn.onclick = () => {
      const val = isPrompt ? inputEl.value.trim() : true;
      const resolve = dialogResolve;
      dialogResolve = null;
      
      const modal = document.getElementById('dialog-modal');
      if (modal) deactivateModal(modal);
      
      if (resolve) resolve(val);
    };
    
    const dialogModal = document.getElementById('dialog-modal');
    activateModal(dialogModal, isPrompt ? inputEl : confirmBtn);
    if (isPrompt) setTimeout(() => inputEl.select(), 50);
  });
}

function closeDialogModal() {
  const modal = document.getElementById('dialog-modal');
  if (modal) deactivateModal(modal);
  if (dialogResolve) {
    const resolve = dialogResolve;
    dialogResolve = null;
    resolve(null);
  }
}

// Keyboard shortcuts for Custom Dialog Modal (Null-Safe)
const dialogInput = document.getElementById('dialog-input');
if (dialogInput) {
  dialogInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const confirmBtn = document.getElementById('dialog-btn-confirm');
      if (confirmBtn) confirmBtn.click();
    }
  });
}

// ------------------------------------------
// Delete Skill Feature
// ------------------------------------------

async function handleDeleteSkill(filename) {
  const skill = skills.find(item => item.filename === filename);
  const codexGlobalNote = skill?.codex_global_enabled
    ? (currentLanguage === 'zh'
        ? ' 同时会移除由 SkillHub 管理的全局入口和导出包；撤销删除时会尝试恢复。'
        : ' SkillHub-managed global entries and exports will also be removed and restored if you undo.')
    : '';
  const confirmed = await showCustomDialog({
    title: currentLanguage === 'zh' ? '删除技能' : 'Delete Skill',
    message: currentLanguage === 'zh'
      ? `将 "${filename}" 移入 SkillHub 回收站。删除后可在提示条中立即撤销。${codexGlobalNote}`
      : `Move "${filename}" to SkillHub trash. You can undo it from the confirmation toast.${codexGlobalNote}`,
    emoji: '🗑️'
  });
  if (!confirmed) return;
  
  try {
    const result = await window.pywebview.api.delete_skill(filename);
    if (result.error) throw new Error(result.error);
    await fetchSkills();
    if (currentProjectPath) {
      await fetchProjects();
      refreshCurrentProject();
    }
    showToast(
      currentLanguage === 'zh' ? '技能已移入回收站' : 'Skill moved to trash',
      'success',
      {
        actionLabel: currentLanguage === 'zh' ? '撤销' : 'Undo',
        duration: 9000,
        onAction: async () => {
          const restored = await window.pywebview.api.restore_deleted_skill(result.trash_token);
          if (restored.error) {
            showToast(
              (currentLanguage === 'zh' ? '恢复失败: ' : 'Restore failed: ') + restored.error,
              'error'
            );
            return;
          }
          await fetchSkills();
          if (currentProjectPath) {
            await fetchProjects();
            refreshCurrentProject();
          }
          showToast(
            restored.warning
              ? ((currentLanguage === 'zh' ? '技能已恢复，但部分全局目标恢复失败: ' : 'Skill restored, but some global targets could not be restored: ') + restored.warning)
              : (currentLanguage === 'zh' ? '技能已恢复' : 'Skill restored'),
            restored.warning ? 'warning' : 'success'
          );
        }
      }
    );
  } catch (e) {
    showToast((currentLanguage === 'zh' ? '删除失败: ' : 'Failed to delete: ') + e, 'error');
  }
}

// ------------------------------------------
// Explicit Global Window Scope Bindings
// ------------------------------------------
window.handleChangeSkillsDir = handleChangeSkillsDir;
window.handleRefreshSkills = handleRefreshSkills;
window.openSettingsModal = openSettingsModal;
window.closeSettingsModal = closeSettingsModal;
window.closeGlobalTargetModal = closeGlobalTargetModal;
window.applySkillGlobalTargets = applySkillGlobalTargets;
window.handleSettingsPickSkillsDir = handleSettingsPickSkillsDir;
window.handleSettingsPickScanDir = handleSettingsPickScanDir;
window.handleSaveSettings = handleSaveSettings;
window.handlePickProject = handlePickProject;
window.handleCreateSkill = handleCreateSkill;
window.handleImportSkill = handleImportSkill;
window.handleSelectProject = handleSelectProject;
window.handleToggleSkill = handleToggleSkill;
window.handleDeleteProject = handleDeleteProject;
window.handleSyncSkills = handleSyncSkills;
window.handleSearch = handleSearch;
window.openSkillViewer = openSkillViewer;
window.openEditorModal = openEditorModal;
window.handleAddSkillCategory = handleAddSkillCategory;
window.handleDeleteSkillCategory = handleDeleteSkillCategory;
window.openCollectionModal = openCollectionModal;
window.closeCollectionModal = closeCollectionModal;
window.closeEditorModal = closeEditorModal;
window.switchModalTab = switchModalTab;
window.handleSaveSkill = handleSaveSkill;
window.closeDialogModal = closeDialogModal;
window.handleDeleteSkill = handleDeleteSkill;
window.showCustomDialog = showCustomDialog;
window.openAIModal = openAIModal;
window.closeAIModal = closeAIModal;
window.sendAIMessage = sendAIMessage;
window.handleChatKeydown = handleChatKeydown;
window.handleAIGenerateSkill = handleAIGenerateSkill;
window.handleAISave = handleAISave;
window.handleAIRegenerate = handleAIRegenerate;
window.handleAITestConnection = handleAITestConnection;
window.toggleApiKeyVisibility = toggleApiKeyVisibility;
window.handleNewSession = handleNewSession;
window.deleteSession = deleteSession;
