# LangGraph 构建智能预约助手

## 一、概述

本项目的智能助手基于 **LangGraph Agent** 构建，核心思路是：给 LLM 一组可调用的**工具函数**（Tool Calling），让它自己决定什么时候调什么工具，最终输出对用户有用的结果。助手同时集成了 RAG 知识库检索能力，能回答规则类问题。

### 与 RAG 的区别

| 维度 | 纯 RAG | LangGraph Agent |
|---|---|---|
| 数据来源 | 向量库（离线文档） | **实时数据库 + 向量库** |
| 能力边界 | 只能"答" | **能查、能约、能取消** |
| 交互模式 | 单轮问答 | **多轮对话、工具链式调用** |
| 本项目中的分工 | 回答规则类问题 | **查询实时数据、执行预约操作** |

助手内部：数据库操作全部走 Tool Calling，文档类问题调 `rag_search` 工具，最终用 LLM 整合输出。

### 技术选型

| 组件 | 版本 | 作用 |
|---|---|---|
| langgraph | 0.2.x | Agent 编排框架 |
| langchain-core | 0.3.x | Message / Tool 基础抽象 |
| langchain-openai | 0.2.x | ChatOpenAI 兼容接口 |
| LLM | agnes-3.0-flash | 承担推理 + 工具调用决策 |

---

## 二、核心概念

### 2.1 LangGraph 的图模型

LangGraph 把 Agent 看作一个**有向图**：节点（Node）执行逻辑，边（Edge）决定流向。

```
          ┌──────────────┐
  ┌──────▶│    agent     │◀───────┐
  │       │  (LLM 决策)  │        │
  │       └──────┬───────┘        │
  │              │                │
  │     tool_calls?               │
  │        │    │                 │
  │       Yes   No → END          │
  │        │                      │
  │        ▼                      │
  │  ┌──────────────┐            │
  │  │    tools     │─────────────┘
  │  │ (ToolNode)   │
  │  └──────────────┘
  │
  └── 工具执行完回到 agent
```

- **agent 节点**：LLM 判断意图 → 决定调哪些工具 / 直接回答
- **tools 节点**：真正执行 Python 函数（查询数据库、创建预约等）
- **循环**：工具执行完把结果返回给 agent，agent 再决定下一步

### 2.2 Tool Calling 原理

LLM 收到用户消息后，有两种输出：

**情况 A：需要调工具**
```json
{
  "content": null,
  "tool_calls": [
    {
      "name": "list_spaces",
      "args": { "keywords": "自习室" }
    }
  ]
}
```

**情况 B：直接回答**
```json
{
  "content": "图书馆自习室在 B 区 2 楼，开放时间 06:00~23:00",
  "tool_calls": []
}
```

LangGraph 的 `ToolNode` 会自动帮你：
1. 解析 `tool_calls` 里的 name 和 args
2. 找到对应的 Python 函数执行
3. 把执行结果包装成 `ToolMessage` 返回给 LLM

你只需要**用 `@tool` 装饰器写好函数**，剩下的 LangGraph 全包了。

---

## 三、项目文件结构

```
backend/app/langgraph/
├── __init__.py
├── state.py        # AgentState 状态定义
├── tools.py        # 所有工具函数 + ALL_TOOLS 列表
└── graph.py        # 系统提示词 + 图构建 + ask_agent() 入口
```

### 和 RAG 模块的协作

```
tools.py ─── rag_search() ──▶ app/rag/vector_store.py
                                    │
                                    ▼
                              ChromaDB 向量库
```

`rag_search` 本身就是一个 LangGraph 工具，LLM 决定要不要调它。

---

## 四、逐层实现

### 4.1 State — 对话状态

`state.py` 定义 Agent 在图中流转的数据结构：

```python
from typing import TypedDict, Annotated
from operator import add
from langchain_core.messages import BaseMessage

class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add]
    user_id: int
```

两个字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `messages` | `list[BaseMessage]` | 完整的对话历史（System / Human / AI / Tool） |
| `user_id` | `int` | 当前登录用户，用于注入到需要身份的工具里 |

`Annotated[list, add]` 是 LangGraph 的关键语法 —— 表示多个节点返回的 messages 会被**累加**而不是覆盖。这让 agent → tools → agent 的循环里，每一轮的新消息都会追加到历史中。

### 4.2 Tools — 工具函数

#### 4.2.1 基础模板

每个工具的写法完全统一：

```python
from langchain_core.tools import tool
from app.database import SessionLocal

@tool
def list_spaces(keywords: str | None = None) -> str:
    """列出图书馆所有开放的区域空间。keywords 可按名称/位置模糊搜索。"""
    db = SessionLocal()
    try:
        # ... 数据库查询逻辑 ...
        return "格式化的结果字符串"
    finally:
        db.close()
```

要点：
- **函数名** = LLM 调用时用的工具名（`@tool` 自动取 `__name__`）
- **docstring** = LLM 理解工具用途的唯一依据，必须写清楚功能和参数说明
- **返回值** = 字符串，LangGraph 自动包装成 `ToolMessage` 传回 LLM
- **异常处理** = 工具内部自己 catch，把错误信息也返回成字符串，不要让异常抛到图外面

#### 4.2.2 完整工具清单

| 工具 | 功能 | LLM 何时调用 |
|---|---|---|
| `list_spaces(keywords?)` | 列出开放区域 | 用户问"有哪些区域"、"自习室在哪" |
| `get_space_detail(space_id)` | 区域详情 + 座位列表 | 用户指定了某个区域 |
| `check_seat_availability(space_id, date, start_time, end_time, seat_id?)` | 检查可约性 | 预约前的最后校验 |
| `create_reservation(user_id, space_id, date, start_time, end_time, seat_id?, remark?)` | 创建预约 | 所有参数到齐后立即调用 |
| `cancel_reservation(user_id, reservation_id)` | 取消预约 | 用户说"取消那个预约" |
| `list_my_reservations(user_id, status?)` | 我的预约 | 用户问"我约了什么" |
| `rag_search(question)` | 知识库检索 | 规则类问题（开放时间、占座规定等） |
| `get_date_info()` | 获取真实日期 | 用户说"明天"、"周五"等模糊日期词 |

#### 4.2.3 必须注入 user_id 的工具

`create_reservation` / `cancel_reservation` / `list_my_reservations` 都需要 `user_id`，但 LLM 不可能凭空知道当前用户是谁。解决方案是在 **graph 层统一注入**，不让 LLM 操心（详见 4.3.5）。

### 4.3 Graph — 图编排

#### 4.3.1 LLM 初始化

```python
def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=0.3,
    )
```

`temperature=0.3` 比普通聊天低一些，因为工具调用需要更确定性的输出。

#### 4.3.2 System Prompt — 灵魂所在

这是决定助手"智不智能"的核心。完整 prompt 在 `graph.py` 中，这里摘录关键策略：

```
1. 能直接做事就别问 → 参数齐全立刻调工具，不要反复确认
2. 日期必须准确 → 涉及日期先 get_date_info，绝对不要自己编造
3. space_id 必须精确 → 调用 create_reservation 前，space_id 必须来自工具返回
4. 时间范围必须精确 → "下午"不行，必须追问到 "14:00-16:00"
5. user_id 已注入 → 调工具时自动带上，不要问用户
```

#### 4.3.3 Agent 节点

```python
def agent_node(state: AgentState) -> dict:
    llm = _build_llm().bind_tools(ALL_TOOLS)

    messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(state.get("messages", []))
    user_id = state.get("user_id")
    if user_id is not None:
        messages.append(SystemMessage(content=f"[当前用户 user_id={user_id}]"))

    response = llm.invoke(messages)
    return {"messages": [response]}
```

三个关键动作：

1. **`bind_tools(ALL_TOOLS)`** — 把所有工具的 schema 注册给 LLM，让它知道有哪些工具可以调、每个工具要什么参数
2. **拼接 messages** — System Prompt 在前，对话历史在后；user_id 单独追加一条 SystemMessage
3. **返回 dict** — LangGraph 的节点必须返回 `{"messages": [新消息]}`，框架自动累加

#### 4.3.4 条件边 — 走 tools 还是结束

```python
def should_continue(state: AgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return END
    last = messages[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END
```

逻辑极其简单：
- 最后一条是 AI 消息 **且** 带 `tool_calls` → 去 tools 节点
- 否则 → 直接结束（AI 已经给了最终文字回答）

#### 4.3.5 Tools 节点 — 带 user_id 注入

```python
def tools_node(state: AgentState) -> dict:
    user_id = state.get("user_id")
    messages = _inject_user_id_into_tool_args(user_id, list(state.get("messages", [])))
    tool_node = ToolNode(ALL_TOOLS)
    result = tool_node.invoke({"messages": messages})
    return {"messages": result["messages"]}
```

`_inject_user_id_into_tool_args` 是项目的一个精巧设计 —— **不让 LLM 负责传 user_id，而在执行层自动塞进去**：

```python
def _inject_user_id_into_tool_args(user_id: int | None, messages: list) -> list:
    if user_id is None:
        return messages
    patched = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            new_calls = []
            for tc in msg.tool_calls:
                args = dict(tc.get("args", {}))
                if tc.get("name") in ("create_reservation", "cancel_reservation", "list_my_reservations"):
                    args["user_id"] = user_id
                new_calls.append({**tc, "args": args})
            msg = AIMessage(content=msg.content, tool_calls=new_calls, id=msg.id)
        patched.append(msg)
    return patched
```

为什么要这样做？

| 不注入（让 LLM 自己传） | 注入（执行层自动塞） |
|---|---|
| LLM 得从 SystemMessage 里解析 user_id | LLM 完全不知道 user_id 的存在 |
| 可能传错（比如用户 A 传了用户 B 的 id） | 永远正确，来自服务器 session |
| 工具 docstring 必须告诉 LLM 传 user_id | 工具 docstring 不用提 user_id，更干净 |

#### 4.3.6 图构建

```python
def build_agent_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    return workflow.compile()
```

5 行代码搭完整个 Agent 循环。`compile()` 后得到一个可直接 `.invoke(state)` 调用的 CompiledGraph。

#### 4.3.7 对外入口

```python
def ask_agent(question: str, user_id: int | None = None, chat_history: list | None = None) -> str:
    graph = build_agent_graph()

    messages = []
    if chat_history:
        messages.extend(chat_history)
    messages.append(HumanMessage(content=question))

    state: AgentState = {"messages": messages}
    if user_id is not None:
        state["user_id"] = user_id

    result = graph.invoke(state)
    final_messages = result.get("messages", [])
    last = final_messages[-1]
    return last.content
```

- **graph 每次新建**：生产环境可以缓存，但开发期图很轻量，每次重建方便热加载
- **chat_history 入参**：来自数据库中的对话历史（由 API 层加载）
- **只返回 content**：LLM 最终的文字回答，前端直接渲染

---

## 五、对话历史持久化

### 5.1 数据库模型

```
chat_sessions    # 会话表（id, user_id, title, create_time, update_time）
chat_messages    # 消息表（id, session_id, role, content, create_time）
```

每个登录用户可以有多个会话，每个会话有独立的消息序列。

### 5.2 调用链路

```
前端 ChatFloat.vue 发送 question + session_id
        │
        ▼
POST /api/chat/ask
        │
        ├─ 1. 加载 session 对应的历史消息 → 转为 LangChain BaseMessage 列表
        ├─ 2. ask_agent(question, user_id, chat_history)
        │       └── LangGraph 循环执行，可能调多个工具
        ├─ 3. 把 user 消息 + agent 最终回复 存入 chat_messages
        └─ 4. 返回 { answer, session_id }
```

### 5.3 会话管理

前端交互：
- 点击悬浮按钮 → 加载最近一次会话
- 点击 "+" → 新建会话（session_id 为 null，后端自动创建）
- 会话列表侧栏 → 切换 / 删除历史会话

---

## 六、典型对话的执行轨迹

### 6.1 完整预约流程

```
用户: "帮我预约明天下午自习室的座位"
        │
        ▼
  agent_node:
    ├── LLM 判断: "下午"是模糊词 + 需要预约
    └── 回复: "请问具体是几点到几点呢？"
        │
        ▼  (用户补了 "14:00-16:00")
        │
  agent_node:
    ├── bind_tools 后 LLM 产生 tool_calls:
    │   [ {name: "get_date_info"}, {name: "list_spaces", args: {keywords: "自习室"}} ]
    └── 返回 AIMessage(tool_calls=[...])
        │
        ▼
  tools_node:
    ├── 执行 get_date_info → "明天: 2026-10-06 星期二"
    └── 执行 list_spaces(keywords="自习室") → "【区域】ID:10 名称:自习室 ..."
        │
        ▼  (两个 ToolMessage 回到 agent)
        │
  agent_node:
    ├── LLM 拿到精确日期 2026-10-06 和 space_id=10
    └── 产生 tool_calls:
        [ {name: "check_seat_availability", args: {space_id: 10, date: "2026-10-06", start_time: "14:00", end_time: "16:00"}} ]
        │
        ▼
  tools_node:
    └── 执行 check_seat_availability → "✅ 区域(自习室) 在 2026-10-06 14:00~16:00 可预约"
        │
        ▼  (ToolMessage 回到 agent)
        │
  agent_node:
    ├── LLM: 可约 → 直接创建！
    └── 产生 tool_calls:
        [ {name: "create_reservation", args: {space_id: 10, date: "2026-10-06", start_time: "14:00", end_time: "16:00"}} ]
        │
        ▼
  tools_node:
    ├── _inject_user_id_into_tool_args → args 里自动塞入 user_id
    └── 执行 create_reservation → "✅ 预约创建成功! 预约ID: 12 ..."
        │
        ▼  (ToolMessage 回到 agent)
        │
  agent_node:
    └── LLM 整理成友好中文 → "好的！已为您预约自习室 明天 14:00-16:00，等待管理员审核 😊"
        │
        ▼
  should_continue: AIMessage 无 tool_calls → END
```

### 6.2 规则问答（RAG 路线）

```
用户: "图书馆占座超过多久会被取消？"
        │
        ▼
  agent_node:
    ├── LLM 判断: 这是规则类问题，数据库里没有，应该查知识库
    └── 产生 tool_calls: [{name: "rag_search", args: {question: "占座 取消"}}]
        │
        ▼
  tools_node:
    └── rag_search → ChromaDB 检索到 "禁止占座超过 30 分钟，超时未到视为自动放弃"
        │
        ▼
  agent_node:
    └── LLM 整理 → "占座超过 30 分钟未到，预约会自动取消哦。"
```

### 6.3 纯查询（直接回答，不调工具）

```
用户: "你好"
        │
        ▼
  agent_node:
    └── LLM: 这不需要任何工具调用，直接回复 "你好！我是图书馆座位预约助手，有什么可以帮你？"
        │
        ▼
  should_continue: AIMessage 无 tool_calls → END
```

---

## 七、API 端点

| 方法 | 路径 | 功能 | 说明 |
|---|---|---|---|
| POST | `/api/chat/ask` | 发送问题给 Agent | body: `{ "question": "...", "session_id": null }`，自动带上当前用户 |
| GET | `/api/chat/sessions` | 我的会话列表 | 按更新时间倒序 |
| GET | `/api/chat/sessions/{id}` | 会话详情（含消息） | 用于切换会话 |
| DELETE | `/api/chat/sessions/{id}` | 删除会话 | 同时级联删除消息 |

所有端点都通过 JWT 认证，`user_id` 从 token 中解析后自动注入到 AgentState。

---

## 八、依赖清单

```toml
# pyproject.toml
dependencies = [
    "langgraph>=0.2.0",
    "langchain>=0.3.0",
    "langchain-core>=0.3.0",
    "langchain-openai>=0.2.0",
    # RAG 相关（rag_search 工具依赖）
    "langchain-chroma>=0.2.0",
    "langchain-text-splitters>=0.3.0",
    "chromadb>=0.5.0",
]
```

安装：

```bash
cd backend
uv sync
```

---

## 九、常见问题

**Q: 助手编造日期（比如明天说错了）？**
A: 确保 System Prompt 里强调了"涉及日期必须先调 get_date_info"，并且这个工具在 ALL_TOOLS 列表里。如果还出现，提高 temperature 到 0.1 试试。

**Q: 助手一直不调 create_reservation，只给信息？**
A: System Prompt 里"能直接做事就别问"这条可能被稀释了。检查一下 prompt 里关于预约流程的描述是否足够明确，特别是"全部参数到齐立刻 create_reservation，不要问确认"这句。

**Q: 工具参数传错了怎么办？**
A: LangChain 的 `bind_tools` 会给 LLM 提供精确的 JSON Schema，大部分情况不会错。如果频繁出错，可以把工具 docstring 写得更详细，或者在 tools 函数内部加参数校验并返回友好错误信息。

**Q: session_id 为 null 时后端怎么处理？**
A: 创建一条新的 chat_session 记录，把 user 消息和 agent 回复都挂在这个 session 下，返回新的 session_id 给前端。

**Q: 如何新增一个工具？**
A: 三步：
1. 在 `tools.py` 里写 `@tool` 函数
2. 加到 `ALL_TOOLS` 列表里
3. 在 System Prompt 里提一下这个工具的用途

LLM 看到新工具的 schema 后会自动学会使用，不需要改 graph.py 的任何代码。

---

## 十、关键设计模式回顾

| 模式 | 位置 | 解决了什么 |
|---|---|---|
| TypedGraph + add 合并器 | `state.py` | Agent 循环中 messages 自动累积，不被覆盖 |
| bind_tools + ToolNode | `graph.py` | 工具注册、调用、结果包装一条龙，不用手动解析 tool_calls |
| 执行层注入 user_id | `_inject_user_id_into_tool_args` | 不让 LLM 管身份，安全且简化 prompt |
| System Prompt 策略驱动 | `SYSTEM_PROMPT` | 助手"聪明"程度的决定因素，LLM 按策略调工具 |
| 工具内自 catch + 返回错误字符串 | `tools.py` 每个 tool | 异常不冒泡到图，LLM 看到错误后可尝试换策略 |
| ask_agent 对外只返回 str | `graph.py::ask_agent` | API 层不用关心 LangGraph 内部结构，只管存消息 |