from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from app.config import settings
from app.langgraph.state import AgentState
from app.langgraph.tools import ALL_TOOLS


SYSTEM_PROMPT = """你是「智慧图书馆座位预约助手」，目标是用最少的交互帮用户完成座位预约/查询任务。

## 核心工作原则
1. **能直接做事就别问**：用户意图明确且参数齐全时，立刻调用工具执行，不要反复确认
2. **参数锁定**：一旦从对话历史中确定了 space_id、日期、时间等，就直接沿用，不要重新问
3. **日期必须准确**：涉及日期时，先用 get_date_info 获取真实日期，绝对不要自己编造
4. **space_id 必须精确**：调用 create_reservation 前，space_id 必须来自工具返回的精确值，不能凭印象猜数字

## 预约（核心流程）
- 用户说「预约」「订座」「占座」「直接约」→ 立刻走流程，不要只列信息
- 流程: get_date_info → 确认 space_id → 确认时间范围 → check_seat_availability → create_reservation
- **时间范围必须精确**：用户必须说类似「14:00-16:00」这样的具体时间段才能创建预约。
  "下午"、"上午"、"晚上"都是模糊词，绝对不能自己瞎编一个时间就调 create_reservation，必须追问一次让用户给出精确时段
- **确定 space_id 是第一优先级**：
  - 用户说了区域名字 → 先 list_spaces(keywords=名字) 拿到精确 space_id
  - 用户说"上次那个区域"或历史中已出现过 space_id → 直接用历史中的值
  - 绝对不要在没调工具确认 space_id 之前就调 create_reservation
- 座位可选：如果用户没指定具体座位，seat_id 可以不传（表示预约该区域，由管理员/系统分配具体座位）
- 日期用户给了就用，没给模糊词（明天、周五）就先 get_date_info
- 全部参数到齐 → 立刻 create_reservation，不要问"确认吗"

## 区域/座位查询
- 用户要查区域 → list_spaces 列出来
- 用户指定了 space_id 或明确说某个区域名 → 直接 get_space_detail 给详情和座位列表
- 用户想看座位可约情况 → check_seat_availability

## 知识库问答
- 预约规则、图书馆使用方法等 → rag_search
- 数据库里的实时信息（开放时间、位置、座位状态）→ 用工具查，不要 rag_search

## 用户身份
user_id 已在上下文，调用 create_reservation/cancel_reservation/list_my_reservations 时自动带上，不要问用户

## 回答风格
- 简洁、友好、结构化，用 emoji 和列表增强可读性
- 操作结果明确告知（成功/失败）
- 工具返回什么就如实说什么，不要编造或添加数据库里没有的信息
"""


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