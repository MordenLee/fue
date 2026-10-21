# 内置 Agent 运行时

2026-10-21 更新：已实现完整问答记忆、MCP 搜索/上下文阅读、两类检索模式与同步删除，当前行为见 [聊天记忆实现说明](../../docs/design/conversation-memory.md)。下文中的 evidence_synthesis 为可选兼容模式；当前默认 iterative_evidence 支持多轮搜索与阅读。

目标架构见 [长对话工作记忆与上下文压缩 v2](../../docs/design/working-context.md)，任务见 [实施清单](../../docs/plans/working-context-v2.md)。1.0.11 同版本更新接入材料状态、按需 summary.md、持久压缩事件及 read_memory，新模式默认关闭；具体用法和真实模型验证见 [实现与验证](../../docs/validation/working-context-2026-10-21.md)。

当前真实调用链：

```text
ChatPage → /api/chat/{model_id}[/rag][/stream]
  → chat.router._prepare
  → AgentRegistry.resolve → build_context（旧模式）/ memory.working.prepare（工作记忆）
  → AgentRunner.events → 已注册工具 → 模型回答
  → 现有引用后处理 → 消息保存 → 现有响应/SSE
```

## 修改行为的入口

- `resources/chat.json`：Skill 关联、工具白名单、模型/工具调用上限、超时与工具协议。
- `resources/prompts/chat.md`：基础角色说明。
- `resources/skills/knowledge-qa/skill.json`：知识库任务的资源与工具要求。
- `resources/skills/knowledge-qa/SKILL.md`：检索、证据使用、无结果和错误处理的任务说明。

这是应用实际读取的资源目录；`docs/design/agent-examples/` 只是设计时样例。资源按进程加载一次，修改后重启后端。主程序启动时校验资源，未知字段、工具、Skill 或越界路径会明确失败。

按资源状态加载 Skill：选中知识库时加载 knowledge-qa，历史查询启用时加载 chat-memory；存在可阅读来源时加载 context-reading。工具名称对模型为 `search_knowledge_base`，内部能力 ID 为 `knowledge.search`。知识库范围由服务端绑定，工具参数不能扩大范围。同步检索在工作线程内创建和关闭独立数据库 Session，不再复用请求 Session；取消后的晚到线程结果不写入本次引用集合。

默认 `tool_protocol=iterative_evidence`：模型选择工具后，将有界工具结果及执行回执放在原问题之后，继续允许搜索与阅读；重复请求复用缓存，并预留原文阅读预算。可选 `evidence_synthesis` 在首批检索后切换到无工具回答；可选 `native` 使用完整工具消息协议。各模式受配置预算约束，需验证所用提供商兼容性。`bind_tools` 明确不支持时，只有符合声明条件的单一检索能力可以 fallback；远端 API 错误不会被静默当作无工具回答。

普通/RAG、流式/非流式共用一个执行器。每次追加结果后检查上下文，模型调用总超时和工具单次超时均有效。知识库工具失败与检索为空分别传递 `error` 和 `empty` 状态。检索任务做法已从旧 Python 工具描述和前端三处 system prompt 移出。

完成时统一用后处理正文和引用保存。流式路径保存失败会返回 ERROR，普通 Chat 也发送 JSON REPLACE 校正含换行的最终正文。现有接口及 SSE 事件兼容前端，未切换为设计中的持久化 Run API。

## 验证

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
npm --prefix frontend run typecheck
```

测试覆盖资源修改传入模型、Skill 激活、工具范围与参数、调用预算、取消、上下文溢出、模型无工具能力降级、四条真实 HTTP 路径和 SQLite 消息/引用一致性。使用假模型、隔离内存数据库，不调用用户配置的远程模型或真实向量库。

真实提供商测试需显式运行 `backend/scripts/smoke_agent_provider.py --model-id <ID> --synthetic`，使用已配置模型及人工测试文档，不写聊天记录。早期调用余额不足，后续充值后已有成功验证；见 [验证记录](../../docs/validation/agent-provider-smoke-2026-10-21.md) 和 [记忆验证说明](../../docs/design/conversation-memory.md#本次验证)。本轮架构文档更新不执行真实模型测试。

## 后续边界

已加入聊天修订日志、问答记忆与累计检索预算。开发版为请求分配 run_id，并记录上下文事件、主模型/总结/标题及本轮检索用量；这不等于已经实现 Run 幂等、事件续读或精确 Token 计量。前端暂时仍发送当前会话历史，工作记忆模式以服务器有效问答为依据。旧模式不自动压缩；新模式需明确选择并指定压缩模型。已有文献引用后处理策略保持兼容。
