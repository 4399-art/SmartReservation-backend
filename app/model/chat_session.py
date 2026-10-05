from sqlalchemy import ForeignKey, String, Text, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = {"comment": "AI聊天会话"}

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), comment="所属用户", nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(100), comment="会话标题，自动从首条消息生成")

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.id"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = {"comment": "AI聊天消息"}

    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id"), comment="所属会话", nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), comment="角色: user/assistant", nullable=False)
    content: Mapped[str] = mapped_column(Text, comment="消息内容", nullable=False)
    # 用于关联 tool_call 等元数据，暂存 JSON 字符串
    extra: Mapped[str | None] = mapped_column(Text, comment="额外元数据JSON")

    session: Mapped[ChatSession] = relationship(back_populates="messages")