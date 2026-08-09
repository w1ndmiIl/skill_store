# SkillHub

[中文](README.md) · [User manual](docs/SkillHub使用说明书.md) · [Download the latest release](https://github.com/w1ndwill/skill_store/releases/latest) · [MIT License](LICENSE)

SkillHub is a local AI Skill management and synchronization tool. It keeps reusable development rules, workflows, and specialist capabilities in one place, then applies them selectively to projects or clients such as Codex, Claude Code, Antigravity, Gemini CLI, and VS Code/Copilot. Current version: **3.5.0**.

Users can review changes, conflicts, and scope overlaps before a write and safely roll back afterward. Import inspection and display localization do not rewrite the original semantics of third-party Skills. SkillOps Agent is optional assistance for finding, inspecting, and maintaining Skills; it does not replace manual management or approval.

![SkillHub English Skill library](docs/screenshots/en/skill-library.png)

*Captured from the v3.3.0 portable build. Skill names, project paths, and enablement states come from the local demonstration environment.*

## Problems SkillHub solves

- Skills are scattered across directories, repositories, and clients.
- AI coding clients use different discovery paths, causing repeated configuration.
- Projects require different Skill sets, while direct copying creates conflicts and stale duplicates.
- Imports and synchronization need previews, ownership records, and rollback to avoid overwriting work.

SkillHub is intended for developers who use multiple AI coding clients, maintain multiple projects, or have accumulated reusable custom Skills.

## Core workflow

Import → local inspection → categorization or collection organization → project or global target selection → preview and conflict review → synchronization, global enablement, or rollback.

## Product capabilities

### 1. Skill asset management

SkillHub imports Markdown, ZIP files, standard `SKILL.md` folders, and repository collections. It provides one workspace for browsing, search, categories, editing, display localization, trash recovery, and deterministic inspection while keeping display metadata separate from source semantics.

#### Multi-Skill collections

![English Skill collection manager](docs/screenshots/en/collection-manager.png)

Repository imports are scanned for collection boundaries. A collection can be disabled as a unit while each child Skill remains reviewable and independently selectable.

#### Skill document details

![English Skill document details](docs/screenshots/en/skill-detail.png)

The detail drawer presents source information, category, tags, Frontmatter, and rendered Markdown. Editing explicitly opens the source; project-only Skills remain read-only.

#### Skill usage configuration

Standard Skill folders expose both `SKILL.md` and `agents/openai.yaml`. The OpenAI metadata editor defaults to an explained form for display metadata, the recommended starter prompt, implicit invocation policy, and tool dependencies, while retaining raw YAML as an advanced mode. Global enablement controls availability for a target client; `allow_implicit_invocation` independently controls whether the model may select the Skill automatically.

### 2. Distribution and project sync

#### Per-project configuration

![English project Skill configuration](docs/screenshots/en/project-configuration.png)

Each project selects its own Skills. The view combines source descriptions, categories, sync status, and enablement controls. A bottom action bar summarizes pending changes and opens a preview before writing. Every executable library Skill can independently target Codex, Claude Code, Antigravity, Gemini CLI, VS Code, or Claude Desktop without binding it to a project.

![Per-Skill global target selection in English](docs/screenshots/en/global-target-selection.png)

Settings only maintains first-enable defaults; each Skill can override them in the same target-selection dialog.

![Default global target settings in English](docs/screenshots/en/global-target-settings.png)

If the same Skill is already enabled in user scope and selected for the current project, SkillHub reports a scope overlap and requires explicit confirmation. It does not merge or automatically remove either entry, avoiding silent changes to the global environment used by other projects.

Generated project content lives at:

```text
<project>\.agent\skills\
<project>\AGENTS.md
```

## Main features

| Capability | Current behavior |
| --- | --- |
| Global Skill library | Manage Markdown guidance, standard `SKILL.md` folders, and Skill collections |
| Skill usage configuration | Visually edit `agents/openai.yaml` interface metadata, invocation policy, and tool dependencies with an advanced YAML mode |
| Multi-client global enablement | Choose Codex, Claude Code, Antigravity, Gemini CLI, VS Code/Copilot, or Claude Desktop independently for each Skill; publishing creates a client-specific view without rewriting the source Skill |
| Claude Desktop export | Build a correctly structured upload ZIP; Claude Desktop still requires manual upload from `Customize > Skills` because it does not watch a local Skill directory |
| Import inspection | Locally detect duplicates, same-name conflicts, risky entries, path issues, and compatibility across six clients; Claude tool pre-approval receives a separate warning |
| Bilingual descriptions | Use display-only localization without rewriting third-party `SKILL.md` |
| Project synchronization | Preview additions, updates, removals, file conflicts, and global/project scope overlaps before writing |
| Sync rollback | Undo the most recent sync when affected project files have not changed again |
| SkillOps Agent | Optional tool-assisted module for finding, inspecting, previewing, and maintaining Skills |
| Single-instance startup | A second launch focuses the existing window instead of opening another |
| Local data model | Skills, settings, sessions, Agent memory, and backups stay on the machine |

### 3. Optional AI assistance

SkillOps Agent is an auxiliary module built on top of SkillHub's existing library and project synchronization workflows. It can help find, inspect, preview, install, and maintain Skills, but it does not replace manual imports, editing, categorization, or synchronization and does not expose an unrestricted shell.

![SkillOps Agent English workspace](docs/screenshots/en/skillops-agent.png)

The model can only call predefined bounded tools. The runtime rejects clearly unrelated requests and checks the original goal, network intent, active project, write intent, and preview binding before every relevant tool call. Skill bodies, web pages, repository documentation, tool results, and recalled memories are marked as untrusted data and cannot change the role, permissions, or approval policy.

Installation, saving, and synchronization require a preview. Approval is bound to the exact tool, target arguments, content or tree hashes, and a one-time approval ID; a changed target invalidates the old approval. Long-term memory accepts only allowlisted fields and explicit memory intent, and rejects content that attempts to broaden permissions, skip approval, or rewrite security rules.

## Quick start

1. Download `SkillHub.exe` from [GitHub Releases](https://github.com/w1ndwill/skill_store/releases/latest).
2. Launch the app and choose a global Skill library.
3. Import a `.md`, `.zip`, standard Skill folder, or Skill collection.
4. Optionally adjust target defaults in Settings, then choose clients separately from each Skill's global action.
5. For per-project configuration, add a target project and select the Skills it needs.
6. Review the sync preview, then confirm the write.
7. Optional: open SkillOps Agent for assisted inspection, installation, or maintenance.

The application is portable and requires no installer. On first launch it creates:

```text
%LOCALAPPDATA%\SkillHub\skills
```

## Run from source

```powershell
git clone https://github.com/w1ndwill/skill_store.git
cd skill_store
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Build the portable executable:

```powershell
python -m pip install pyinstaller
pyinstaller --clean --noconfirm SkillHub.spec
```

## Repository layout

```text
├── agent_runtime.py         # Agent loop, tool protocol, approvals, memory, and run records
├── main.py                  # Backend, file operations, sync, and Agent tool adapters
├── static/                  # PyWebView frontend, interactions, and bundled resources
├── docs/
│   ├── SkillHub使用说明书.md
│   └── screenshots/
│       ├── zh/              # Chinese interface screenshots
│       └── en/              # English interface screenshots
├── SkillHub.spec            # PyInstaller build entry
└── requirements.txt
```

## Security and privacy

- API keys remain in local configuration and are shown only in masked form.
- Agent memory and run records exclude API keys, complete sensitive files, and hidden chain of thought.
- External Skills, pages, and tool results are untrusted data, not new operating instructions.
- The Agent is limited to Skill lifecycle work; unrelated, unauthorized network, cross-project, and read-only-to-write calls are blocked at runtime.
- Agent writes bind preview hashes, current target state, an argument digest, and a one-time approval ID, so stale approvals cannot be reused.
- Same-name, different-content targets require an explicit replace, keep-both, or cancel decision.
- Imports never execute repository hooks, MCP servers, installer scripts, or downloaded code.
- Unmanaged project files are not silently overwritten.
- Release builds exclude personal Skills, local configuration, tests, sessions, memory, and run logs.

The fixed regression suite in `security_evals/` covers prompt injection, Markdown/Base64 hidden instructions, secondary injection, domain escape, cross-project access, memory poisoning, stale approval, and secret leakage. Run it with:

```powershell
python -B security_evals\run_security_evals.py
```

The current 12 deterministic cases establish a baseline of 100% normal-task completion and out-of-scope refusal, with 0% attack success, dangerous tool execution, approval bypass, sensitive-information leakage, and false refusal. This suite checks deterministic runtime controls and does not replace continuing red-team evaluation against real models.

## Boundaries and next steps

- SkillOps Agent is not a general-purpose Agent and does not handle weather, finance, general programming, or private-file requests.
- Remote installation is limited to constrained public sources and isolated previews; downloaded scripts, hooks, and MCP services are never executed.
- Future work will expand real-model attacks, encoded and multilingual variants, and measurement of the security/usability balance.

## Tech stack

- Python + [pywebview](https://pywebview.flowrl.com/)
- System WebView2 runtime
- HTML, CSS, and JavaScript
- Optional OpenAI-compatible API and DuckDuckGo web search

## License

[MIT](LICENSE)
