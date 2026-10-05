from fastapi import APIRouter, Depends
from sqlalchemy import desc, func

from app.common.response import Response
from app.database import SessionLocal
from app.dependencies.auth import get_current_user
from app.model.chat_session import ChatSession, ChatMessage
from app.model.user import User
from app.schemas.chat import SessionCreate

router = APIRouter()


def _fmt_time(dt) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@router.post("/chat/sessions")
async def create_session(
    body: SessionCreate,
    current_user: User = Depends(get_current_user),
) -> Response:
    db = SessionLocal()
    try:
        session = ChatSession(user_id=current_user.id, title=body.title)
        db.add(session)
        db.commit()
        db.refresh(session)
        return Response.success(data={"id": session.id, "title": session.title})
    finally:
        db.close()


@router.get("/chat/sessions")
async def list_sessions(
    current_user: User = Depends(get_current_user),
) -> Response:
    db = SessionLocal()
    try:
        rows = (
            db.query(
                ChatSession.id,
                ChatSession.title,
                ChatSession.create_time,
                ChatSession.update_time,
                func.count(ChatMessage.id).label("message_count"),
            )
            .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
            .filter(ChatSession.user_id == current_user.id)
            .group_by(ChatSession.id)
            .order_by(desc(ChatSession.update_time))
            .all()
        )
        data = [
            {
                "id": r.id,
                "title": r.title,
                "create_time": _fmt_time(r.create_time),
                "update_time": _fmt_time(r.update_time),
                "message_count": r.message_count,
            }
            for r in rows
        ]
        return Response.success(data=data)
    finally:
        db.close()


@router.get("/chat/sessions/latest")
async def get_latest_session(
    current_user: User = Depends(get_current_user),
) -> Response:
    db = SessionLocal()
    try:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.user_id == current_user.id)
            .order_by(desc(ChatSession.update_time))
            .first()
        )
        if not session:
            return Response.success(data=None)
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.id)
            .all()
        )
        return Response.success(
            data={
                "id": session.id,
                "title": session.title,
                "create_time": _fmt_time(session.create_time),
                "update_time": _fmt_time(session.update_time),
                "messages": [
                    {"id": m.id, "role": m.role, "content": m.content} for m in messages
                ],
            }
        )
    finally:
        db.close()


@router.get("/chat/sessions/{session_id}")
async def get_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
) -> Response:
    db = SessionLocal()
    try:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
            .first()
        )
        if not session:
            return Response.error(message="会话不存在")
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id)
            .all()
        )
        return Response.success(
            data={
                "id": session.id,
                "title": session.title,
                "create_time": _fmt_time(session.create_time),
                "update_time": _fmt_time(session.update_time),
                "messages": [
                    {"id": m.id, "role": m.role, "content": m.content} for m in messages
                ],
            }
        )
    finally:
        db.close()


@router.put("/chat/sessions/{session_id}/title")
async def rename_session(
    session_id: int,
    body: dict,
    current_user: User = Depends(get_current_user),
) -> Response:
    db = SessionLocal()
    try:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
            .first()
        )
        if not session:
            return Response.error(message="会话不存在")
        session.title = body.get("title", session.title)
        db.commit()
        return Response.success(message="已更新")
    finally:
        db.close()


@router.delete("/chat/sessions/{session_id}")
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
) -> Response:
    db = SessionLocal()
    try:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
            .first()
        )
        if not session:
            return Response.error(message="会话不存在")
        db.delete(session)
        db.commit()
        return Response.success(message="会话已删除")
    finally:
        db.close()