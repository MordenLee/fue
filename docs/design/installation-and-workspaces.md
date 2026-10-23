# 安装、宿主接入与资料库发现

## 两条用户路径

FUE 保留 Core、Studio、Skill 三个组件，对用户提供两种安装方式：

| 路径 | 安装内容 | 后续接入 |
| --- | --- | --- |
| Agent 版 | 独立 Core、Python 运行环境、指定宿主目录内的 Skill | 后装 Studio 自动读取登记并复用资料库 |
| 桌面版 | Studio 及用于首次部署的 Core/Python/Skill 资源 | 设置 → 通用 → 资料库与 Agent 接入 → 安装 FUE Skill |

Skill 不是完整运行环境。复制 Skill 文件夹不等于安装 Core。独立研究和清洗仍由 FUE 执行，宿主记忆不反向同步。

## 给 Agent 的安装指令

可以将下面这段交给具备本地命令执行能力的 Agent，并提供 FUE 完整源码或已发布的 Agent 离线包：

> 请按 FUE 的 docs/design/installation-and-workspaces.md 安装 Agent 版。先运行安装检查，有已登记的 Core 和资料库就复用。将 fue-skill 安装到本宿主支持的 skills 目录。只有明确首次创建资料库时才使用 --init；不能为解决连接失败而新建空库。安装后运行 Skill 的 status 和 libraries list，报告实际使用的数据目录。不要上传宿主历史或修改宿主记忆配置。

安装器不猜测不同宿主的私有目录。宿主已有 Skill 安装机制可以先放置 Skill，但仍需按其连接说明完成 Core 安装。宿主是否自动发现 Skill、是否需要重载由宿主决定。

## Agent 版操作

### 从源码安装

需要 Python 3.11+。在完整仓库根目录运行：

```powershell
python install.py inspect
# 已有 FUE 数据目录：
python install.py install --skill-dir "宿主的 skills 目录" --data-dir "D:\FUEData"
# 首次创建一个空资料库：
python install.py install --skill-dir "宿主的 skills 目录" --data-dir "D:\FUEData" --init
```

无可复用运行环境时，安装器复制 Core 源码，在独立目录创建 venv 并安装依赖，不修改系统 Python。首次源码安装需要联网获取依赖。安装日志走 stderr，stdout 返回 JSON 结果。

已有默认资料库时，可省略 `--data-dir`；显式指定另一个目录不会静默切换已有全局默认。新安装的 Skill 通过 `connection.json` 中的 `workspace_id` 绑定本次选中的资料库。既有 Skill 的本地配置保留。

### Windows 离线包

离线包包含 `install.ps1`、`install.py`、`fue-core/`、`fue-skill/` 和 `python/`。解压后：

```powershell
powershell -NoProfile -File .\install.ps1 inspect
powershell -NoProfile -File .\install.ps1 install --skill-dir "宿主的 skills 目录" --data-dir "D:\FUEData" --init
powershell -NoProfile -File "宿主的 skills 目录\fue-skill\scripts\fue.ps1" status --json
powershell -NoProfile -File "宿主的 skills 目录\fue-skill\scripts\fue.ps1" --auto-start libraries list --json
```

便携 Python 与依赖随包提供，安装和执行 Skill 不要求系统 PATH 中有 Python。宿主可能仍对脚本执行有自己的权限限制；安装器不修改这些限制。

重复安装相同 Skill 不覆盖数据；不同内容需要 `--update-skill`，会保留原 Skill 备份及连接设置。单独下载 Skill、又没有 Core 或完整源码时，会提示获取完整发行包，不会假装安装完成。

## 共同登记与资料库

默认登记位置：

- Windows：`%APPDATA%/fue/installation.json`
- macOS：`~/Library/Application Support/fue/installation.json`
- Linux：`${XDG_CONFIG_HOME:-~/.config}/fue/installation.json`

`FUE_REGISTRY_PATH` 可指定独立登记文件，其父目录也作为该安装上下文的默认配置根目录；用于隔离测试或便携部署。`FUE_INSTALL_ROOT` 可指定运行环境存放目录。

登记格式为 `schema_version: 1`，含 `runtimes`、`workspaces`、`default_runtime`、`default_workspace`。运行环境项记录目录、Python、API/应用版本及是否由安装器管理；资料库项记录 ID、名称和数据目录。登记文件不包含模型密钥和运行时身份凭据。

写入使用文件锁与原子替换。读取和检查不创建数据库。登记已有目录时以只读方式检查 SQLite 中的 FUE 表。路径失效或登记损坏会报错，不会回退到新空库。

资料库保存 SQLite、Chroma、工作记忆和运行状态。安装目录只放程序。Studio 和 Skill 共用相同数据路径，同机接入无需 JSON 迁移。

## Studio 首次使用与切换

1. 存在一个已登记资料库时自动连接；旧版 `core-connection.json` 和默认旧数据目录也会被发现。
2. 多个候选时显示选择，不自动合并。选择后在当前 Studio 配置中记住路径。
3. 无候选时提供“创建默认资料库”“打开已有资料库”“取消”。
4. 设置页可打开另一个已有目录。只登记并为下次启动选择，当前会话、任务和数据连接不强行切换。
5. 设置页可选择宿主的 skills 目录并安装 Skill。不会修改宿主的其他配置。

生产 Studio 首次部署时将便携运行环境复制到用户的共享运行环境目录；以后复用登记的 Core。独立 Core 不放在 Studio 安装目录。交互式卸载 Studio 时，由用户选择是否同时卸载 Core 和 Python 环境，并告知删除后 Agent Skill 将暂时无法使用。资料库单独保留。

开发模式优先使用 `FUE_DATA_DIR`（兼容 `APP_BACKEND_DATA_DIR`）或仓库 `.fue-workspace.json` 指定的目录；新环境使用 `workspaces/development`，旧 `backend/` 仍可发现。已选资料库丢失时拒绝静默创建空库。设置 `FUE_REGISTRY_PATH`、`FUE_USE_REGISTERED_WORKSPACE=1` 或在界面明确选择资料库后可进入共同登记流程。开发环境登记的是用户管理的源码/Python，删除源码或 venv 后需要修复连接。

## 版本与生命周期

- Core 状态接口提供 `api_version`、`data_format_version`、应用版本。客户端拒绝不兼容的大版本/API/数据格式。
- 每个资料库增加 `workspace.json`。Core 在数据库初始化前检查它，拒绝低版本打开较新的资料库。
- 数据库使用独立 `schema_migrations` 编号；即使产品版本仍为 2.0.0，必要的 schema 更新也会执行。迁移前通过 SQLite backup API 保存快照，事务迁移成功后写入工作区清单。当前没有 Chroma 格式迁移，不能将 SQLite 快照称为全部附件/向量备份。
- 安装登记记录 Core 源码指纹；同版本实现发生变化时，Studio 也会提示更新安装器管理的 Core。
- `install.py install --upgrade` 显式更新运行环境。若 Studio 或研究任务仍占用 Core，会拒绝升级；空闲 Core 正常退出后才能切换。新旧环境并排保存，新的启动成功后才替换已有默认运行环境。
- 当前检查不实现未知未来格式迁移，也不会自动恢复备份覆盖数据。
- Core 继续按需启动，Studio lease 和实际工作维持存活，空闲约五分钟退出；无需系统服务。

卸载 Skill 只删除宿主中的 Skill 目录。交互式卸载 Studio 会询问是否删除安装器管理的 Core/Python，默认选中保留；静默卸载和版本更新保留共享组件。删除只针对有运行环境标记、且通过路径与资料库隔离检查的目录，不删除用户自行登记的源码环境或宿主 Skill。仍有 Core 占用资料库时会中止卸载并提示退出后重试。聊天记录与知识库不随 Core 删除。需要单独执行相同清理时，可从完整源码或离线包运行 `python install.py remove-core --confirm`；执行清理的 Python 必须位于待删除运行环境之外。

## 构建与验证

先准备桌面端便携 Python，再运行：

```powershell
python scripts/build-agent-bundle.py
```

生成 `fue-studio/dist/fue-agent-2.0.0-windows-x64.zip` 及 SHA-256 文件。打包仅包含应用源码、Skill 和便携 Python，不包含用户数据库或连接信息。构建得到本地包不代表已上传 GitHub Release。

自动测试：`fue-core/tests/test_installation.py` 覆盖登记、选择、无副作用检查、损坏/缺失目录、重复安装、保留连接配置、旧库发现、备份和降级拒绝。实际验证还应覆盖两种安装顺序：Agent → Studio，以及 Studio → Agent，检查相同数据目录及同一测试知识库，无需调用模型。
