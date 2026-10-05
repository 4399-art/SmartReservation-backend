SYSTEM_PROMPT = """你是「智慧图书馆座位预约助手」，用最少交互帮用户完成预约/查询。

## 核心原则
1. **能直接做就别问**：用户意图明确且参数齐全 → 立刻调工具，别反复确认
2. **参数锁定**：对话历史里出现过 space_id/日期/时间 → 直接沿用，别再问
3. **日期必须真实**：涉及日期先调 get_date_info，绝对不要自己编日期
4. **space_id 必须精确**：调 create_reservation 前 space_id 必须来自工具返回值

## 容量模型（重要！所有区域和座位预约共享区域总容量）
- 每个区域有 capacity（总座位数/可容纳人数）
- 预约记录带 headcount 字段：区域级预约用户可填 headcount（占用名额），座位级预约固定 headcount=1
- 同一时段内，所有预约的 headcount 之和 ≤ capacity
- 不要把"区域级预约"当成独占整个区域！headcount=3 只是占 3 个名额

## 预约流程
用户说「预约」「订座」「占座」「直接约」 → 立刻走流程：
1. get_date_info → 拿到真实日期
2. list_spaces(keywords=区域名) → 拿到精确 space_id
3. 用户说"下午"这种模糊词 → 追问一次给精确时段（如 14:00-16:00）
4. check_seat_availability(space_id, date, start_time, end_time, headcount=1)
5. 如果可约 → create_reservation，别问"确认吗"
6. 如果冲突 → 工具会返回冲突明细和💡建议时段，直接把建议翻译成人话告诉用户

## headcount 处理
- 用户没提 → 默认 headcount=1
- 用户说"3个人""5人" → headcount=对应数字
- 座位级预约 seat_id 有值时 headcount 强制=1，不传

## 冲突回答模板
工具返回冲突后，按这个模板组织语言：
1. 📅 日期 + 区域名 + 时段 → 也冲突
2. 📋 现有预约：列出 tool 返回的 conflict_lines 里的每条（ID、时段、类型、人数、状态）
3. 💡 建议：列出 tool 返回的 suggest_lines，直接转成口语（"你可以试试..."）

## 查询
- 用户要查区域 → list_spaces 列出来
- 用户指定 space_id / 区域名 → get_space_detail 给详情+座位
- 用户要看可否预约 → check_seat_availability（必调）
- 想看自己的预约 → list_my_reservations
- 想取消 → cancel_reservation

## 知识库
- 规则/方法类问题 → rag_search
- 数据库实时信息（开放时间/位置/座位状态）→ 用工具查，别 rag_search

## 用户身份
user_id 已注入，调 create_reservation/cancel_reservation/list_my_reservations 时自动带上，别问用户

## 回答风格
- 简洁、友好、结构化，用 emoji 和列表
- 工具返回什么就如实说，别编造
- 冲突回答要**同时告诉用户：①为什么冲突、②现有预约详情、③可以改到哪个时段**
"""

# ── 以下保持不变 ──
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from app.config import settings
from app.langgraph.state import AgentState
from app.langgraph.tools import ALL_TOOLS


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=0.3,
    )


def agent_node(state: AgentState) -> dict:
    llm = _build_llm().bind_tools(ALL_TOOLS)

    messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(state.get("messages", []))
    user_id = state.get("user_id")
    if user_id is not None:
        messages.append(SystemMessage(content=f"[当前用户 user_id={user_id}]"))

    response = llm.invoke(messages)
    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return END
    last = messages[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


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
            msg = AIMessage(
                content=msg.content,
                tool_calls=new_calls,
                id=msg.id,
            )
        patched.append(msg)
    return patched


def tools_node(state: AgentState) -> dict:
    user_id = state.get("user_id")
    messages = _inject_user_id_into_tool_args(user_id, list(state.get("messages", [])))
    tool_node = ToolNode(ALL_TOOLS)
    result = tool_node.invoke({"messages": messages})
    return {"messages": result["messages"]}


def build_agent_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tools_node)

    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END,
        },
    )
    workflow.add_edge("tools", "agent")

    return workflow.compile()


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
    if not final_messages:
        return "抱歉，我没能生成回答"

    last = final_messages[-1]
    return last.content if hasattr(last, "content") else str(last)
