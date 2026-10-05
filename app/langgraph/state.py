from typing import TypedDict, Annotated
from operator import add

from langchain_core.messages import BaseMessage


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add]
    user_id: int