from pydantic import BaseModel, Field


class ChatHistoryItem(BaseModel):
    role: str = Field(..., description="user 或 assistant")
    content: str


class RagChatRequest(BaseModel):
    question: str = Field(..., description="用户的问题")
    session_id: int | None = Field(default=None, description="会话ID，新会话不传")
    chat_history: list[ChatHistoryItem] = Field(
        default_factory=list, description="前端传来的历史（若传了session_id则忽略，后端从DB加载）"
    )


class RagSourceInfo(BaseModel):
    name: str
    chunk_count: int


class RagUploadResponse(BaseModel):
    filename: str
    chunks_count: int
    message: str = "上传成功"