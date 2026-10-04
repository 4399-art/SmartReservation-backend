# RAG 智能问答模块说明

## 整体架构

RAG（Retrieval-Augmented Generation）模块由以下文件协作完成：

```
backend/
├── app/
│   ├── rag/
│   │   ├── __init__.py            # 模块导出
│   │   ├── embeddings.py          # 自定义 Embeddings 类（OpenAI 兼容接口）
│   │   ├── vector_store.py        # ChromaDB 封装（增/删/查向量）
│   │   ├── document_loader.py     # Markdown 文档加载与切分
│   │   └── chain.py               # LangChain RAG Chain 构建 + 问答入口
│   ├── api/rag.py                 # FastAPI 路由（上传 / 列表 / 删除 / 问答）
│   ├── schemas/rag.py             # Pydantic 请求体
│   └── config.py                  # 新增 CHROMA_DIR / RAG_UPLOAD_DIR / Embedding 配置
├── chroma_db/                     # ChromaDB 持久化目录（自动创建）
├── rag_uploads/                   # 原始上传文件保存目录（自动创建）
└── .env                           # Embedding / LLM 相关配置

frontend/
├── src/
│   ├── api/rag.js                 # 4 个 API 封装
│   ├── views/RagManage.vue        # 知识库管理页面（上传 + 列表 + 删除）
│   ├── components/ChatFloat.vue   # 右下角悬浮智能助手
│   ├── router/index.js            # 新增 /manager/rag 路由
│   ├── App.vue                    # 全局挂载 ChatFloat
│   └── layouts/Layout.vue         # 侧边栏新增「知识库管理」菜单
```

## 技术选型

| 层级 | 技术 | 说明 |
|---|---|---|
| 向量数据库 | **ChromaDB 1.5.9** | 轻量级嵌入式向量库，无需独立服务，持久化到本地目录 |
| LangChain | langchain 0.3.14 + langchain-chroma | RAG 编排框架 |
| Embedding | OpenAI 兼容接口（自定义 Embeddings 类） | 默认走阿里云 MAAS，也支持 DashScope |
| LLM | AgnesAI `agnes-3.0-flash` | 复用现有对话模型，承担 RAG 的生成角色 |
| 前端 UI | Element Plus `el-upload` + Vue 悬浮组件 | 知识库管理 + 全局智能助手 |

## 核心流程

### 文档上传与向量化

```
前端 RagManage.vue 选择 .md 文件
        │ POST /api/rag/upload  (multipart/form-data)
        ▼
  app/api/rag.py
        │
        ├─ 1. 校验扩展名仅允许 .md
        ├─ 2. 保存原始文件到 rag_uploads/{uuid}_{filename}
        ├─ 3. load_and_split_markdown(path)
        │       ├── MarkdownHeaderTextSplitter  按 H1~H4 标题分层
        │       └── RecursiveCharacterTextSplitter  回退切分 (chunk_size=800, overlap=100)
        │
        └─ 4. add_documents(chunks, source_file)
                │
                ▼
          vector_store.py → Chroma.add_texts(metadatas=[{source: filename}])
                │
                ▼
          ChromaDB 持久化到 chroma_db/
```

### 智能问答

```
前端 ChatFloat.vue 发送问题
        │ POST /api/rag/chat  { question: "..." }
        ▼
  app/api/rag.py → ask_rag(question)
        │
        ▼
  chain.py · build_rag_chain()
        │
        ├─ 1. Chroma Retriever.similarity_search(k=4) → 检索相关片段
        ├─ 2. 注入 Prompt 模板（参考文档 + 问题）
        └─ 3. 调用 LLM 生成回答
                │
                ▼
          返回 { answer: "..." }
```

## Embeddings 设计

### 为什么自定义 Embeddings 类？

项目使用的 Embedding 通道（阿里云 MAAS 等）与 LangChain 内置的 `OpenAIEmbeddings` 存在兼容性问题：

- LangChain OpenAIEmbeddings 默认启用 tiktoken，批量切分后传入 token ids 而非原始文本
- 部分 MAAS 网关不接受 token ids，只接受字符串输入

因此在 `app/rag/embeddings.py` 中实现了 `OpenAICompatibleEmbeddings`，**直接封装 OpenAI SDK 的 `embeddings.create(input=[...])` 调用**，传入原始字符串，绕过一切中间层。

### 双 Provider 支持

`.env` 中通过 `EMBEDDING_PROVIDER` 切换：

```env
# 方案 A：OpenAI 兼容接口（默认，阿里云 MAAS / 千帆 / OneAPI 等）
EMBEDDING_PROVIDER=openai
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_BASE_URL=https://xxx.maas.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=qwen3.7-text-embedding-flash

# 方案 B：阿里百炼 DashScope
EMBEDDING_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-xxx
EMBEDDING_MODEL=text-embedding-v3
```

`vector_store.py::_get_embeddings()` 根据 provider 值分发到 `_get_openai_embeddings()` 或 `_get_dashscope_embeddings()`。

## 文档去重与更新策略

上传接口 `POST /api/rag/upload` 内置三层防重校验，避免向量库被重复写入：

```
上传 test.md
    │
    ▼
[Layer 1] 按文件名查找 rag_uploads/ 下的已有副本
    │
    ├─ 找到 & 字节级内容完全一致 → 直接返回 "跳过"，零 Embedding 开销
    │   返回: { code: 200, data: { skipped: true, chunks_count: 0 } }
    │
    └─ 没找到 或 内容有变化
            │
            ▼
    [Layer 2] 先删后写
            │
            ├─ delete_documents_by_source(filename)  → 清 Chroma 中该文件的所有旧向量
            ├─ 删除 rag_uploads/ 中该文件的旧副本
            │
            ▼
    [Layer 3] 正常向量化
            ├─ 保存新文件副本  uuid_filename.md
            ├─ load_and_split_markdown() 切分
            └─ add_documents() 写入 Chroma
```

### 设计理由

| 场景 | 行为 |
|---|---|
| 同一个文件连点上传按钮 | Layer 1 命中，跳过向量化，省 Embedding API 调用 |
| 同名文件内容改了 | Layer 2 先删旧向量再写新的，保证同名文件永远只有一份向量 |
| 不同名文件 | 互不干扰，各自独立管理 |

文件查找逻辑：`rag_uploads/` 里的存储格式是 `{uuid}_{原始文件名}`，通过 `endswith(f"_{source_name}")` 反查，定位已有副本后做 `bytes == raw` 比对。

## API 端点

| 方法 | 路径 | 功能 | 请求体 / 参数 |
|---|---|---|---|
| POST | `/api/rag/upload` | 上传 .md 文档 | `multipart/form-data`, field: `file` |
| GET | `/api/rag/documents` | 列出所有已入库文档 | — |
| DELETE | `/api/rag/documents/{filename}` | 删除指定文档及其向量 | URL path: 原始文件名 |
| POST | `/api/rag/chat` | 智能问答 | `{ "question": "..." }` |

所有端点返回统一格式：

```json
{ "code": 200, "message": "操作成功", "data": { ... } }
```

## 关键实现细节

### ChromaDB metadata 按源文件分组

每次 `add_documents` 写入时，都会在每个 chunk 的 metadata 里附加 `source=原始文件名`。删除文档时通过 `store.get(where={"source": filename})` 查出所有向量 id 再批量删除，保证源文件与向量库状态一致。

### Markdown 切分策略

```python
# 第一层：按标题结构分层，保留层级信息
splitter = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("#", "H1"), ("##", "H2"), ("###", "H3"), ("####", "H4")]
)
# 第二层：按字符长度回退切分，保留上下文重叠
recursive = RecursiveCharacterTextSplitter(
    chunk_size=800, chunk_overlap=100, length_function=len
)
```

chunk_size=800 兼顾中文语义完整性与 Embedding 模型上下文窗口限制，overlap=100 避免关键信息被截断在边界。

### RAG Prompt 模板（chain.py）

```python
template = """你是一个专业的智能实验室预约系统助手。请根据以下参考文档回答用户问题。
如果参考文档中没有相关内容，请直接回答"抱歉，我在知识库中没有找到相关内容"，不要编造答案。

参考文档：
{context}

用户问题：{question}"""
```

检索到的 Top-4 片段会拼接进 `{context}` 占位符，LLM 在上下文约束下生成回答。

## 目录结构与数据持久化

| 目录 | 内容 | 清理方式 |
|---|---|---|
| `chroma_db/` | ChromaDB 向量数据（自动创建） | 删掉整个目录即可清空所有向量 |
| `rag_uploads/` | 用户上传的原始文件副本（uuid 重命名） | 可手动清理 |

**开发调试时如果向量库出现异常**，直接删除 `chroma_db/` 目录后重新上传文档即可。

## 前端交互说明

### 知识库管理页 `/manager/rag`

- 侧边栏点击「知识库管理」进入
- 支持上传 `.md` 文件，上传后自动切分并写入向量库
- 下方表格列出所有已入库文档，支持单个删除

### 悬浮智能助手

- 全局组件 `ChatFloat.vue`，挂载在 `App.vue` 中
- 右下角圆形按钮，点击展开聊天窗口
- 支持多轮对话历史，自动滚底，typing 动画
- Enter 发送，Shift+Enter 换行

## 依赖清单

```toml
# pyproject.toml
dependencies = [
    "langchain==0.3.14",
    "langchain-community==0.3.14",
    "langchain-openai==0.2.12",
    "langchain-text-splitters>=0.3.0",
    "langchain-chroma>=0.2.0",
    "chromadb>=0.5.0",
    "python-multipart>=0.0.32",   # FastAPI 文件上传必需
    # dashscope 可选：如果用阿里百炼 Embedding
]
```

## 常见问题

**Q: 上传报错 "Microsoft Visual C++ 14.0 required"？**
A: 这是旧版 chroma-hnswlib 的编译错误。已升级到 ChromaDB 1.5.9，该问题已修复。如果还出现，确认 `pyproject.toml` 中 `chromadb>=0.5.0` 并重新 `uv sync`。

**Q: 上传成功但回答总是"没找到相关内容"？**
A: 可能原因：
1. 文档内容确实与问题不相关（Embedding 向量距离太远）
2. `CHROMA_DIR` 目录被删过但旧数据还在内存中 → 重启后端
3. `EMBEDDING_MODEL` 和 `LLM_MODEL` 跨通道混用导致检索向量维度不匹配

**Q: 如何切换 Embedding 通道？**
A: 修改 `.env` 的 `EMBEDDING_PROVIDER` 为 `openai` 或 `dashscope`，同时配置对应的 API Key / Base URL。切换后需要**删除 `chroma_db/` 目录并重新上传所有文档**，因为不同 Embedding 模型产生的向量维度不同，不能混用。

**Q: 支持哪些文档格式？**
A: 当前仅支持 `.md`（Markdown）。如需扩展 `.txt` / `.pdf` / `.docx`，在 `document_loader.py` 中增加对应 Loader（PyPDFLoader / Docx2txtLoader 等），并在 `api/rag.py::ALLOWED_RAG_EXT` 白名单中添加后缀即可。