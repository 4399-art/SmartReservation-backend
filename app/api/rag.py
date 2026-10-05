from pathlib import Path
import hashlib
import uuid

from fastapi import APIRouter, UploadFile, File, Depends
from langchain_core.messages import HumanMessage, AIMessage

from app.common.response import Response
from app.config import RAG_UPLOAD_DIR
from app.database import SessionLocal
from app.dependencies.auth import get_current_user
from app.langgraph.graph import ask_agent
from app.model.chat_session import ChatSession, ChatMessage
from app.model.user import User
from app.rag.document_loader import load_and_split_markdown
from app.rag.vector_store import add_documents, delete_documents_by_source, list_sources
from app.schemas.rag import RagChatRequest

router = APIRouter()

ALLOWED_RAG_EXT = {".md"}


def _find_uploaded_by_source(source_name: str) -> Path | None:
    for p in RAG_UPLOAD_DIR.iterdir():
        if p.is_file() and p.name.endswith(f"_{source_name}"):
            return p
    return None


@router.post("/rag/upload")
async def upload_document(file: UploadFile = File(...)) -> Response:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_RAG_EXT:
        return Response.error(message="仅支持 .md 文件")

    raw = await file.read()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return Response.error(message="文件编码错误，请使用 UTF-8 编码的 Markdown 文件")

    original_name = file.filename or "untitled.md"

    existing_path = _find_uploaded_by_source(original_name)
    if existing_path and existing_path.read_bytes() == raw:
        return Response.success(
            message="文档未修改，跳过重复向量化",
            data={"filename": original_name, "chunks_count": 0, "skipped": True},
        )

    delete_documents_by_source(original_name)
    if existing_path:
        existing_path.unlink(missing_ok=True)

    stored_name = f"{uuid.uuid4().hex}_{original_name}"
    stored_path = RAG_UPLOAD_DIR / stored_name
    stored_path.write_bytes(raw)

    try:
        chunks = load_and_split_markdown(stored_path)
    except Exception as e:
        stored_path.unlink(missing_ok=True)
        return Response.error(message=f"解析文档失败: {e}")

    try:
        add_documents(chunks, source_file=original_name)
    except Exception as e:
        stored_path.unlink(missing_ok=True)
        return Response.error(message=f"写入向量库失败: {e}")

    return Response.success(data={"filename": original_name, "chunks_count": len(chunks)})


@router.get("/rag/documents")
async def list_documents() -> Response:
    sources = list_sources()
    return Response.success(data=sources)


@router.delete("/rag/documents/{filename:path}")
async def delete_document(filename: str) -> Response:
    deleted = delete_documents_by_source(filename)
    if deleted == 0:
        return Response.error(message=f"未找到文档: {filename}")
    return Response.success(data={"filename": filename, "deleted_chunks": deleted})


@router.post("/rag/chat")
async def rag_chat(
    req: RagChatRequest,
    current_user: User = Depends(get_current_user),
) -> Response:
    question = req.question.strip()
    if not question:
        return Response.error(message="问题不能为空")

    db = SessionLocal()
    try:
        session = None
        if req.session_id:
            session = (
                db.query(ChatSession)
                .filter(
                    ChatSession.id == req.session_id,
                    ChatSession.user_id == current_user.id,
                )
                .first()
            )

        if session is None:
            session = ChatSession(user_id=current_user.id)
            db.add(session)
            db.flush()

        chat_history_msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.id)
            .all()
        )
        chat_history = []
        for m in chat_history_msgs:
            if m.role == "user":
                chat_history.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                chat_history.append(AIMessage(content=m.content))

        answer = ask_agent(
            question=question,
            user_id=current_user.id,
            chat_history=chat_history if chat_history else None,
        )

        db.add(ChatMessage(session_id=session.id, role="user", content=question))
        db.add(ChatMessage(session_id=session.id, role="assistant", content=answer))

        if not session.title:
            title = question[:30] + ("..." if len(question) > 30 else "")
            session.title = title

        db.commit()
        db.refresh(session)

        return Response.success(
            data={
                "session_id": session.id,
                "title": session.title,
                "answer": answer,
            }
        )
    except Exception as e:
        db.rollback()
        return Response.error(message=f"智能问答失败: {e}")
    finally:
        db.close()