# 内置 Agent / Skill 声明样例

这些文件是目标格式样例，目前没有运行时加载器。实现后复制到 `backend/agents/resources/`，保持相同目录结构。

## 路径与字段约束

- Agent 的 `prompt_file` 相对资源根目录解析。
- Skill ID 解析到资源根目录下的 `skills/{id}/skill.json`；其 `instructions_file` 相对该 Skill 目录解析。
- 所有路径解析后必须仍在资源根目录内；首期不允许资源目录外的符号链接或绝对路径。
- ID 仅允许小写字母、数字和中划线。重复 ID、未知字段、未知 schema_version 或未知策略名均为配置错误。
- `version` 是声明版本；每次运行另外记录文件实际内容哈希，避免只改正文却漏改版本时丢失追溯。
- 模型由会话选择，不把数据库 model_id 固定到随应用发布的 Agent 配置。

## 首期策略名称

以下名称是应用注册的有限枚举，不是可导入的 Python 类路径或任意表达式。增加新策略需修改程序，修改现有策略的任务说明只需编辑 Markdown。

| 名称 | 含义 |
| --- | --- |
| has_selected_knowledge_bases | 经服务端验证后，本轮所选知识库列表非空 |
| selected_knowledge_bases | 运行上下文提供的知识库范围，不能由模型扩大 |
| conversation_budgeted | 读取有效会话历史，预留输出/证据预算并构造上下文 |
| text_with_verified_references | 返回最终正文与已经验证的引用，无引用时 references 为空 |
| bounded_retrieval | 允许在全局执行预算内调用检索工具；Runner 不包含按 Skill ID 特判的循环 |
| verified_evidence_only | 模型引用必须映射到本轮或有效历史证据 |
| retrieve_then_answer | 模型不支持可靠工具协议时，先以本轮问题执行一次知识库检索，再无工具生成回答 |

无工具协议时，补充检索能力会受限；运行快照和 progress 应记录这一模式。首期只有 knowledge.search，因此该降级模式不存在工具选择歧义。未来增加其他工具时，需单独声明降级计划，不能让 Runner 猜测如何执行。

`limits` 均为正整数，必须不超过应用硬上限；实际运行值还受会话设置限制。required_tools 必须属于 Agent allowed_tools 和工具注册表。执行策略、能力检查、引用策略的冲突在加载/解析时处理，不能静默忽略。
