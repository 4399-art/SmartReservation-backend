from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, description="会话标题，可不传")


class SessionInfo(BaseModel):
    id: int
    title: str | None
    create_time: str
    update_time: str
    message_count: int = 0


class SessionDetail(BaseModel):
    id: int
    title: str | None
    create_time: str
    update_time: str
    messages: list["MessageInfo"] = []


class MessageInfo(BaseModel):
    id: int
    role: str
    content: str


SessionDetail.model_rebuild()