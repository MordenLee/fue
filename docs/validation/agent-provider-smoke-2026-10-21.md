# Agent 真实提供商验证

日期：2026-10-21。

## 已执行

- 使用开发数据库中已启用的 `siliconflow` 提供商。
- 模型：`Pro/deepseek-ai/DeepSeek-V3.2`，本地模型 ID 为 32。
- 调用路径：现有 `chat_stream` 路由 → 运行时 Agent/Skill 注册表 → ContextBuilder → AgentRunner → 真实提供商 API。
- 只发送固定连通性测试问候，不创建会话或保存消息。
- 耗时约 5.29 秒，收到真实服务响应：HTTP 402，code=30001，`Sorry, your account balance is insufficient`。

## 判断与边界

请求能够到达提供商并取得业务错误响应，但模型生成没有成功。不能据此宣称真实模型问答、工具调用或引用链路通过。

真实知识库片段出站的测试被自动审批要求明确授权，本次没有执行。改用隔离内存数据库和人工 Chroma 文档准备测试；由于第一项普通聊天已返回余额不足，脚本停止，没有继续调用知识库 Agent。

## 恢复后重跑

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe backend/scripts/smoke_agent_provider.py --model-id 32 --synthetic
```

人工资料只包含测试标识和 `ORCHID-742` 验证口令。该命令将执行真实普通聊天，以及真实模型选择工具、实际 Chroma 关键词检索和引用后处理。两项必须均通过才返回成功；不自动使用用户真实知识库。

原有 19 项假模型/隔离数据库测试和生产构建已通过；本次没有改动 Agent 实现来绕过提供商余额错误。
