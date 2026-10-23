# Core / Studio / Skill 实施架构

更新：2026-10-23。产品版本保持 2.0.0，数据库迁移编号独立维护。

## 组件和目录

```text
fue-core/
  fue_core/
    platform/           # 路径、注册、迁移、安装与生命周期
    execution.py        # 聊天幂等、状态、取消和统一事件存储
    chat/router.py      # 兼容 HTTP 路由
    chat/service.py     # 聊天编排与持久化
    agents/             # 声明式 Agent 与工具执行
    knowledge/ memory/ providers/ ...
  tests/
fue-studio/src/
  main/ preload/ renderer/
fue-skill/              # 外部宿主接入说明与薄 CLI 包装
contracts/             # API 合约
workspaces/            # 忽略入 Git 的开发数据
artifacts/             # 忽略入 Git 的测试结果、临时环境与构建产物
```

不再维护另一套 frontend/backend 工程。Studio 的 main、preload、renderer 是 Electron 自身的职责划分，继续保留。本机 HTTP 服务由 Core 提供；Studio 与 Skill 不直接读写业务数据库。

根 package.json 只提供命令，UI 依赖和锁文件由 Studio 管理。Python 包统一归属 fue_core，旧 HTTP 路径和 main.py 启动适配器保留。业务模块内部仍可按实际复杂度继续细分，不要求每个小模块都增加一层空服务。

## 执行与费用

每次新聊天携带 request_id。Core 在调用模型前持久占用该 ID；相同输入的已完成请求返回保存结果，执行中或失败的重复请求返回 409，改变输入复用 ID 也返回 409。客户端仅自动重试 GET/HEAD，不自动重发生成和写入请求。

状态为 running、succeeded、failed、cancelled、interrupted。显式取消传递到执行协程；传输断开和 Core 重启归为 interrupted。没有完成标记的 SSE EOF 不再被视为成功。部分流式回答在可捕获的中断时保存；进程被强制杀死时尚未落盘的 token 不保证恢复。继续阅读原记录不调用模型，重新生成必须产生新请求 ID。

预算独立于 chat_context_mode：默认单次输入 12000、输出 2048；整轮输入 48000、输出 8192。模型和工具次数仍受 Agent 定义与请求下调上限约束。真实用量和估算用量分开标注；没有配置价格表时不把 token 数伪装成精确费用。

聊天和独立研究使用 execution_events 逐条记录事件，包含 run_id、sequence、type、data、timestamp。独立研究的旧 JSON 事件可继续读取。查询分页，研究与聊天的来源权限保持分离。会话删除清除关联事件和回答副本；只保留无原文的执行 ID 墓碑，阻止延迟重试重新生成被删除内容。

Studio 执行面板展示阶段、调用次数、输入/输出用量和剩余预算，可查原执行的最终/部分回答并请求停止。旧工作记忆面板继续承担总结、材料状态与原文回读。

## 数据迁移与回退

schema_migrations 使用独立编号。启动生命周期内完成检查、SQLite 备份、事务迁移，再公布成功的工作区 manifest；导入应用模块不执行建表和补列。较新 schema 被旧 Core 拒绝，迁移失败回滚 DDL。备份位于资料库 backups/schema-* 下。

恢复时关闭使用该资料库的 Core，保留失败现场，再用对应备份的 app.db 替换数据库并使用兼容 Core 启动。SQLite 备份不等同于向量数据库格式转换；本轮没有执行 Chroma 格式升级。

开发资料复制命令：

```powershell
python install.py migrate-workspace --source <旧目录> --destination <不存在的新目录>
```

迁移要求资料库未被 Core 占用，拒绝覆盖或重叠路径。跳过运行环境和日志；SQLite 使用备份 API 并检查完整性、记录数量，其余数据（包括向量文件）逐文件校验 SHA-256。通过后原子发布新目录，原目录不删除。失败的 .migrating-* 目录留作诊断，不能当成成功资料库。

本地开发通过忽略入 Git 的 .fue-workspace.json 选择 workspaces/development。旧 backend 留作回退副本，缺失新目录时不能静默创建空库。新环境使用 workspaces/development 或用户配置目录的 workspaces/default；旧 backend-data 继续可发现。

FUE_DATA_DIR、FUE_CORE_PORT 是新名称；APP_BACKEND_DATA_DIR、APP_BACKEND_PORT 继续兼容。Studio 使用 getCoreUrl，同时保留 getBackendUrl 兼容入口。

## 安装和界面

设置显示资料库身份、目录、Core 版本、连接状态和下次启动待切换目录。Skill 安装支持更新，保留连接配置并备份旧内容；检测按钮通过实际已安装 Skill 查询连接。

Core 构建指纹与产品版本分开：同为 2.0.0 但内置实现变化时，Studio 提示更新共享 Core；升级仍受活跃任务/Studio 租约保护。开发中旧 Core 进程缺少执行管理能力时明确提示重启，不假装已加载新代码。

卸载 Studio 时用户选择保留或删除安装器管理的 Core；资料库不随 Core 删除。写作页面和主进程写作 IPC 默认不加载，源码与数据保留。FUE_ENABLE_WRITING=1 仅供原型开发启用 IPC，不恢复正式写作入口。

## 验证入口

```powershell
npm run test:core
npm run build
```

测试结果、界面截图和安装测试放入 artifacts，测试目录不再散落根目录。Windows 实际验证和限制见对应验收记录；macOS/Linux 不据此宣称通过。
