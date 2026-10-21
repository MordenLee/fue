# 内置 Agent 运行时

当前真实调用链：

```text
ChatPage → /api/chat/{model_id}[/rag][/stream]
  → chat.router._prepare
  → AgentRegistry.resolve → build_context
  → AgentRunner.events → 已注册工具 → 模型回答
  → 现有引用后处理 → 消息保存 → 现有响应/SSE
```

## 修改行为的入口

- `resources/chat.json`：Skill 关联、工具白名单、模型/工具调用上限、超时与工具协议。
- `resources/prompts/chat.md`：基础角色说明。
- `resources/skills/knowledge-qa/skill.json`：知识库任务的资源与工具要求。
- `resources/skills/knowledge-qa/SKILL.md`：检索、证据使用、无结果和错误处理的任务说明。

这是应用实际读取的资源目录；`docs/design/agent-examples/` 只是设计时样例。资源按进程加载一次，修改后重启后端。主程序启动时校验资源，未知字段、工具、Skill 或越界路径会明确失败。

未选知识库时只加载 Chat 基础角色；选中知识库时加载 knowledge-qa。工具名称对模型为 `search_knowledge_base`，内部能力 ID 为 `knowledge.search`。知识库范围由服务端绑定，工具参数不能扩大范围。同步检索在工作线程内创建和关闭独立数据库 Session，不再复用请求 Session；取消后的晚到线程结果不写入本次引用集合。

默认 `tool_protocol=evidence_synthesis` 保留现有推理模型兼容方式：模型选择首批检索后，将工具结果以数据块加入原上下文，再由无工具模型调用生成回答。需要多轮检索时可改为 `native`，执行器使用完整工具消息协议，仍受配置预算约束；应先对所用提供商验证兼容性。`bind_tools` 明确不支持时，声明的 fallback 先以当前问题检索，再生成回答；远端 API 错误不会被静默当作无工具回答。

普通/RAG、流式/非流式共用一个执行器。每次追加结果后检查上下文，模型调用总超时和工具单次超时均有效。知识库工具失败与检索为空分别传递 `error` 和 `empty` 状态。检索任务做法已从旧 Python 工具描述和前端三处 system prompt 移出。

完成时统一用后处理正文和引用保存。流式路径保存失败会返回 ERROR，普通 Chat 也发送 JSON REPLACE 校正含换行的最终正文。现有接口及 SSE 事件兼容前端，未切换为设计中的持久化 Run API。

## 验证

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
npm --prefix frontend run typecheck
```

测试覆盖资源修改传入模型、Skill 激活、工具范围与参数、调用预算、取消、上下文溢出、模型无工具能力降级、四条真实 HTTP 路径和 SQLite 消息/引用一致性。使用假模型、隔离内存数据库，不调用用户配置的远程模型或真实向量库。

真实提供商测试需显式运行 `backend/scripts/smoke_agent_provider.py --model-id <ID> --synthetic`，使用已配置模型及人工测试文档，不写聊天记录。2026-10-21 的真实调用收到余额不足，见 [验证记录](../../docs/validation/agent-provider-smoke-2026-10-21.md)。

## 后续边界

本次是 Agent 解耦的实际接入，不是整份设计的全部实现。运行 ID 与幂等、消息修订、后台摘要版本检查、持久事件续读、完整 Token 预算和长期记忆仍需后续迁移；前端暂时仍发送历史消息。旧的历史压缩设置此前没有生效，本次没有启用自动压缩。已有引用后处理策略保持兼容，尚未升级为完整的版本化证据服务。
