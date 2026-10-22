# FUE

FUE 是一个基于 Electron、React、TypeScript 和 FastAPI 的桌面 AI 工作台，提供模型配置、对话、知识库管理与检索能力。项目希望将日常对话中积累的信息，逐步连接到可持续维护的知识与写作流程。

## 当前版本

当前正式版为 **v1.0.11**。下载请前往 [GitHub Releases](https://github.com/MordenLee/fue/releases/tag/v1.0.11)，更新与当前限制见 [发布说明](docs/releases/1.0.11.md)。

本次 1.0.11 同版本更新增加记忆管理：材料处理状态、限长 summary.md、压缩记录、精确回读及用量展示；工作记忆默认关闭，需在对话设置中启用。请重新下载安装包获取更新。

架构文档：[当前聊天记忆与 MCP](docs/design/conversation-memory.md)、[长对话工作记忆 v2 设计](docs/design/working-context.md)、[v2 实施清单](docs/plans/working-context-v2.md)。具体启用、真实模型验证与已知限制见 [记忆管理说明](docs/validation/working-context-2026-10-21.md)。

现有功能包括：

- AI 对话、流式输出与会话管理。
- 模型供应商及聊天、嵌入、重排序等模型配置。
- 知识库文档管理、检索增强问答与引用展示。
- 中英文界面、明暗主题及相关设置。

本版新增可配置的 Agent/Skill 执行体系、聊天问答对记忆索引、历史检索与相邻上下文阅读，并修复设置选项的勾选图标排版。同版本补充了工作记忆与按需压缩。写作编辑器为现有原型；多人协作、完整运行恢复、精确费用估算与多级压缩仍待完善。

## 后续开发方向

拆分以 [FUE 2.0 架构与拆分决策](docs/design/fue-architecture-v2.md) 为准。本地重构分支已拆成 Core、Studio、Skill，增加独立接入、双身份和空闲回收；实现范围与验证见 [拆分验收记录](docs/validation/core-split-2026-10-21.md)。当前 GitHub 正式版仍为 1.0.11，未发布本次重构。下述写作与协作能力留到下个大版本。

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

需要 Node.js/npm 和 Python 3.11+。以下命令在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r fue-core/requirements.txt
npm install
npm --prefix fue-studio install
npm run dev
```

桌面开发入口会启动后端服务。首次使用时，在应用中配置模型供应商及所需模型。

类型检查与构建：

```powershell
npm --prefix fue-studio run typecheck
npm run build
```

更多说明见 [后端说明](fue-core/README.md) 与 [前端说明](fue-studio/README.md)。

## 目录

- `fue-studio/`：Electron 主进程、预加载层与 React 界面。
- `fue-core/`：FastAPI 服务、对话、模型与知识库相关模块。
- `fue-skill/`：外部 Agent 的安装、连接和 Direct/Delegated 使用说明。
- `backend/`：仅保留原开发数据，忽略进 Git；业务代码已迁入 Core。
- `contracts/`：Core 对外接口与数据约定；供应商预设随 Core 打包。
- `i18n/`：中英文翻译资源。

## 许可

使用和分发须遵守 [LICENSE](LICENSE) 中的条款。
