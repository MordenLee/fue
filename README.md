# FUE

FUE 是一个基于 Electron、React、TypeScript 和 FastAPI 的桌面 AI 工作台，提供模型配置、对话、知识库管理与检索能力。项目希望将日常对话中积累的信息，逐步连接到可持续维护的知识与写作流程。

## 当前版本

当前源码版本为 **v2.0.0**，更新与当前限制见 [2.0.0 更新说明](docs/releases/2.0.0.md)。本次同步源码及版本标签；历史安装包请查看 [GitHub Releases](https://github.com/MordenLee/fue/releases)，1.0.11 安装包不包含本次重构。

完整重构后的职责、执行管理、数据库迁移和开发工作区见 [实施架构](docs/design/core-studio-skill-implementation.md)。本地新增改动的验证记录不代表 GitHub 安装包已经更新。

2.0.0 将底层拆分为 Core、Studio、Skill，并增加携带向量的知识库 JSON 导入导出；迁移直接复用已有文本、引用和向量，不调用模型。写作入口暂时隐藏，修复 Windows 后台 Core 启动时多弹出终端的问题。使用方式见 [知识库迁移说明](docs/design/knowledge-base-transfer.md)。

架构文档：[当前聊天记忆与 MCP](docs/design/conversation-memory.md)、[长对话工作记忆 v2 设计](docs/design/working-context.md)、[v2 实施清单](docs/plans/working-context-v2.md)。具体启用、真实模型验证与已知限制见 [记忆管理说明](docs/validation/working-context-2026-10-21.md)。

现有功能包括：

- AI 对话、流式输出与会话管理。
- 模型供应商及聊天、嵌入、重排序等模型配置。
- 知识库文档管理、检索增强问答与引用展示。
- 中英文界面、明暗主题及相关设置。

本版保留可配置的 Agent/Skill 执行体系、聊天问答对记忆索引、历史检索、相邻上下文阅读与按需压缩。工作记忆默认关闭，需在对话设置中启用。写作原型代码和数据保留，页面不显示；多人协作、完整运行恢复、精确费用估算与多级压缩仍待完善。

## 后续开发方向

拆分以 [FUE 2.0 架构与拆分决策](docs/design/fue-architecture-v2.md) 为准。2.0.0 已拆成 Core、Studio、Skill，增加独立接入、双身份和空闲回收；实现范围与验证见 [拆分验收记录](docs/validation/core-split-2026-10-21.md)。下述写作与协作能力留到后续版本。

### 1. 将所有 Chat 对话内容建设为可编辑、可追溯的知识库

让每次对话都成为可持续积累、整理和复用的知识，而不只是一段聊天记录。

- 将全部对话内容纳入知识管理，支持编辑、整理、分类和检索。
- 保留原始对话及修改历史，记录内容来自哪次会话、哪条消息，以及何时发生修改。
- 建立对话、引用资料和知识条目之间的来源关联，让后续检索、问答与写作能够回溯依据。
- 编辑后同步更新检索索引，同时保留历史版本与恢复能力。

### 2. 增加协作写作功能

围绕文稿、讨论和知识引用建立协作流程，逐步支持多人共同写作。

- 提供文稿编辑、保存及与相关对话、知识条目的关联。
- 支持评论、修改建议、版本记录与修改审阅。
- 逐步完善共享权限、多人编辑及冲突处理。
- AI 辅助修改应保留来源与改动记录，并允许用户审阅、接受或拒绝。

多人协作属于后续开发目标，当前写作编辑器为原型，尚不支持多人协作。

### 3. 开发面向 CC、Codex、DSH 等平台的 Skill 接口

让外部平台通过统一接口使用 FUE 的知识、只读聊天记忆和研究执行能力。

- 定义目录、知识检索、上下文读取、引文和 FUE 记忆查询接口。
- 面向 CC、Codex、DSH 等平台提供适配层、调用说明及 Skill 示例。
- 明确读写权限、调用范围、错误反馈与版本兼容约定。
- 外部研究委托由 FUE 执行并保存自身的任务记录；宿主聊天与记忆不反向同步到 FUE。

本地接入包见 [FUE Skill](fue-skill/SKILL.md)，安装与连接见其 references。已验证脚本接入；宿主自身的发现与加载行为依其安装机制，不承诺所有客户端相同体验。

### 4. 优化部分对话逻辑

持续改善对话的连贯性、可靠性以及与知识库之间的协作方式。

- 优化上下文组织、历史消息加载与长对话处理。
- 改善流式输出、消息持久化及界面状态同步。
- 优化知识检索、引用关联与回答内容之间的一致性。
- 完善中断、重试和异常反馈，减少重复消息与状态错乱。

## 本地开发

安装 Agent 版、后装 Studio 复用已有知识库，以及桌面端安装 Skill 的步骤见 [安装与资料库管理](docs/design/installation-and-workspaces.md)。完整源码根目录提供 `install.py` / `install.ps1`，桌面端设置页提供资料库和 Agent 接入入口。

需要 Node.js/npm 和 Python 3.11+。以下命令在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r fue-core/requirements.txt
npm install
npm --prefix fue-studio install
npm run dev
```

桌面开发入口会发现或启动 Core。首次使用时，在应用中配置模型供应商及所需模型。

类型检查与构建：

```powershell
npm --prefix fue-studio run typecheck
npm run build
```

更多说明见 [Core 说明](fue-core/README.md) 与 [Studio 说明](fue-studio/README.md)。回归测试运行 `npm run test:core`。

## 目录

- `fue-studio/`：Electron 主进程、预加载层与 React 界面。
- `fue-core/`：FastAPI 服务、对话、模型与知识库相关模块。
- `fue-skill/`：外部 Agent 的安装、连接和 Direct/Delegated 使用说明。
- `workspaces/`：开发工作区，忽略入 Git；`.fue-workspace.json` 选择当前开发数据目录。
- `backend/`：旧开发资料的兼容/回退位置，不再承载业务代码，不能当作无用源码直接删除。
- `artifacts/`：本地测试和构建产物，忽略入 Git。
- `contracts/`：Core 对外接口与数据约定；供应商预设随 Core 打包。
- `i18n/`：中英文翻译资源。

## 许可

使用和分发须遵守 [LICENSE](LICENSE) 中的条款。
