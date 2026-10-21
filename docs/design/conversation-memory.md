# 完整聊天记忆与 MCP 翻阅

2026-10-21，本文描述 1.0.11 已实现的原文保存、问答索引与 MCP 翻阅。保存完整对话，检索单位是问答对；摘要不是记忆原本。

下一阶段的长对话架构见 [工作记忆与上下文压缩 v2](working-context.md)，实施清单见 [working-context-v2.md](../plans/working-context-v2.md)。这些能力已部分接入本地开发代码，启用步骤及差距见 [开发实现与验证](../validation/working-context-2026-10-21.md)，尚未发布到 1.0.11 安装包。

## 当前上下文能力与边界

1.0.11 与开发版默认的旧模式由 `agents/context.py` 为普通聊天和 RAG 统一构建输入：默认保留最近 5 个完整问答及当前问题，字符数除以 2 粗估 token，超过配置窗口的 90% 时拒绝。开发版可显式选择 working 模式，经 `memory/working.py` 按预算组织材料、总结与原文；不会先按旧轮数再次截取。

`Conversation.summary` 与 `chat_summary_model_id` 实际生成侧栏短标题，不是长对话工作记忆。原版 FUE 存在 `_compress_old_turns` 与压缩模型配置，但没有接入聊天调用；开发版的 `chat_compress_model_id` 仅在显式启用工作记忆且需要压缩时生效。保存并检索全部聊天，不代表模型每轮自动记得全部聊天。

## 存储与日志

SQLite `app.db` 保留现有 conversations/messages，并新增：

- `chat_events`：消息原文、角色、时间、顺序、引用及编辑/重生成事件。日志与聊天变更同事务提交。
- `chat_qa_pairs`：从日志快照投影出的完整问题与回答，关联消息、日志事件、原始时间、有效分支和索引状态。编辑/重生成产生新版本，旧版本标明 active=false。

Chroma 的 `chat_memory` 保存完整问答原文，用于关键词检索；`chat_memory_vectors_{model_id}` 保存同一个完整问答对的语义向量。检索单位不会按固定字符数切碎。关键词 collection 使用固定占位向量，不做语义查询；切换嵌入模型不会混用旧模型向量。

新提问在模型执行前持久化，失败或取消时保留不完整输出的日志，标明状态；未完成问答与完整答案可区分。历史回填只导入当前仍存在的记录，不可能恢复升级前已被删除的数据。

后台工作线程负责旧数据回填、Chroma 关键词索引及语义索引。关键词检索在向量未完成或没有嵌入模型时仍能工作；SQLite 对新写入但尚未索引的问答提供检索兜底。向量失败记录异常类型，设置页可重试，不将错误等同于没有历史。

## 设置

| 设置 | 值 / 行为 |
| --- | --- |
| memory_query_scope | disabled / 7 / 30 / 360 / all，限制查询与阅读，不影响日志保存 |
| memory_query_mode | keyword / rag；keyword 强制禁止向量查询，但仍允许搜索、时间浏览和阅读 |
| knowledge_query_mode | keyword / rag；keyword 禁用嵌入查询与重排，搜索页与 Agent 均生效 |
| memory_embed_model_id | 聊天索引模型；未指定时可使用 default_embed_model_id |

新安装默认禁止历史查询、关键词模式，用户可在聊天设置中启用。当前开发数据库按本次授权设为 all + rag，使用硅基流动嵌入模型 ID=30。语义查询及索引会将对应文本发送到所选嵌入提供商；关闭查询 RAG 不删除已经保存的向量。

范围按问题的原始发送时间计算，不按索引更新时间计算。搜索、直接读取和前后展开都执行时间检查；Agent 只能缩小访问范围。

## MCP 工具

Agent 与 MCP HTTP 入口共用 JSON-RPC `tools/call` 分发器。第一方 Agent 使用进程内客户端，避免回环 HTTP 开销；工具参数、授权范围及业务实现完全相同。

| 工具 | 能力 |
| --- | --- |
| search_chat_history | 关键词/语义/混合检索完整问答对；空 query 按时间分页浏览；可筛选会话、起止时间和更短时间范围 |
| search_knowledge_base | 在本轮所选知识库中通过 kb_ids 选择子集，返回定位信息与短预览 |
| read_context | source=chat 读取问答与相邻问答；source=knowledge 读取同文档相邻 chunk；offset/length 分页 |

聊天来源使用 `chat:pair_id`，保留问题和助手回答的区别。知识库结果返回 document_id、chunk_index、kb_id 和 CITE 标记。Agent 不接受任意 SQL 表名或任意 Chroma collection 名，能够在用户许可的来源之间选择。

外部 MCP 的可选端点为 `POST /api/mcp?kb_ids=3`：

- 设置 `APP_MCP_TOKEN` 才启用，调用需 `Authorization: Bearer ...`；缺省不开放外部访问。
- 支持 initialize、ping、tools/list、tools/call，通知返回 202。
- 使用 JSON 响应；不提供服务器主动 SSE，GET 返回 405。
- 校验 Origin 和 Accept，采用 [MCP 2025-06-18 Streamable HTTP](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) 的基本请求方式。
- 这是只读工具入口，不提供任意脚本、写入或 Skill 扩展。

## 主模型上下文保护

搜索只返回短预览。按需读取才能获得完整问答或文档上下文，单页最多 4000 字符。

整轮所有工具结果共享 12000 字符预算（包括 JSON 包装）；根据模型剩余容量再收紧，不因每次工具调用而重置。原始存储不截断；超额仅缩减本轮结果，并标明 truncated。预算不足停止进一步工具调用，保留无工具回答机会。

工具结果另预留包装和执行回执空间；在有阅读工具时，搜索预览最多占结果预算的一半，剩余部分留给原文阅读。搜索额度耗尽后向模型只提供阅读工具。执行回执列出实际调用名称和状态，Skill 明确禁止把仅检索预览说成已阅读全文。

默认采用 iterative_evidence：每轮重新构建有界证据上下文，继续允许检索/阅读，避免对推理提供商回放不完整工具消息。Agent 配置最多 10 次模型调用、20 次工具调用；设置页默认 5 次工具调用可改，搜索与阅读共享；请求可额外设更低上限。总运行截止时间 180 秒。新请求未指定上限时不会再被旧的默认 5 强行压住。

## 删除与并发

主动删除会同步清除对应原文、修订日志、问答投影和所有聊天 Chroma collection 中的索引。索引删除失败时接口不报告成功，SQLite 事务回滚，允许重试；不保留带正文的删除留底。

桌面后端单进程内通过锁保护删除与索引最终提交。嵌入网络调用在锁外执行，返回后重新检查问答是否存在，再写索引；源记录已删除时丢弃晚到结果。删除还会清空运行中的瞬时工具证据缓存，阻止源提问删除后保存晚到回答，并阻止旧后台摘要恢复被清除的内容。

跨 SQLite/Chroma 的提交不是分布式事务；若部分索引先删除而后续删除失败，源数据回滚保留，可重新构建索引。`POST /api/memory/reindex` 可从保留的问答重建；新索引状态由 `/api/memory/status` 查询。

## 本次验证

- 现有 66 条消息已回填为 66 条消息日志与 33 个完整问答对；关键词与真实语义索引均为 33/33，错误 0。
- 真实硅基流动 DeepSeek-V3.2 完成 `search_chat_history → read_context → read_context`，在人工长答案预览之外找到 ORCHID-742，并返回 PREVIOUS-MARKER / NEXT-MARKER。
- 一次额外知识库测试出现模型反复搜索、未执行 read_context 却口头声称已阅读；该次判为失败。随后收紧预览、预留阅读预算并加入实际执行回执，避免把模型文字当成工具执行证据。
- 进一步修正兼容循环的观察顺序：工具结果放在原问题之后；相同参数重复检索复用缓存并停止继续提供该搜索工具，保留阅读能力。
- 修正后真实模型重测：聊天为 `search_chat_history → read_context`，返回预览之外的三个验证标记；知识库为 `search_knowledge_base → read_context`，请求文档 46 的 chunk 183 前后各一块、分页长度 2500，返回一条文献引用，无错误，用时 73.42 秒。
- 最终 35 项自动测试通过，前端 Node/Web 类型检查及 Electron 生产构建通过。未执行桌面逐项交互验收。
- 集成测试验证完整问答单元、修订、删除、晚到嵌入、时间限制、两类相邻上下文、关闭 RAG 的关键词查询、MCP 鉴权及累计结果预算。

验证脚本：`backend/scripts/index_chat_memory.py`（会发送已授权历史到嵌入提供商）与 `backend/scripts/smoke_memory_provider.py`（仅发送人工资料到真实主模型）。
