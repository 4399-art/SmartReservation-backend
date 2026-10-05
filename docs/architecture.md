# 智慧图书馆座位预约系统 — 架构文档

## 一、技术栈总览

| 层 | 技术 | 版本 |
|---|---|---|
| 后端框架 | FastAPI | 0.115 |
| ORM | SQLAlchemy | 2.0 |
| 数据库 | MySQL | — |
| 数据校验 | Pydantic v2 | 2.10 |
| 认证 | JWT (PyJWT) + bcrypt | — |
| AI 编排 | LangGraph | 0.5 |
| RAG | LangChain + ChromaDB | — |
| 向量嵌入 | 可切换 (OpenAI / DashScope) | — |
| 前端 | Vue 3 + Element Plus | — |
| 包管理 | uv | — |

## 二、目录结构

```
backend/
├── main.py                     # FastAPI 入口，路由注册，数据库初始化
├── pyproject.toml              # 依赖声明（uv）
├── .env                        # 环境变量（数据库/密钥/LLM）
├── uploads/                    # 静态文件上传目录（图片等）
├── rag_uploads/                # RAG 文档上传目录
├── chroma_db/                  # ChromaDB 持久化存储
└── app/
    ├── config.py               # Settings + 常量（路径、大小限制等）
    ├── database.py             # SQLAlchemy engine / Session / Base
    │
    ├── model/                  # ORM 模型（数据库表定义）
    │   ├── user.py             # users — 用户
    │   ├── space.py            # spaces — 图书馆区域
    │   ├── seat.py             # seats — 座位（FK → spaces）
    │   ├── reservation.py      # reservations — 预约记录
    │   └── chat_session.py     # chat_sessions + chat_messages — AI 会话
    │
    ├── schemas/                # Pydantic Schema（请求/响应 DTO）
    │   ├── auth.py             # 登录
    │   ├── user.py
    │   ├── space.py
    │   ├── seat.py
    │   ├── reservation.py
    │   ├── chat.py             # LangGraph 对话请求
    │   └── rag.py              # RAG 上传/问答
    │
    ├── api/                    # FastAPI Router（HTTP 入口）
    │   ├── auth.py             # POST /api/auth/login
    │   ├── user.py             # /api/users/*（受保护）
    │   ├── space.py            # /api/space/*
    │   ├── seat.py             # /api/seat/*
    │   ├── reservation.py      # /api/reservation/*
    │   ├── chat.py             # /api/chat/*（LangGraph 对话）
    │   ├── rag.py              # /api/rag/*（知识库）
    │   └── files.py            # 文件上传
    │
    ├── service/                # 业务逻辑（可复用）
    │   ├── auth_service.py
    │   ├── user_service.py
    │   ├── space_service.py    # get_space_occupancy() 区域占用查询
    │   ├── seat_service.py
    │   └── reservation_service.py
    │
    ├── langgraph/              # LangGraph 智能助手
    │   ├── graph.py            # StateGraph 定义 + 节点 + 系统提示词
    │   ├── state.py            # AgentState TypedDict
    │   └── tools.py            # 工具函数（查区域/查座位/创建预约...）
    │
    ├── rag/                    # RAG 管线
    │   ├── embeddings.py       # 嵌入模型初始化（OpenAI / DashScope）
    │   ├── vector_store.py     # ChromaDB 集合管理（含去重校验）
    │   ├── document_loader.py # 文档加载 + 分块
    │   └── chain.py            # RetrievalQA 链路
    │
    ├── common/                 # 公共模块
    │   ├── response.py         # ApiResponse<T> 统一响应
    │   └── exceptions.py       # BusinessException + 全局异常处理器
    │
    ├── dependencies/
    │   └── auth.py             # get_current_user（JWT 校验依赖）
    │
    └── utils/
        ├── jwt.py              # create / decode
        └── password.py         # hash / verify
```

## 三、分层架构

```
 HTTP Request
      │
      ▼
 ┌──────────────┐
 │   api/*.py   │  ← Router 层：参数解析、权限、返回格式
 └──────┬───────┘
        │
        ▼
 ┌──────────────┐
 │ service/*.py │  ← 业务层：核心业务逻辑
 └──────┬───────┘
        │
        ▼
 ┌──────────────┐     ┌─────────────────┐
 │  model/*.py  │     │  langgraph/      │  ← AI 旁路
 │  SQLAlchemy  │     │  RAG chain       │
 └──────┬───────┘     └────────┬────────┘
        │                      │
        ▼                      ▼
   MySQL DB               ChromaDB + LLM
```

**各层职责**：

| 层 | 做什么 | 不做什么 |
|---|---|---|
| `api/` | 解析参数、鉴权、响应格式、错误码转换 | 不写业务判断 |
| `service/` | 业务规则校验、事务、组合多个 model | 不处理 HTTP 细节 |
| `model/` | 表结构、外键、enum | 不写业务逻辑 |
| `schemas/` | DTO 定义 | — |

## 四、数据模型关系

```
 users ──┬── reservations ─── spaces ── seats
          │                       │
          └───────────────────────┘   (seat_id 可空 = 预约整个区域)
```

```sql
 spaces  ─ 图书馆区域
   id, name, location, capacity, open_time, close_time, status

 seats  ─ 座位
   id, space_id (FK), seat_no, seat_type, has_power, has_socket, status

 reservations  ─ 预约
   id, user_id (FK), space_id (FK), seat_id (FK nullable),
   date, start_time, end_time, status (0-3), audit_remark

 users  ─ 用户
   id, username, password (bcrypt), role, status

 chat_sessions / chat_messages  ─ LangGraph 会话历史持久化
```

**预约状态机**：

```
  PENDING(0) ──admin 审核通过──▶ APPROVED(1)
      │
      ├──admin 拒绝──▶ REJECTED(2)
      │
      └──用户取消──▶ CANCELLED(3)
```

## 五、API 路由清单

所有前缀 `/api`。

### 公开路由

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/login` | 账号密码登录，返回 JWT |
| POST | `/auth/register` | 学生自助注册 |
| GET | `/space/open` | 开放区域列表（无需登录） |

### 受保护路由（需 Bearer Token）

| 方法 | 路径 | 说明 |
|---|---|---|
| **User** | | |
| GET | `/users/me` | 当前用户信息 |
| **Space** | | |
| GET | `/space/list` | 分页查询（管理员） |
| POST | `/space` | 新增区域 |
| PUT | `/space/{id}` | 更新区域 |
| DELETE | `/space/{id}` | 删除区域 |
| GET | `/space/{id}/occupancy?date=` | 某区域某天占用情况（时间轴用） |
| **Seat** | | |
| GET | `/seat/list?space_id=` | 区域下的座位 |
| POST | `/seat` | 新增座位 |
| PUT | `/seat/{id}` | 更新座位 |
| DELETE | `/seat/{id}` | 删除座位 |
| **Reservation** | | |
| POST | `/reservation` | 创建预约（seat_id 空 = 区域级） |
| GET | `/reservation/my` | 我的预约 |
| GET | `/reservation/list` | 全部预约（管理员） |
| PUT | `/reservation/{id}/audit` | 审核通过/拒绝 |
| PUT | `/reservation/{id}/cancel` | 取消预约 |
| **LangGraph AI** | | |
| POST | `/chat/session` | 创建新会话 |
| GET | `/chat/session/list` | 我的会话列表 |
| GET | `/chat/session/{id}/messages` | 会话历史 |
| DELETE | `/chat/session/{id}` | 删除会话 |
| POST | `/chat/{session_id}` | 发送消息 → LangGraph 流式回复 |
| **RAG 知识库** | | |
| POST | `/rag/upload` | 上传 md 文档（向量化 + 去重） |
| GET | `/rag/list` | 已上传文档 |
| DELETE | `/rag/{id}` | 删除文档（同步清理向量） |
| POST | `/rag/query` | 基于知识库问答 |
| **Files** | | |
| POST | `/files/upload` | 通用文件上传 |

## 六、核心业务流程

### 1. 区域预约（时间轴）

```
前端 Space.vue
     │
     ├── 1. GET /api/space/{id}/occupancy?date=2026-10-06
     │     → 返回 { open_time, close_time, occupancy: [{start_time, end_time, ...}] }
     │
     ├── 2. 用户在时间轴上拖拽选择 → mySelection
     │
     └── 3. POST /api/reservation
           { space_id, seat_id: null, date, start_time, end_time }
     │
     ▼
service/reservation_service.py
     │  校验：时段是否在开放时间内？是否与已有 PENDING/APPROVED 冲突？
     │
     ▼
DB 写入 reservations，status = 0 (PENDING)
```

### 2. LangGraph 智能助手

详见 [langgraph.md](langgraph.md)。

```
用户消息 → /api/chat/{session_id}
    │
    ▼
LangGraph graph.py StateGraph
    │  ┌─ Node 1: llm_with_tools（决定是否调用工具）
    │  ├─ Node 2: tools_condition（判断 tool call 还是直接回复）
    │  ├─ Node 3: tool_node（执行 tools.py 中的函数）
    │  └─ Node 4: 循环或结束
    │
    ▼
SSE stream → 前端 Chat.vue 逐 token 渲染
```

### 3. RAG 文档问答

详见 [rag.md](rag.md)。

```
POST /rag/upload (file.md)
    │
    ├── document_loader.py → 读取 md
    ├── RecursiveCharacterTextSplitter → 分块
    ├── embeddings.py → 调用 LLM 生成向量
    ├── vector_store.py → 去重校验（文件 hash）
    └── ChromaDB.add()

POST /rag/query { question }
    │
    ├── ChromaDB.similarity_search() → Top-K chunks
    └── RetrievalQA.run() → LLM 综合回答
```

## 七、环境变量 (.env)

| 变量 | 示例 | 说明 |
|---|---|---|
| `DATABASE_URL` | `mysql+pymysql://root:xxx@localhost:3306/library` | MySQL 连接串 |
| `JWT_SECRET_KEY` | — | JWT 签名密钥 |
| `JWT_EXPIRE_HOURS` | `24` | Token 过期小时数 |
| `CORS_ORIGINS` | `http://localhost:5173` | 逗号分隔 |
| `LLM_API_KEY` | `sk-...` | LLM 平台 Key |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | 兼容 OpenAI 格式 |
| `LLM_MODEL` | `deepseek-chat` | 对话模型 |
| `EMBEDDING_PROVIDER` | `openai` / `dashscope` | 嵌入提供方 |
| `EMBEDDING_API_KEY` | — | 嵌入 Key（可同 LLM） |
| `EMBEDDING_BASE_URL` | — | 嵌入 endpoint |
| `EMBEDDING_MODEL` | `text-embedding-v2` | 嵌入模型名 |
| `DASHSCOPE_API_KEY` | — | 阿里云百炼 Key（DashScope 模式） |

## 八、启动方式

```bash
# 1. 安装依赖
uv sync --default-index https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 配置环境
cp .env.example .env   # 填入真实值

# 3. 启动
uv run uvicorn main:app --reload --port 8000

# 4. 前端（分离目录）
cd ../frontend
npm run dev
```

启动后访问：
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：`GET /` → `{"service": "智慧图书馆座位预约系统", "status": "ok"}`

## 九、依赖关系速查

```
  FastAPI ─── SQLAlchemy ─── MySQL
     │
     ├── Pydantic v2 (schemas)
     ├── PyJWT + bcrypt (auth)
     │
     ├── LangGraph ── LangChain ── ChromaDB (RAG)
     │                                │
     └── OpenAI SDK ─────────────────┘
            (对话 + 嵌入)
```

## 十、设计原则

| 原则 | 体现 |
|---|---|
| **分层清晰** | api / service / model 严格分离，禁止跨层依赖 |
| **统一响应** | 所有接口返回 `{ code, data, message }` |
| **统一异常** | BusinessException + 全局 4 个异常处理器 |
| **可切换嵌入** | `EMBEDDING_PROVIDER` 支持 openai / dashscope |
| **区域+座位二级预约** | `reservation.seat_id` 可空，区分预约粒度 |
| **LangGraph 持久化会话** | chat_sessions + chat_messages 存 DB，SQLite checkpointer |
| **RAG 文档去重** | upload 前计算文件 hash，已存在则跳过 |
