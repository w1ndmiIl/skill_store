# SkillHub

[English](README_EN.md) · [使用说明书](docs/SkillHub使用说明书.md) · [下载最新版](https://github.com/w1ndwill/skill_store/releases/latest) · [MIT License](LICENSE)

SkillHub 是一个本地运行的 AI Skill 管理与同步工具。它用于集中保存可复用的开发规则、工作流和专业能力，并将它们按需应用到不同项目或 Codex、Claude Code、Cursor、Cline、OpenCode、Windsurf、Gemini CLI、VS Code/Copilot 等客户端。当前版本：**3.5.0**。

用户可以在写入前查看变化、冲突和作用域重叠，在写入后安全回滚；导入体检和展示本地化不会直接改写第三方 Skill 的原始语义。SkillOps Agent 是可选辅助功能，用自然语言帮助查找、检查和维护 Skill，不取代手动管理与审批流程。

![SkillHub 中文技能库界面](docs/screenshots/zh/skill-library.png)

*截图依据 v3.5.0 当前界面重拍；Skill 名称、项目路径和启用状态均为脱敏演示数据。*

## SkillHub 解决什么问题

- Skill 分散在多个目录、仓库和客户端中，难以统一查找与维护。
- 不同 AI 编程工具使用不同的发现目录，同一套规则需要重复配置。
- 多项目需要不同 Skill 组合，直接复制文件容易产生冲突和过期副本。
- 导入、同步和修改如果没有预览、所有权记录与回滚，容易覆盖已有工作。

SkillHub 适合同时使用多个 AI 编程工具、维护多个项目，或已经积累自定义 Skill 的开发者。

## 核心工作流程

导入 Skill → 本地体检 → 分类或集合整理 → 选择项目或全局目标 → 查看预览与冲突 → 同步、全局启用或回滚。

## 产品能力

### 1. Skill 资产管理

SkillHub 支持导入 Markdown、ZIP、标准 `SKILL.md` 文件夹和仓库集合，并在统一界面中完成浏览、搜索、分类、编辑、展示本地化、回收站恢复和本地体检。第三方 Skill 的展示信息与原始语义分开保存。

#### 多 Skill 集合

![中文 Skill 集合管理](docs/screenshots/zh/collection-manager.png)

仓库级导入会先扫描集合边界。集合可以整体停用，子 Skill 仍可单独查看和选择；关闭集合不会删除源文件或丢失子项选择。

#### Skill 文档详情

![中文 Skill 文档详情](docs/screenshots/zh/skill-detail.png)

详情抽屉展示来源、分类、标签、Frontmatter 和渲染后的 Markdown。编辑操作显式进入源文件，项目专属 Skill 保持只读。

#### Skill 使用配置编辑

![Skill 使用配置可视化编辑](docs/screenshots/zh/skill-metadata-editor.png)

标准 Skill 文件夹可分别编辑 `SKILL.md` 和 `agents/openai.yaml`。后者默认提供可视化配置，逐项说明显示名称、界面简短说明、推荐使用提示、自动调用策略及工具依赖的作用；高级用户仍可切换到 YAML 源码。全局启用只决定 Skill 是否对目标客户端可用，`allow_implicit_invocation` 独立决定是否允许模型根据请求自动选择该 Skill。

### 2. 分发与项目同步

#### 项目独立配置

![中文项目 Skill 配置](docs/screenshots/zh/project-configuration.png)

每个项目独立选择需要的 Skill。界面同时展示来源说明、分类、同步状态和启用开关；底部操作栏汇总待应用变化，并在写入前打开同步预览。全局库中的每个可执行 Skill 还可以分别选择发布到 Codex、Claude Code、Cursor、Cline、OpenCode、Windsurf、Antigravity、Gemini CLI、VS Code 或 Claude Desktop，不必绑定项目。

![中文逐 Skill 全局目标选择](docs/screenshots/zh/global-target-selection.png)

设置页只维护首次启用时使用的默认目标；每个 Skill 都可以在统一的目标选择窗口中覆盖这些默认值。

![中文默认全局目标设置](docs/screenshots/zh/global-target-settings.png)

如果同一个 Skill 已在用户全局范围启用，又被当前项目选中，SkillHub 会把它标为“作用域重叠”并要求明确确认。两份入口不会被自动合并或互相删除，避免在用户不知情时改变其他项目的全局环境。

同步产物位于：

```text
<项目目录>\.agent\skills\
<项目目录>\AGENTS.md
```

## 主要功能

| 能力 | 当前行为 |
| --- | --- |
| 全局技能库 | 管理 Markdown 规则、标准 `SKILL.md` 文件夹和 Skill 集合 |
| Skill 使用配置 | 可视化编辑 `agents/openai.yaml` 的界面元数据、调用策略和工具依赖，并保留 YAML 高级模式 |
| 多客户端全局启用 | 每个 Skill 独立选择 Codex、Claude Code、Cursor、Cline、OpenCode、Windsurf、Antigravity、Gemini CLI、VS Code/Copilot 或 Claude Desktop；发布时生成目标端适配副本，不改源 Skill |
| Claude Desktop 导出 | 生成符合上传结构的 ZIP；由于 Claude Desktop 不监听本地 Skill 目录，仍需在 `Customize > Skills` 中手动上传 |
| 导入体检 | 在本机识别重复、同名冲突、风险条目、路径问题及十类客户端兼容性；Claude 工具预授权单独提示 |
| 双语说明 | 根据界面语言使用展示缓存，不改写第三方 `SKILL.md` |
| 项目同步 | 先预览新增、更新、移除、文件冲突和全局/项目作用域重叠，再执行写入 |
| 同步撤销 | 项目文件未被继续修改时，可安全撤销最近一次同步 |
| SkillOps Agent | 可选的工具化辅助模块，用于检索、检查、预览和维护 Skill |
| 单实例运行 | 第二次启动唤醒已有窗口，不创建第二个应用窗口 |
| 本地数据 | Skill、配置、会话、Agent 记忆和备份均保存在本机 |

### 3. 可选 AI 辅助

SkillOps Agent 是 SkillHub 中的辅助模块，用于在现有技能库和项目同步流程上完成 Skill 检索、检查、安装预览和维护。它不取代手动导入、编辑、分类或同步功能，也不提供任意终端访问。

![SkillOps Agent 中文工作区](docs/screenshots/zh/skillops-agent.png)

模型只能调用预先定义的有边界工具。运行时会拒绝明显的领域外请求，并在每次工具调用前检查原始目标、联网意图、当前项目、写入意图和预览绑定。Skill 正文、网页、仓库说明、工具返回和历史记忆都作为不可信数据传给模型，不能改变角色、权限或审批规则。

安装、保存和同步等写操作必须先形成预览。审批绑定具体工具、目标参数、内容或文件树哈希以及一次性审批 ID；预览后目标发生变化时，旧审批失效。长期记忆只接受白名单字段和明确的用户记忆意图，并拒绝扩大权限、跳过审批或改写安全规则的内容。

## 快速开始

1. 从 [GitHub Releases](https://github.com/w1ndwill/skill_store/releases/latest) 下载 `SkillHub.exe`。
2. 启动程序并选择全局 Skill 库目录。
3. 导入 `.md`、`.zip`、标准 Skill 文件夹或 Skill 集合。
4. 可在设置中调整默认目标；点击某个 Skill 的“全局启用”后，为它单独选择客户端。
5. 如需项目独立配置，添加目标项目并选择需要的 Skill。
6. 查看同步预览，确认后写入项目。
7. 可选：需要辅助检查、安装或维护 Skill 时，打开 SkillOps Agent。

程序为便携版，无需安装。首次启动时默认创建：

```text
%LOCALAPPDATA%\SkillHub\skills
```

## 从源码运行

```powershell
git clone https://github.com/w1ndwill/skill_store.git
cd skill_store
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

构建便携版：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm SkillHub.spec
```

## 仓库结构

```text
├── agent_runtime.py         # Agent 循环、工具协议、审批、记忆与运行记录
├── main.py                  # 后端、文件操作、同步与 Agent 工具适配
├── static/                  # PyWebView 前端、交互与本地资源
├── docs/
│   ├── SkillHub使用说明书.md
│   └── screenshots/
│       ├── zh/              # 中文界面截图
│       └── en/              # 英文界面截图
├── SkillHub.spec            # PyInstaller 构建入口
└── requirements.txt
```

## 安全与隐私

- API Key 只保存在本地配置中，界面仅显示脱敏状态。
- Agent 记忆和运行记录不保存 API Key、完整敏感文件或隐藏思维链。
- 外部 Skill、网页和工具返回默认是不可信数据，不能成为新的操作指令。
- Agent 只处理 Skill 生命周期任务；领域外、未授权联网、跨项目和只读目标中的写调用会被运行时阻止。
- Agent 写操作使用预览哈希、当前目标状态、参数摘要哈希和一次性审批 ID 绑定，过期审批不能复用。
- 同名不同内容必须明确选择替换、保留两个版本或取消。
- 导入过程不会执行仓库中的 Hook、MCP 服务、安装脚本或下载代码。
- 项目中不受 SkillHub 管理的同名文件不会被静默覆盖。
- Release 不包含个人 Skill、本地配置、测试、会话、记忆或运行日志。

固定安全评测位于 `security_evals/`，覆盖提示词注入、Markdown/Base64 隐藏指令、二次注入、领域越界、跨项目、记忆污染、过期审批和敏感信息泄漏。运行：

```powershell
python -B security_evals\run_security_evals.py
```

当前 12 个确定性用例的基线结果为：正常任务完成率和领域外拒绝率 100%，攻击成功率、危险工具执行率、审批绕过率、敏感信息泄漏率和正常任务误拒率均为 0%。该评测验证运行时约束，不替代对真实模型进行持续的红队测试。

## 边界与后续方向

- SkillOps Agent 不是通用 Agent，不处理天气、股票、通用编程或私人文件读取。
- 远程安装仅支持受约束的公开来源和隔离预览，不执行下载包中的脚本、Hook 或 MCP 服务。
- 后续将扩展真实模型攻击集、更多编码与多语言变体，并持续统计安全性与正常任务可用性的平衡。

## 技术栈

- Python + [pywebview](https://pywebview.flowrl.com/)
- 系统 WebView2
- HTML、CSS、JavaScript
- 可选的 OpenAI 兼容接口与 DuckDuckGo 联网搜索

## 开源协议

[MIT](LICENSE)
