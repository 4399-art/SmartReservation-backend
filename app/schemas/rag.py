from pydantic import BaseModel, Field


class RagChatRequest(BaseModel):
    question: str = Field(..., description="用户的问题")


class RagSourceInfo(BaseModel):
    name: str
    chunk_count: int


class RagUploadResponse(BaseModel):
    filename: str
    chunks_count: int
    message: str = "上传成功"