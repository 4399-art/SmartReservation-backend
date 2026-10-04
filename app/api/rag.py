from pathlib import Path
import hashlib
import uuid

from fastapi import APIRouter, UploadFile, File

from app.common.response import Response
from app.config import RAG_UPLOAD_DIR
from app.rag.document_loader import load_and_split_markdown
from app.rag.vector_store import add_documents, delete_documents_by_source, list_sources
from app.rag.chain import ask_rag
from app.schemas.rag import RagChatRequest

router = APIRouter()

ALLOWED_RAG_EXT = {".md"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
        text = raw.decode("utf-8")
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
async def rag_chat(req: RagChatRequest) -> Response:
    question = req.question.strip()
    if not question:
        return Response.error(message="问题不能为空")
    try:
        answer = ask_rag(question)
        return Response.success(data={"answer": answer})
    except Exception as e:
        return Response.error(message=f"智能问答失败: {e}")