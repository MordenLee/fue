# 前端设计说明

## 1. 项目概览

基于 Electron + React + TypeScript 的桌面 RAG（检索增强生成）对话应用。前端与 Python FastAPI 后端通过 REST API + SSE 通信，提供对话管理、知识库搜索、知识库管理、模型/供应商配置和全局设置五大功能域。

**技术栈：** Electron (electron-vite) · React 19 · TypeScript · Tailwind CSS 4 · react-markdown · rehype-katex · remark-math · remark-gfm · highlight.js

---

## 2. 页面路由规划

| 路由路径 | 页面 | 说明 |
|---|---|---|
| `/` | `ChatPage` | 默认首页，聊天对话主界面 |
| `/search` | `SearchPage` | 知识库独立搜索页，手动检索与结果查看 |
| `/knowledge` | `KnowledgePage` | 知识库管理（左侧 KB 列表 + 右侧详情与文档） |
| `/providers` | `ProvidersPage` | 供应商与模型管理（左侧供应商列表 + 右侧配置与模型） |
| `/settings` | `SettingsPage` | 全局设置 |

---

## 3. 整体布局

应用采用 **导航栏 + 侧边栏 + 主内容区** 的经典三栏结构。侧边栏为通用的带文件夹功能的列表组件（`FolderListSidebar`），根据当前页面上下文切换显示内容。

```
┌──────────────────────────────────────────────────────────────────┐
│  AppShell                                                        │
│  ┌──────┬──────────────┬─────────────────────────────────────┐   │
│  │ Nav  │ FolderList   │  Main Content Area                  │   │
│  │ Bar  │ Sidebar      │                                     │   │
│  │      │              │  (根据路由渲染对应页面)               │   │
│  │ 💬   │ 📁 文件夹A    │                                     │   │
│  │ 🔍   │   ├ 对话1     │                                     │   │
│  │ 📚   │   └ 对话2     │                                     │   │
│  │ ⚙    │ 📁 文件夹B    │                                     │   │
│  │      │   └ 对话3     │                                     │   │
│  │      │ 对话4 (未归类) │                                     │   │
│  └──────┴──────────────┴─────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

对话页面在主内容区右侧增加可折叠的 **搜索结果面板**（`RetrievalPanel`），形成四栏布局：

```
┌──────┬──────────────┬───────────────────────┬──────────────┐
│ Nav  │ FolderList   │  ChatArea             │ Retrieval    │
│ Bar  │ Sidebar      │                       │ Panel        │
│      │              │  消息流                │              │
│      │  会话列表     │  ...                  │ 检索块列表    │
│      │              │  输入框               │ 块详情       │
└──────┴──────────────┴───────────────────────┴──────────────┘
```

### 3.1 NavBar（导航栏）

最左侧窄栏，固定宽度，纯图标导航：

| 图标 | 目标路由 | 说明 |
|---|---|---|
| 💬 | `/` | 对话 |
| 🔍 | `/search` | 知识库搜索 |
| 📚 | `/knowledge` | 知识库管理 |
| 🔌 | `/providers` | 供应商与模型管理 |
| ⚙ | `/settings` | 设置 |

### 3.2 FolderListSidebar（通用文件夹列表侧边栏）

这是一个**通用的带文件夹分组功能的列表组件**，在不同页面显示不同内容，但共享相同的交互模式。

**通用功能（所有场景共享）：**
- 顶部操作栏：「新建」按钮 + 搜索输入框
- 文件夹分组：支持创建/重命名/删除文件夹，拖拽列表项到文件夹
- 列表项：选中高亮、右键上下文菜单（重命名 / 移入文件夹 / 删除）
- 折叠/展开文件夹
- 未归入文件夹的项目显示在底部

**各页面的侧边栏内容：**

| 页面 | 列表内容 | 新建操作 | 搜索范围 |
|---|---|---|---|
| 对话页 | 会话列表（按 `updated_at` 降序） | 新建对话 | 会话标题+摘要+消息内容 |
| 搜索页 | 搜索历史记录列表 | 新建搜索 | 历史搜索记录 |
| 知识库管理页 | 知识库列表 | 新建知识库 | 知识库名称+描述 |
| 供应商管理页 | 供应商列表 | 添加供应商 | 供应商名称 |

**Props 接口设计：**

```typescript
interface FolderListSidebarProps<T> {
  items: T[]                                // 列表数据
  folders: Folder[]                          // 文件夹列表
  selectedId: string | number | null         // 当前选中项
  onSelect: (item: T) => void               // 选中回调
  onCreateNew: () => void                    // 新建按钮回调
  onSearch: (query: string) => void          // 搜索回调
  renderItem: (item: T) => ReactNode         // 自定义列表项渲染
  createLabel: string                        // 新建按钮文案（如"新建对话"）
  searchPlaceholder: string                  // 搜索占位符
  contextMenuActions: ContextMenuAction<T>[] // 右键菜单项
}
```

---

## 4. 页面设计

### 4.1 ChatPage — 对话页面

应用的核心页面，采用 **侧边栏 + 聊天区 + 检索面板** 三栏布局：

```
┌──────────────┬──────────────────────────────────┬──────────────────┐
│ FolderList   │  ChatHeader                      │ RetrievalPanel   │
│ Sidebar      │  模型选择 | KB绑定 | 引用格式     │ (可折叠)         │
│              ├──────────────────────────────────┤                  │
│ [+ 新建对话] │                                  │ 搜索轮次 #1      │
│ [🔍 搜索...] │  MessageList                     │ ┌──────────────┐ │
│              │  ┌────────────────────────┐      │ │ 📄 paper.pdf  │ │
│ 📁 课程项目   │  │ 👤 用户消息             │      │ │ 段落 3        │ │
│   ├ 对话1    │  │ 🤖 助手消息 [1][2]      │      │ │ 分数: 0.92   │ │
│   └ 对话2    │  │ 👤 追问                 │      │ │ "文本预览..." │ │
│ 📁 论文阅读   │  │ 🤖 回复 [3]             │      │ └──────────────┘ │
│   └ 对话3    │  └────────────────────────┘      │ ┌──────────────┐ │
│ 对话4        │                                  │ │ 📄 notes.md   │ │
│              ├──────────────────────────────────┤ │ 段落 7        │ │
│              │  ChatInput                       │ │ 分数: 0.85   │ │
│              │  [输入框...            ] [发送]   │ │ "文本预览..." │ │
│              │                                  │ └──────────────┘ │
└──────────────┴──────────────────────────────────┴──────────────────┘
```

**关键交互：**

1. **普通对话**：`POST /api/chat/{model_id}/stream`（SSE 流式）
2. **RAG 对话**：绑定知识库后自动切换至 `POST /api/chat/{model_id}/rag/stream`
3. **流式消息渲染**：逐 token 追加显示，实时 Markdown + LaTeX 渲染
4. **引用标注**：解析 `[CITE-N]` 标记，流结束后通过 `[CITATIONS]` 事件中的 `cite_map` 替换为 `[N]`，点击角标弹出引用来源详情
5. **检索结果面板**：RAG 对话时，每次 `[TOOL_CALL]` 触发搜索后，将返回的文档块实时展示在右侧面板，用户可点击查看完整块内容
6. **自动摘要**：流结束后若收到 `[SUMMARY]` 事件，更新会话列表中的摘要显示
7. **新建对话**：`POST /api/conversations` → 创建后自动聚焦
8. **加载历史**：选中会话后 `GET /api/conversations/{id}` 获取完整消息列表

**SSE 事件处理流程：**

```
fetch POST 连接
  ├─ data: {token}          → 追加到当前助手消息
  ├─ data: [TOOL_CALL] json → 显示"正在搜索知识库…" + 将搜索参数记录到检索面板
  ├─ data: [CITATIONS] json → 解析引用映射、替换 CITE 标记、更新检索面板块列表
  ├─ data: [SUMMARY] json   → 更新会话摘要
  ├─ data: [ERROR] msg      → 显示错误 Toast
  └─ data: [DONE]           → 标记流式结束，保存消息
```

**RetrievalPanel（检索结果面板）：**

右侧面板展示当前对话中 RAG 检索返回的所有文档块：

- 默认折叠，RAG 对话时自动展开
- 按搜索轮次分组显示（第1轮、第2轮…）
- 每个检索块卡片包含：来源文件名、段落序号、相关度分数、内容文本预览
- 点击块卡片展开查看完整文本内容
- 点击消息中的引用角标 `[N]` 时，面板自动滚动到对应的块并高亮
- 可手动折叠/展开面板以获得更大的聊天区域

---

### 4.2 SearchPage — 知识库独立搜索页

独立于对话的手动搜索模块，让用户直接对知识库进行检索并查看原始结果。

```
┌──────────────┬────────────────────────────────────────────────────┐
│ FolderList   │  SearchHeader                                      │
│ Sidebar      │  知识库选择 | 搜索类型 | Top K | Rerank开关         │
│              ├────────────────────────────────────────────────────┤
│ [+ 新建搜索] │  SearchBar                                         │
│ [🔍 搜索...] │  [输入查询...                           ] [搜索]   │
│              ├────────────────────────────────────────────────────┤
│ 📁 论文检索   │  SearchResultList                                  │
│   ├ "RAG综述" │                                                    │
│   └ "向量数据" │  ┌─ 结果 1 ──────────────────────────────────────┐ │
│ "attention"  │  │ 📄 paper.pdf · 段落 3 · 分数 0.95              │ │
│              │  │                                                │ │
│              │  │ 检索到的文本内容完整显示在这里，支持             │ │
│              │  │ Markdown 渲染和 LaTeX 公式渲染...               │ │
│              │  │                                                │ │
│              │  │ [查看引用信息]  [定位到知识库]                    │ │
│              │  └────────────────────────────────────────────────┘ │
│              │  ┌─ 结果 2 ──────────────────────────────────────┐ │
│              │  │ 📄 notes.md · 段落 7 · 分数 0.82              │ │
│              │  │ ...                                           │ │
│              │  └────────────────────────────────────────────────┘ │
└──────────────┴────────────────────────────────────────────────────┘
```

**核心功能：**

1. **知识库选择**：单选或多选要搜索的知识库（复用 `KBSelector`）
2. **搜索类型切换**：语义搜索（semantic）/ 关键词搜索（keyword）
3. **参数配置**：Top K 数量、是否启用 Rerank
4. **结果展示**：每个结果块完整显示文本内容，支持 Markdown + LaTeX 渲染
5. **搜索历史**：左侧侧边栏保留历史搜索记录（查询词 + 时间），可以文件夹分组管理
6. **结果交互**：
   - 查看该文档块的引用信息（`GET .../citation/formatted?style=apa`）
   - 跳转到知识库管理页并选中对应知识库

**API 调用：**
- 搜索：`GET /api/knowledge-bases/{kbId}/search?q=...&search_type=semantic&top_k=5&rerank=true`
- 可跨多个知识库并行搜索，结果合并后按分数排序显示

---

### 4.3 KnowledgePage — 知识库管理

采用 **侧边栏 + 内容区** 的左右布局，左侧为知识库列表（支持文件夹分组），右侧显示当前选中知识库的详细信息和文档管理。不使用独立的详情页路由。

```
┌──────────────┬────────────────────────────────────────────────────┐
│ FolderList   │  KBInfoPanel                                      │
│ Sidebar      │  ┌──────────────────────────────────────────────┐  │
│              │  │  名称: 机器学习论文集           [编辑] [导出]  │  │
│ [+ 新建KB]   │  │  描述: 包含深度学习相关的关键论文...           │  │
│ [🔍 搜索...] │  │  Embedding: text-embedding-3-large             │  │
│              │  │  Rerank: Qwen3-Reranker-8B                     │  │
│ 📁 课程资料   │  │  分片: 500字符 / 50重叠 | 文档数: 12           │  │
│   ├ 知识库A  │  └──────────────────────────────────────────────┘  │
│   └ 知识库B  ├────────────────────────────────────────────────────┤
│ 📁 论文库    │  DocumentTable                                     │
│   └ 知识库C  │  [+ 添加文档]  [搜索文档名...]                     │
│ 知识库D (选中)│  ┌──────────────────────────────────────────────┐ │
│              │  │  文件名          类型  大小   分块  状态  操作  │ │
│              │  ├──────────────────────────────────────────────┤ │
│              │  │  📄 attention.pdf pdf  2.3MB  32   ✅    ⋮   │ │
│              │  │  📄 bert.pdf      pdf  1.8MB  28   ✅    ⋮   │ │
│              │  │  📄 notes.md      md   45KB   5    ✅    ⋮   │ │
│              │  │  📄 draft.docx    docx 890KB  --   🔄    ⋮   │ │
│              │  └──────────────────────────────────────────────┘ │
│              │                                                    │
│              │  展开的文档详情（点击某行展开）                       │
│              │  ┌──────────────────────────────────────────────┐ │
│              │  │  摘要: Attention Is All You Need 提出了...    │ │
│              │  │  引用信息:                                    │ │
│              │  │    类型: article | 作者: Vaswani et al.       │ │
│              │  │    年份: 2017 | DOI: 10.48550/...             │ │
│              │  │    [编辑引用]  [格式化引用: APA ▼]             │ │
│              │  │  操作: [重新索引] [删除文档]                   │ │
│              │  └──────────────────────────────────────────────┘ │
└──────────────┴────────────────────────────────────────────────────┘
```

**左侧 — FolderListSidebar：**
- 复用通用 `FolderListSidebar` 组件，列表内容为知识库
- 支持文件夹分组、搜索过滤、右键上下文菜单（重命名 / 移入文件夹 / 删除）
- 顶部「+ 新建知识库」按钮 → 弹窗表单（名称、描述、Embedding 模型、分片参数、Rerank 模型）
- 选中某个知识库后，右侧内容区加载其详情

**右侧上部 — KBInfoPanel（知识库信息区）：**
- 显示 KB 名称、描述、Embedding 模型、Rerank 模型、分片参数、文档总数、创建/更新时间
- 「编辑」按钮 → 弹窗编辑（复用 `FormModal`）
- 「导出」按钮 → `GET /api/knowledge-bases/{id}/export` 下载 JSON

**右侧下部 — DocumentTable（文档管理区）：**
- 表格形式展示文档列表，列：文件名、类型、大小、分块数、状态、操作菜单
- 「添加文档」→ Electron 文件选择对话框 → `POST .../documents/batch`
- 状态实时轮询（pending/processing → indexed/failed）
- 点击某行展开详情面板：查看摘要、引用信息、格式化引用
- 操作菜单（⋮）：重新索引、编辑引用、删除

**未选中状态：**
- 右侧显示 `EmptyState` 占位：提示用户从左侧选择一个知识库，或新建知识库

**API 调用：**
- 列表：`GET /api/knowledge-bases`
- 新建：`POST /api/knowledge-bases`
- 编辑：`PUT /api/knowledge-bases/{id}`
- 删除：`DELETE /api/knowledge-bases/{id}`（需确认）
- 导出：`GET /api/knowledge-bases/{id}/export`（下载 JSON 文件）
- 导入：`POST /api/knowledge-bases/import`（multipart/form-data）
- 文档列表：`GET /api/knowledge-bases/{kbId}/documents`
- 添加文档：`POST /api/knowledge-bases/{kbId}/documents`（单个）或 `/batch`（批量）
- 重新索引：`POST /api/knowledge-bases/{kbId}/documents/{docId}/reindex`
- 删除文档：`DELETE /api/knowledge-bases/{kbId}/documents/{docId}`
- 引用 CRUD：`GET/PUT/PATCH/DELETE /api/knowledge-bases/{kbId}/documents/{docId}/citation`
- 格式化引用：`GET .../citation/formatted?style=apa`

**文档状态显示：**

| 状态 | 显示 | 样式 |
|---|---|---|
| `pending` | 等待中 | 灰色 |
| `processing` | 处理中 | 蓝色 + 旋转动画 |
| `indexed` | 已索引 | 绿色 |
| `failed` | 失败 | 红色 + 悬停显示 `error_message` |

---

### 4.4 ProvidersPage — 供应商与模型管理

采用与 KnowledgePage 一致的 **侧边栏 + 内容区** 左右布局。左侧为供应商列表，右侧显示当前选中供应商的 API 配置和模型管理。

```
┌──────────────┬────────────────────────────────────────────────────┐
│ Provider     │  ProviderConfig                                    │
│ List         │  ┌──────────────────────────────────────────────┐  │
│ Sidebar      │  │  OpenAI                     [启用 ✓] [删除]  │  │
│              │  │                                              │  │
│ [+ 添加供应商]│  │  接口类型: openai                             │  │
│ [🔍 搜索...] │  │  API Key:  [sk-***...               ] [显示] │  │
│              │  │  API 地址: [https://api.openai.com   ]       │  │
│  OpenAI  ✓   │  │  描述:     [官方 OpenAI 服务         ]       │  │
│  Anthropic ✓ │  │                                              │  │
│  Ollama  ✓   │  │            [测试连通性]  [保存]               │  │
│  DeepSeek    │  └──────────────────────────────────────────────┘  │
│  Moonshot    ├────────────────────────────────────────────────────┤
│              │  ModelList                                         │
│              │  [+ 添加模型]                                      │
│              │                                                    │
│              │  ── GPT-4 系列 ──                                  │
│              │  ┌──────────────────────────────────────────────┐ │
│              │  │  gpt-4o          chat  vision  ✓默认 [启用] ⋮│ │
│              │  │  gpt-4o-mini     chat         [启用] ⋮       │ │
│              │  └──────────────────────────────────────────────┘ │
│              │  ── Embedding 系列 ──                              │
│              │  ┌──────────────────────────────────────────────┐ │
│              │  │  text-embedding-3-large  embedding  [启用] ⋮ │ │
│              │  │  text-embedding-3-small  embedding  [启用] ⋮ │ │
│              │  └──────────────────────────────────────────────┘ │
└──────────────┴────────────────────────────────────────────────────┘
```

**左侧 — 供应商列表侧边栏：**
- 复用 `FolderListSidebar` 组件（无文件夹功能，仅列表 + 搜索）
- 每个供应商项显示：名称 + 启用状态指示（✓ 绿点 / 灰点）
- 顶部「+ 添加供应商」按钮 → 弹窗表单
- 选中某个供应商后，右侧加载其配置和模型列表

**右侧上部 — ProviderConfig（供应商配置区）：**
- 显示供应商名称、接口类型、启用/禁用开关
- 可编辑字段：API Key（密码模式 + 显示/隐藏切换）、API 地址、描述
- 「测试连通性」按钮 → `POST /api/providers/{id}/test` → 显示结果 Toast
- 「保存」按钮 → `PUT /api/providers/{id}`
- 「删除」按钮 → 确认弹窗（级联删除所有模型）

**右侧下部 — ModelList（模型列表区）：**
- 按 `series` 字段分组显示模型（如 GPT-4 系列、Embedding 系列）
- 每个模型行显示：`api_name`、`model_type` 标签、capabilities 徽标（vision / reasoning / function_calling）、是否默认、启用开关
- 操作菜单（⋮）：编辑模型、设为默认、删除
- 「添加模型」按钮 → 弹窗表单（选择模型类型、填写 api_name、display_name、series 等）

**未选中状态：**
- 右侧显示 `EmptyState` 占位：提示用户从左侧选择一个供应商

**供应商 API 调用：**
- 列表：`GET /api/providers`
- 新建：`POST /api/providers`
- 编辑：`PUT /api/providers/{id}`
- 启用/禁用：`PATCH /api/providers/{id}/enabled?enabled=true/false`
- 测试连通性：`POST /api/providers/{id}/test`
- 删除：`DELETE /api/providers/{id}`（级联删除所有模型，需确认）

**模型 API 调用：**
- 列表：`GET /api/models?provider_id={id}`
- 新建：`POST /api/models`
- 编辑：`PUT /api/models/{id}`
- 启用/禁用：`PATCH /api/models/{id}/enabled?enabled=true/false`
- 删除：`DELETE /api/models/{id}`

**供应商接口类型（`interface_type`）：**

| 类型 | 说明 |
|---|---|
| `openai` | OpenAI 官方 |
| `anthropic` | Anthropic Claude |
| `google` | Google Gemini |
| `ollama` | Ollama 本地 |
| `openai_compatible` | OpenAI 兼容接口（DeepSeek / Moonshot 等） |
| `cohere` | Cohere |
| `jina` | Jina AI |

---

### 4.5 SettingsPage — 全局设置

```
┌───────────────────────────────────────┐
│  设置                    [恢复默认]    │
├───────────────────────────────────────┤
│  通用设置                              │
│  ├─ 界面语言        [中文 ▼]          │
│                                       │
│  RAG 设置                             │
│  ├─ 默认检索数量    [5]               │
│                                       │
│  文档解析                              │
│  ├─ PDF 解析引擎    [pdfplumber ▼]    │
│  ├─ DOCX 解析引擎   [python-docx ▼]  │
│  ├─ 索引并行数      [4]               │
│                                       │
│  辅助模型                              │
│  ├─ 文档清洗模型    [选择模型 ▼]      │
│  ├─ 对话摘要模型    [选择模型 ▼]      │
│  ├─ 引用抽取模型    [选择模型 ▼]      │
│                                       │
│            [保存]                      │
└───────────────────────────────────────┘
```

**API 调用：**
- 获取：`GET /api/settings`
- 保存：`PUT /api/settings`
- 恢复默认：`POST /api/settings/reset`
- 辅助模型列表：`GET /api/aux-models`
- 设置辅助模型：`PUT /api/aux-models/{role}`
- 清除辅助模型：`DELETE /api/aux-models/{role}`

---

## 5. 可复用组件设计

### 5.1 基础 UI 组件（无业务逻辑）

这些组件只接受 props，不依赖任何全局状态，可在全应用范围内复用。

#### 5.1.1 表单控件

| 组件 | 用途 | 使用场景 |
|---|---|---|
| `Button` | 统一按钮样式（primary / secondary / danger / ghost / icon） | 全局 |
| `IconButton` | 纯图标按钮（圆形/方形，常配合 Tooltip 使用） | 工具栏、操作列 |
| `Input` | 文本输入框（支持 label、error、前缀/后缀图标、clearable） | 全局表单 |
| `Textarea` | 多行文本输入（支持自动调整高度） | 聊天输入、描述编辑 |
| `Select` | 下拉选择器（单选，支持分组选项） | 模型选择、语言切换等 |
| `MultiSelect` | 多选下拉（带标签展示已选项） | 知识库多选 |
| `Switch` | 开关切换 | 启用/禁用、Rerank 开关 |
| `NumberInput` | 数值输入框（带步进按钮、min/max 约束） | Top K、分片参数 |
| `FormField` | 表单字段容器（统一 label + 输入控件 + 错误提示 + 描述文字的布局） | 所有表单页面 |

#### 5.1.2 反馈与提示

| 组件 | 用途 | 使用场景 |
|---|---|---|
| `Toast` | 轻量操作反馈（自动消失，success / error / warning / info） | 全局，通过 `useToast()` 触发 |
| `Tooltip` | 悬停提示气泡（支持上/下/左/右方向） | 图标按钮说明、截断文本完整显示、状态详情 |
| `Popover` | 点击触发的悬浮面板（比 Tooltip 更重，支持交互内容） | 引用详情卡片、筛选面板 |
| `Badge` | 数字/文本标签（小圆点、计数徽标） | 未读数、文档数 |
| `StatusTag` | 状态标签（预定义颜色：success / warning / error / info / neutral） | 文档状态、启用状态 |
| `Spinner` | 加载旋转指示器（可指定尺寸） | 按钮加载态、内容加载 |
| `Skeleton` | 骨架屏占位块（支持行/卡片/头像等形状） | 列表加载、卡片加载 |
| `ProgressBar` | 进度条（不确定/确定两种模式） | 文档索引进度 |

#### 5.1.3 弹窗与覆盖层

| 组件 | 用途 | 使用场景 |
|---|---|---|
| `Modal` | 基础模态弹窗容器（背景遮罩 + 居中内容 + 关闭按钮） | 所有弹窗的基础 |
| `ConfirmDialog` | 确认操作弹窗（标题 + 描述 + 确认/取消按钮，支持 danger 变体） | 删除确认、危险操作确认 |
| `FormModal` | 表单编辑弹窗（Modal + 表单内容 + 提交/取消按钮 + 加载态） | 新建/编辑知识库、供应商、模型、引用信息 |
| `Drawer` | 侧滑抽屉面板（从右侧/左侧滑出） | 文档详情、检索面板 |

#### 5.1.4 布局与容器

| 组件 | 用途 | 使用场景 |
|---|---|---|
| `Card` | 卡片容器（边框 + 内边距 + 可选标题栏） | 搜索结果卡片、信息面板 |
| `Tabs` | 标签页切换 | 设置页分组、文档详情切换 |
| `Divider` | 分割线（水平/垂直） | 表单分组、内容分隔 |
| `EmptyState` | 空列表占位（图标 + 标题 + 描述 + 操作按钮） | 空会话列表、空知识库、空搜索结果 |
| `ResizablePanel` | 可拖拽调整宽度的面板（用于侧边栏和检索面板） | 侧边栏、检索面板 |
| `ScrollArea` | 自定义滚动条容器 | 消息列表、文档列表 |

#### 5.1.5 交互与菜单

| 组件 | 用途 | 使用场景 |
|---|---|---|
| `ContextMenu` | 右键上下文菜单 | 会话右键（重命名/删除/移入文件夹） |
| `DropdownMenu` | 点击触发的下拉菜单 | 文档操作菜单（⋮ 按钮） |
| `SearchInput` | 搜索输入框（带防抖、清除按钮、搜索图标） | 侧边栏搜索、文档名筛选 |

### 5.2 通用业务组件

这些组件封装可复用的业务级 UI 模式，跨多个功能域共享。

| 组件 | 用途 | 使用页面 |
|---|---|---|
| `FolderListSidebar` | 通用带文件夹分组的列表侧边栏（见 3.2 节详细设计） | 对话页、搜索页、知识库管理页 |
| `ModelSelector` | 选择 AI 模型（支持按类型过滤：chat / embedding / reranking，显示供应商分组） | 对话页、知识库创建、设置页（辅助模型） |
| `KBSelector` | 选择知识库（多选，展示名称 + 文档数） | 对话页 Header、搜索页、新建会话弹窗 |
| `CitationStyleSelect` | 引用格式选择器（APA / MLA / Chicago / GB/T 7714） | 对话页 Header、会话设置 |
| `MarkdownLatexRenderer` | Markdown + LaTeX 公式渲染器（见第 6 节详细设计） | 聊天消息、搜索结果、文档摘要 |
| `CitationRenderer` | 解析消息中的 `[N]` 引用角标，渲染为可点击的上标标注 | 聊天消息（RAG） |
| `CitationPopover` | 点击引用角标后的悬浮卡片（来源文件名 + 段落号 + 格式化引用文本） | 聊天消息 |
| `ChunkCard` | 检索到的文档块卡片（来源文件、段落号、分数、内容预览、展开查看完整内容） | 检索面板、搜索结果页 |
| `CitationForm` | 引用信息编辑表单（类型 / 标题 / 作者 / 年份等全部字段，用于 FormModal 内） | 知识库文档详情 |
| `StatusBadge` | 统一状态标签（pending / processing / indexed / failed，映射颜色和 i18n 文本） | 文档列表 |
| `ProviderBadge` | 供应商类型图标 + 名称 | 供应商列表、模型选择器 |

### 5.3 组件层次依赖关系

```
页面层 (pages/)
  └── 通用业务组件 (components/shared/, components/{domain}/)
        └── 基础 UI 组件 (components/ui/)
              └── 无外部依赖（仅 React + Tailwind）
```

**原则：**
- **基础 UI 组件** → 零业务逻辑，纯 props 驱动，任何项目可复用
- **通用业务组件** → 知道业务含义（如"知识库""模型"），可调用 hooks 获取数据，但不直接调用 API
- **页面层** → 组装组件、管理页面级状态、调用 service 层、处理路由参数

---

## 6. Markdown + LaTeX 渲染方案

### 6.1 功能需求

所有来自 LLM 和知识库的文本内容需要支持：

1. **Markdown 渲染**：标题、列表、表格、代码块（带语法高亮）、引用块、链接、图片、粗/斜体、分割线
2. **LaTeX 数学公式渲染**：
   - 行内公式：`$E = mc^2$` → $E = mc^2$
   - 块级公式：`$$\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}$$`
3. **GFM 扩展**：删除线、任务列表、自动链接、表格
4. **代码高亮**：多语言语法高亮（Python、JavaScript、SQL、JSON 等）
5. **流式渲染**：在 SSE 流式对话中，token 逐字追加时也能正确实时渲染（避免闪烁和布局抖动）

### 6.2 技术方案

基于 `react-markdown` + 插件链：

```
react-markdown
  ├── remark-math       → 解析 $...$ 和 $$...$$ 语法为 math AST 节点
  ├── remark-gfm        → 支持 GFM 扩展（表格、删除线、任务列表）
  ├── rehype-katex       → 将 math 节点渲染为 KaTeX HTML
  └── rehype-highlight   → 代码块语法高亮（或使用 highlight.js 自定义组件）
```

### 6.3 MarkdownLatexRenderer 组件设计

```typescript
interface MarkdownLatexRendererProps {
  content: string                    // Markdown + LaTeX 原始文本
  isStreaming?: boolean              // 是否正在流式追加（影响渲染策略）
  className?: string                 // 自定义容器样式
  components?: Record<string, FC>    // 覆盖特定元素的渲染组件（如 a、code）
}
```

**使用场景：**

| 场景 | `isStreaming` | 说明 |
|---|---|---|
| 聊天消息（助手回复流式追加中） | `true` | 逐 token 追加，需要高频 re-render 但避免闪烁 |
| 聊天消息（历史/完成的消息） | `false` | 一次性渲染完整内容 |
| 搜索结果块的文本内容 | `false` | 完整渲染 |
| 文档摘要 | `false` | 完整渲染 |

**流式渲染优化策略：**
- 使用 `useMemo` 或 throttle（~50ms）避免每个 token 触发完整 re-parse
- 未闭合的 LaTeX 分隔符（如 `$` 已出现但还没收到闭合 `$`）暂时作为纯文本显示，闭合后再渲染为公式
- 未闭合的代码围栏（` ``` `）同理

### 6.4 样式要求

- LaTeX 公式字体与正文字体协调（KaTeX 默认字体即可）
- 代码块：深色背景、等宽字体、左上角显示语言标签、右上角复制按钮
- 表格：边框、交替行背景色
- 引用块（`>`）：左侧边框高亮
- 行内代码：浅色背景 + 圆角

---

## 7. 服务层设计（services/）

按后端模块一一对应拆分，每个文件封装一组相关 API 调用。

```
services/
  ├── api.ts              # 基础请求封装（fetch wrapper、错误处理、BASE_URL）
  ├── chat.ts             # 对话相关 API（含 SSE 流式处理）
  ├── conversations.ts    # 会话 CRUD + 消息管理 + 搜索
  ├── knowledge.ts        # 知识库 CRUD + 搜索 + 导入导出
  ├── documents.ts        # 文档 CRUD + 重索引
  ├── citations.ts        # 引用 CRUD + 格式化
  ├── providers.ts        # 供应商 CRUD + 连通性测试
  ├── models.ts           # 模型 CRUD + 默认模型
  ├── settings.ts         # 设置读写 + 重置
  └── auxModels.ts        # 辅助模型配置
```

### 7.1 API 基础封装（api.ts）

```typescript
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

// 通用 JSON 请求
async function request<T>(path: string, init?: RequestInit): Promise<T>

// SSE 流式请求（返回 ReadableStream 回调）
function streamRequest(path: string, body: object, onEvent: (event: SSEEvent) => void): AbortController
```

### 7.2 各服务文件职责

**chat.ts**
```
sendMessage(modelId, messages, conversationId?)    → ChatResponse
streamMessage(modelId, messages, conversationId?)  → SSE stream
sendRAG(modelId, messages, kbIds, opts?)           → RAGChatResponse
streamRAG(modelId, messages, kbIds, opts?)         → SSE stream (含 TOOL_CALL / CITATIONS)
```

**conversations.ts**
```
list(skip?, limit?)              → ConversationOut[]
search(query)                    → ConversationSearchResult[]
getById(id)                      → ConversationDetail
create(data)                     → ConversationOut
update(id, data)                 → ConversationOut
remove(id)                       → void
removeAll()                      → void
getMessages(convId)              → MessageOut[]
appendMessages(convId, msgs)     → MessageOut[]
removeMessage(convId, msgId)     → void
clearMessages(convId)            → void
```

**knowledge.ts**
```
list(skip?, limit?)              → KnowledgeBaseOut[]
getById(id)                      → KnowledgeBaseOut
create(data)                     → KnowledgeBaseOut
update(id, data)                 → KnowledgeBaseOut
remove(id)                       → void
exportKB(id)                     → Blob (下载)
importKB(file, embedModelId, name?) → KBImportResult
search(kbId, query, opts?)       → SearchResult[]
```

**documents.ts**
```
list(kbId, skip?, limit?)        → DocumentFileOut[]
getById(kbId, docId)             → DocumentFileOut
add(kbId, path)                  → DocumentFileOut
addBatch(kbId, paths)            → DocumentFileOut[]
reindex(kbId, docId)             → DocumentFileOut
remove(kbId, docId)              → void
```

**citations.ts**
```
get(kbId, docId)                 → CitationOut
upsert(kbId, docId, data)       → CitationOut
patch(kbId, docId, data)         → CitationOut
remove(kbId, docId)              → void
getFormatted(kbId, docId, style) → { style, text }
```

**providers.ts**
```
list()                           → ProviderOut[]
getById(id)                      → ProviderOut
create(data)                     → ProviderOut
update(id, data)                 → ProviderOut
setEnabled(id, enabled)          → ProviderOut
remove(id)                       → void
test(id, modelId?)               → { success, message, latency_ms }
```

**models.ts**
```
list(filters?)                   → AIModelOut[]
getDefaults()                    → { chat, embedding, reranking }
getById(id)                      → AIModelOut
create(data)                     → AIModelOut
update(id, data)                 → AIModelOut
setEnabled(id, enabled)          → AIModelOut
remove(id)                       → void
```

**settings.ts**
```
get()                            → SettingsOut
update(data)                     → SettingsOut
reset()                          → SettingsOut
```

**auxModels.ts**
```
list()                           → AuxModelOut[]
assign(role, modelId)            → AuxModelOut
clear(role)                      → void
```

---

## 8. 自定义 Hooks 设计

封装可复用的业务逻辑，使组件保持精简。

| Hook | 职责 | 使用场景 |
|---|---|---|
| `useStreamingChat()` | 管理 SSE 连接、token 累积、检索块收集、引用解析、错误处理、中止控制 | ChatPage |
| `useConversations()` | 会话列表加载、分页、搜索、CRUD 刷新 | ChatPage 侧边栏 |
| `useMessages(convId)` | 加载/追加/删除消息 | ChatPage |
| `useKnowledgeBases()` | 知识库列表加载与 CRUD | KnowledgePage 侧边栏, SearchPage |
| `useDocuments(kbId)` | 文档列表加载、状态轮询（处理中 → 已索引） | KnowledgePage |
| `useKBSearch(kbIds)` | 知识库搜索（支持多 KB 并行搜索、结果合并排序） | SearchPage, KnowledgePage |
| `useProviders()` | 供应商列表与模型列表加载 | ProvidersPage |
| `useSettings()` | 设置读写、重置 | SettingsPage |
| `useToast()` | Toast 消息队列管理 | 全局 |
| `useFolders()` | 文件夹 CRUD + 拖拽排序（前端本地存储） | FolderListSidebar |

### 8.1 核心 Hook：useStreamingChat

这是最复杂的 hook，负责管理 SSE 流式对话的完整生命周期：

```typescript
interface UseStreamingChatReturn {
  // 状态
  isStreaming: boolean
  currentResponse: string          // 实时累积的助手回复
  toolCalls: ToolCallEvent[]       // RAG 搜索工具调用记录
  retrievedChunks: ChunkInfo[]     // 当前轮次所有检索到的块（用于 RetrievalPanel）
  citations: CitationMap | null    // 引用映射（流结束后填充）
  error: string | null

  // 操作
  send(messages, modelId, options?): void
  abort(): void                    // 中止当前流
}
```

### 8.2 文档状态轮询：useDocuments

文档添加后状态为 `pending`，需要轮询更新：

```
添加文档 → pending → (轮询 2s 间隔) → processing → indexed / failed → 停止轮询
```

### 8.3 知识库搜索 Hook：useKBSearch

```typescript
interface UseKBSearchReturn {
  results: SearchResult[]          // 合并排序后的搜索结果
  isSearching: boolean
  error: string | null
  search(query: string, opts?: SearchOptions): void
  clear(): void
}

interface SearchOptions {
  kbIds: number[]
  searchType: 'semantic' | 'keyword'
  topK: number
  rerank: boolean
}
```

---

## 9. 状态管理策略

采用 **React Context + useReducer** 管理少量全局状态，大部分状态保持在组件/页面本地。

### 9.1 全局状态（Context）

| Context | 数据 | 说明 |
|---|---|---|
| `SettingsContext` | `{ language, ... }` | 界面语言等全局设置，影响 i18n |
| `ToastContext` | `Toast[]` | 全局消息提示队列 |

### 9.2 页面级状态（组件内部）

| 页面 | 状态 |
|---|---|
| `ChatPage` | 当前会话 ID、消息列表、流式响应缓冲、已选模型、已选知识库、检索面板块列表、面板展开/折叠 |
| `SearchPage` | 搜索历史列表、当前搜索参数、搜索结果列表、已选知识库 |
| `KnowledgePage` | 知识库列表、文件夹列表、选中的知识库 ID、KB 详情、文档列表、展开的文档 ID、新建/编辑弹窗开关、引用编辑弹窗 |
| `ProvidersPage` | 供应商列表、选中的供应商 ID、供应商配置表单、模型列表、新建/编辑弹窗开关 |
| `SettingsPage` | 设置表单值 |

### 9.3 本地持久化

以下数据使用 `localStorage` 或 Electron Store 持久化（不依赖后端）：

| 数据 | 存储位置 | 说明 |
|---|---|---|
| 文件夹结构与分组关系 | `localStorage` | 会话/知识库/搜索记录的文件夹归属映射 |
| 搜索历史记录 | `localStorage` | 搜索页的历史查询（查询词 + 参数 + 时间戳） |
| 检索面板宽度/折叠状态 | `localStorage` | 用户偏好 |
| 侧边栏宽度 | `localStorage` | 用户偏好 |

**原则**：不使用重量级全局状态管理库（Redux / Zustand），因为跨页面共享数据较少，Context 足以覆盖。

---

## 10. 前端目录结构

```
src/renderer/src/
├── main.tsx                    # 入口：挂载 React、全局 Provider
├── App.tsx                     # 路由定义、AppShell 布局
├── assets/
│   ├── base.css
│   └── main.css
├── components/
│   ├── ui/                     # 基础 UI 组件（无业务逻辑）
│   │   ├── Button.tsx
│   │   ├── IconButton.tsx
│   │   ├── Input.tsx
│   │   ├── NumberInput.tsx
│   │   ├── Textarea.tsx
│   │   ├── Select.tsx
│   │   ├── MultiSelect.tsx
│   │   ├── Switch.tsx
│   │   ├── FormField.tsx
│   │   ├── Modal.tsx
│   │   ├── ConfirmDialog.tsx
│   │   ├── FormModal.tsx
│   │   ├── Drawer.tsx
│   │   ├── Toast.tsx
│   │   ├── Tooltip.tsx
│   │   ├── Popover.tsx
│   │   ├── Badge.tsx
│   │   ├── StatusTag.tsx
│   │   ├── Spinner.tsx
│   │   ├── Skeleton.tsx
│   │   ├── ProgressBar.tsx
│   │   ├── EmptyState.tsx
│   │   ├── Card.tsx
│   │   ├── Tabs.tsx
│   │   ├── Divider.tsx
│   │   ├── ResizablePanel.tsx
│   │   ├── ScrollArea.tsx
│   │   ├── ContextMenu.tsx
│   │   ├── DropdownMenu.tsx
│   │   └── SearchInput.tsx
│   ├── chat/                   # 聊天业务组件
│   │   ├── ChatHeader.tsx         # 模型/知识库/引用格式选择
│   │   ├── MessageList.tsx        # 消息列表容器（自动滚动）
│   │   ├── ChatMessage.tsx        # 单条消息渲染（含 Markdown/LaTeX + 引用）
│   │   ├── ChatInput.tsx          # 输入框 + 发送按钮
│   │   ├── RetrievalPanel.tsx     # 右侧检索结果面板
│   │   ├── CitationRenderer.tsx   # [N] 引用角标渲染（上标，可点击）
│   │   └── CitationPopover.tsx    # 引用详情悬浮卡片
│   ├── search/                 # 搜索页业务组件
│   │   ├── SearchHeader.tsx       # 知识库选择 + 搜索参数配置
│   │   ├── SearchBar.tsx          # 搜索输入栏
│   │   └── SearchResultList.tsx   # 搜索结果列表
│   ├── knowledge/              # 知识库业务组件
│   │   ├── KBInfoPanel.tsx        # 知识库信息区（右侧上半部分）
│   │   ├── KBCreateForm.tsx       # 新建/编辑知识库表单（用于 FormModal）
│   │   ├── DocumentTable.tsx      # 文档管理表格（右侧下半部分）
│   │   ├── DocumentDetail.tsx     # 文档展开详情（摘要 + 引用信息）
│   │   ├── CitationForm.tsx       # 引用信息编辑表单
│   │   └── StatusBadge.tsx        # 文档状态标签
│   ├── providers/              # 供应商业务组件
│   │   ├── ProviderConfig.tsx     # 供应商配置区（API Key / 地址 / 测试连通性）
│   │   ├── ProviderForm.tsx       # 新建供应商弹窗表单
│   │   ├── ModelList.tsx          # 模型列表（按 series 分组）
│   │   ├── ModelForm.tsx          # 新建/编辑模型表单
│   │   └── ModelRow.tsx           # 模型列表行
│   ├── settings/               # 设置业务组件
│   │   └── SettingsForm.tsx       # 设置表单
│   └── shared/                 # 跨业务域共享组件
│       ├── FolderListSidebar.tsx  # 通用文件夹列表侧边栏
│       ├── NavBar.tsx             # 左侧导航栏
│       ├── ModelSelector.tsx      # 模型选择器（chat/embedding/reranking）
│       ├── KBSelector.tsx         # 知识库多选器
│       ├── CitationStyleSelect.tsx# 引用格式选择
│       ├── MarkdownLatexRenderer.tsx # Markdown + LaTeX 渲染器
│       ├── ChunkCard.tsx          # 检索块卡片（文件名+段落+分数+内容）
│       └── ProviderBadge.tsx      # 供应商类型徽标
├── hooks/                      # 自定义 Hooks
│   ├── useStreamingChat.ts
│   ├── useConversations.ts
│   ├── useMessages.ts
│   ├── useKnowledgeBases.ts
│   ├── useDocuments.ts
│   ├── useKBSearch.ts
│   ├── useProviders.ts
│   ├── useSettings.ts
│   ├── useToast.ts
│   └── useFolders.ts
├── pages/                      # 页面级组件
│   ├── ChatPage.tsx
│   ├── SearchPage.tsx
│   ├── KnowledgePage.tsx
│   ├── ProvidersPage.tsx
│   └── SettingsPage.tsx
├── services/                   # API 服务层
│   ├── api.ts
│   ├── chat.ts
│   ├── conversations.ts
│   ├── knowledge.ts
│   ├── documents.ts
│   ├── citations.ts
│   ├── providers.ts
│   ├── models.ts
│   ├── settings.ts
│   └── auxModels.ts
├── contexts/                   # React Context
│   ├── SettingsContext.tsx
│   └── ToastContext.tsx
├── types/                      # TypeScript 类型定义
│   ├── conversation.ts
│   ├── knowledge.ts
│   ├── provider.ts
│   ├── settings.ts
│   ├── chat.ts
│   ├── search.ts
│   └── folder.ts
├── utils/                      # 工具函数
│   ├── format.ts                  # 日期/文件大小格式化
│   ├── citation.ts                # 引用标记解析工具
│   └── storage.ts                 # localStorage 持久化工具
└── i18n/                       # 国际化
    └── index.ts                   # 加载 i18n/zh.json 或 en.json
```

---

## 11. TypeScript 类型定义

与后端 Pydantic schema 一一对应，放在 `types/` 目录下。

### 11.1 conversation.ts

```typescript
interface ConversationOut {
  id: number
  title: string
  summary: string | null
  model_id: number | null
  kb_ids: number[] | null
  citation_style: string
  created_at: string
  updated_at: string
  message_count: number
}

interface ConversationDetail extends ConversationOut {
  messages: MessageOut[]
}

interface MessageOut {
  id: number
  conversation_id: number
  role: 'system' | 'user' | 'assistant'
  content: string
  position: number
  references: ReferenceItem[] | null
  created_at: string
}

interface ReferenceItem {
  ref_num: number
  document_file_id: number
  original_filename: string
  formatted_citation: string
}

interface ConversationSearchResult {
  conversation: ConversationOut
  matched_in_title: boolean
  matched_in_summary: boolean
  matched_messages: MatchedMessage[]
}
```

### 11.2 knowledge.ts

```typescript
interface KnowledgeBaseOut {
  id: number
  name: string
  description: string | null
  collection_name: string | null
  embed_model_id: number
  chunk_size: number
  chunk_overlap: number
  rerank_model_id: number | null
  created_at: string
  updated_at: string
  document_count: number
}

interface DocumentFileOut {
  id: number
  knowledge_base_id: number
  original_filename: string
  file_type: string
  file_size: number
  status: 'pending' | 'processing' | 'indexed' | 'failed'
  error_message: string | null
  chunk_count: number
  created_at: string
  indexed_at: string | null
  has_citation: boolean
  abstract: string | null
}

interface CitationOut {
  id: number
  document_file_id: number
  citation_type: 'article' | 'book' | 'chapter' | 'thesis' | 'conference' | 'website' | 'other'
  title: string | null
  authors: string[] | null
  year: number | null
  source: string | null
  volume: string | null
  issue: string | null
  pages: string | null
  publisher: string | null
  edition: string | null
  doi: string | null
  isbn: string | null
  url: string | null
  accessed_date: string | null
  raw_citation: string | null
  extra: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

interface SearchResult {
  document_id: number
  original_filename: string
  chunk_index: number
  content: string
  score: number
}
```

### 11.3 provider.ts

```typescript
type InterfaceType = 'openai' | 'anthropic' | 'google' | 'ollama' | 'openai_compatible' | 'cohere' | 'jina'
type ModelType = 'chat' | 'embedding' | 'reranking'
type Capability = 'vision' | 'reasoning' | 'function_calling'

interface ProviderOut {
  id: number
  name: string
  interface_type: InterfaceType
  api_base_url: string | null
  api_key: string | null
  description: string | null
  is_enabled: boolean
  created_at: string
  updated_at: string
}

interface AIModelOut {
  id: number
  provider_id: number
  api_name: string
  display_name: string
  series: string | null
  model_type: ModelType
  capabilities: Capability[] | null
  context_length: number | null
  is_enabled: boolean
  is_default: boolean
  temperature: number | null
  top_p: number | null
  qps: number | null
  created_at: string
  updated_at: string
}
```

### 11.4 settings.ts

```typescript
interface SettingsOut {
  language: 'zh' | 'en'
  embed_max_concurrency: number
  rag_top_k: number
  default_embed_model_id: number | null
  pdf_parser: 'pdfplumber' | 'pymupdf' | 'pypdf'
  docx_parser: 'python-docx' | 'markitdown'
  doc_clean_model_id: number | null
  chat_summary_model_id: number | null
  info_extract_model_id: number | null
}

interface AuxModelOut {
  role: 'doc_clean' | 'chat_summary' | 'info_extract'
  description: string
  model_id: number | null
  model_display_name: string | null
  model_api_name: string | null
  provider_name: string | null
  model_qps: number | null
}
```

### 11.5 chat.ts

```typescript
interface ChatMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

interface ChatResponse {
  content: string
  model: string
  provider: string
  summary?: string | null
}

interface RAGChatResponse extends ChatResponse {
  references: ReferenceItem[]
}

// SSE 事件类型
type SSEEvent =
  | { type: 'token'; data: string }
  | { type: 'tool_call'; data: { name: string; args: Record<string, unknown> } }
  | { type: 'citations'; data: { references: ReferenceItem[]; cite_map: Record<string, string> } }
  | { type: 'summary'; data: string }
  | { type: 'error'; data: string }
  | { type: 'done' }
```

### 11.6 search.ts

```typescript
// 搜索页独立搜索的历史记录（前端本地存储）
interface SearchHistoryItem {
  id: string                       // 唯一标识（uuid）
  query: string                    // 查询文本
  kbIds: number[]                  // 搜索的知识库
  searchType: 'semantic' | 'keyword'
  topK: number
  rerank: boolean
  resultCount: number              // 结果数量
  createdAt: string                // 搜索时间
  folderId: string | null          // 所属文件夹
}
```

### 11.7 folder.ts

```typescript
// 通用文件夹结构（前端本地存储）
interface Folder {
  id: string                       // 唯一标识（uuid）
  name: string                     // 文件夹名称
  parentId: string | null          // 父文件夹（预留，暂不支持嵌套）
  scope: 'conversations' | 'search' | 'knowledge'  // 所属功能域
  createdAt: string
}

// 列表项与文件夹的映射关系
interface FolderMapping {
  itemId: string | number          // 列表项 ID（会话 ID / 搜索记录 ID / 知识库 ID）
  folderId: string                 // 所属文件夹 ID
}
```

---

## 12. SSE 流式处理方案

### 12.1 连接方式

使用 `fetch` + `ReadableStream` 处理 SSE（而非 `EventSource`，因为需要 POST 请求体）：

```typescript
const response = await fetch(url, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(requestBody),
})
const reader = response.body!.getReader()
const decoder = new TextDecoder()
// 逐块读取并解析 "data: xxx\n\n" 格式
```

### 12.2 事件解析规则

| 原始数据 | 解析为 |
|---|---|
| `data: {普通文本}\n\n` | `{ type: 'token', data: '...' }` |
| `data: [TOOL_CALL] {...}\n\n` | `{ type: 'tool_call', data: JSON.parse(...) }` |
| `data: [CITATIONS] {...}\n\n` | `{ type: 'citations', data: JSON.parse(...) }` |
| `data: [SUMMARY] {...}\n\n` | `{ type: 'summary', data: ... }` |
| `data: [ERROR] ...\n\n` | `{ type: 'error', data: '...' }` |
| `data: [DONE]\n\n` | `{ type: 'done' }` |

### 12.3 RAG 消息渲染流程

```
1. 流开始 → 显示空助手消息气泡 + 加载指示器 + 自动展开右侧检索面板
2. 收到 [TOOL_CALL] → 在消息区域显示"🔍 正在搜索知识库…" + 记录搜索参数到检索面板
3. 收到 token → 逐字追加到消息气泡（实时 Markdown + LaTeX 渲染）
4. 收到 [CITATIONS] → 获取 cite_map 替换 CITE 标记 + 将检索块填充到右侧面板
5. 收到 [DONE] → 消息完成，渲染引用角标为可交互元素
6. 点击 [N] → 弹出 CitationPopover + 右侧面板自动滚动到对应块并高亮
```

---

## 13. 国际化（i18n）方案

### 13.1 实现方式

从后端 `GET /api/settings` 读取 `language` 字段，加载对应的 `i18n/{lang}.json`。

前端维护一份 i18n 工具函数：

```typescript
function t(key: string, params?: Record<string, string>): string
// 示例: t('kb.not_found') → "知识库不存在"
// 示例: t('chat.rate_limited') → "请求超出模型 QPS 限制，请稍后重试"
```

### 13.2 i18n 涵盖的分类

| Key 前缀 | 内容 |
|---|---|
| `provider.*` | 供应商管理消息 |
| `model.*` | 模型管理与类型校验 |
| `chat.*` | 对话错误消息 |
| `admin.*` | 管理任务消息 |
| `settings.*` | 设置页标签 |
| `kb.*` | 知识库错误消息 |
| `conversation.*` | 会话管理消息 |
| `citation.*` | 引用格式名称与错误 |
| `auxmodel.*` | 辅助模型警告 |
| `status.*` | 文档状态标签（等待中/处理中/已索引/失败） |

---

## 14. 错误处理策略

### 14.1 HTTP 错误码对应 UI 行为

| 状态码 | 含义 | UI 行为 |
|---|---|---|
| `400` | 请求参数错误 | Toast 错误提示（显示 `detail`） |
| `403` | 供应商/模型已禁用 | Toast 警告 + 引导启用 |
| `404` | 资源不存在 | Toast 错误 + 返回列表 |
| `409` | 状态冲突 | Toast 警告（如模型已删除） |
| `429` | QPS 限流 | Toast 提示"请稍后重试" |
| `502` | 上游 LLM 调用失败 | Toast 错误 + 建议检查模型配置 |

### 14.2 统一错误处理

在 `api.ts` 的 `request()` 中统一捕获，解析 `detail` 字段：

```typescript
if (!res.ok) {
  const body = await res.json().catch(() => ({}))
  throw new ApiError(res.status, body.detail ?? res.statusText)
}
```

---

## 15. 关键交互流程

### 15.1 新建 RAG 对话

```
用户点击「新建对话」
  → 弹出配置弹窗（选模型、选知识库、选引用格式）
  → POST /api/conversations → 获得 conversation_id
  → 进入对话页面
  → 用户发送消息
  → POST /api/chat/{modelId}/rag/stream (body: messages + kb_ids + conversation_id)
  → 流式渲染回复 + 引用
```

### 15.2 添加文档到知识库

```
用户点击「添加文档」
  → Electron 文件选择对话框（支持多选）
  → POST /api/knowledge-bases/{kbId}/documents/batch (paths)
  → 返回文档列表（status: pending）
  → 前端开始轮询 GET .../documents（每 2 秒）
  → 文档状态变为 processing → indexed / failed
  → 停止轮询，更新列表显示
```

### 15.3 供应商连通性测试

```
用户点击「测试连通性」
  → POST /api/providers/{id}/test
  → 显示加载状态
  → 返回 { success, message, latency_ms }
  → 成功: 绿色 Toast "连通 (延迟 123ms)"
  → 失败: 红色 Toast 显示错误信息
```

---

### 15.4 独立知识库搜索

```
用户进入搜索页
  → 选择目标知识库（支持多选）
  → 配置搜索参数（类型 / Top K / Rerank）
  → 输入查询并搜索
  → GET /api/knowledge-bases/{kbId}/search (每个 KB 并行请求)
  → 合并结果按分数降序排列
  → 展示结果列表（每个块完整显示文本，支持 Markdown + LaTeX）
  → 搜索记录自动保存到左侧历史列表
  → 点击「查看引用信息」→ 弹窗显示格式化引用
  → 点击「定位到知识库」→ 跳转至 /knowledge 并选中对应知识库
```

---

## 16. 支持的文档格式

前端文件选择对话框应限制以下扩展名：

| 类型 | 扩展名 |
|---|---|
| 文本 | `.txt`, `.md`, `.csv`, `.json` |
| PDF | `.pdf` |
| Word | `.docx`, `.doc` |
| PowerPoint | `.pptx` |
| Excel | `.xlsx`, `.xls` |
| 网页 | `.html`, `.htm`, `.xml` |
| 电子书 | `.epub` |
| 富文本 | `.rtf` |
| OpenDocument | `.odt` |
