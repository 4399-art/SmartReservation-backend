from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import settings, CHROMA_DIR, RAG_COLLECTION_NAME


def _get_embeddings():
    provider = (settings.EMBEDDING_PROVIDER or "").strip().lower()
    if provider == "dashscope":
        return _get_dashscope_embeddings()
    return _get_openai_embeddings()


def _get_openai_embeddings():
    from app.rag.embeddings import OpenAICompatibleEmbeddings

    api_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
    base_url = settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL
    model = settings.EMBEDDING_MODEL

    if not api_key or not model:
        raise ValueError(
            "Embedding 配置未找到。请在 .env 中设置 EMBEDDING_API_KEY / EMBEDDING_BASE_URL / EMBEDDING_MODEL，"
            "或设置 EMBEDDING_PROVIDER=dashscope 并配置 DASHSCOPE_API_KEY。"
        )

    return OpenAICompatibleEmbeddings(api_key=api_key, base_url=base_url, model=model)


def _get_dashscope_embeddings():
    from langchain_community.embeddings import DashScopeEmbeddings

    api_key = settings.DASHSCOPE_API_KEY
    model = settings.EMBEDDING_MODEL or "text-embedding-v3"

    if not api_key:
        raise ValueError(
            "使用 DashScope Embedding 请在 .env 中设置 DASHSCOPE_API_KEY。"
        )

    return DashScopeEmbeddings(model=model, dashscope_api_key=api_key)


_vector_store: Chroma | None = None


def get_vector_store() -> Chroma:
    global _vector_store
    if _vector_store is None:
        _vector_store = Chroma(
            persist_directory=str(CHROMA_DIR),
            collection_name=RAG_COLLECTION_NAME,
            embedding_function=_get_embeddings(),
        )
    return _vector_store


def add_documents(documents: list[Document], source_file: str) -> list[str]:
    store = get_vector_store()
    texts = [d.page_content for d in documents]
    metadatas = [dict(d.metadata, source=source_file) for d in documents]
    ids = store.add_texts(texts=texts, metadatas=metadatas)
    return ids


def delete_documents_by_source(source_file: str) -> int:
    store = get_vector_store()
    existing = store.get(where={"source": source_file})
    ids = existing.get("ids", [])
    if ids:
        store.delete(ids=ids)
    return len(ids)


def list_sources() -> list[str]:
    store = get_vector_store()
    existing = store.get(include=["metadatas"])
    metadatas = existing.get("metadatas", [])
    sources = set()
    for meta in metadatas:
        src = meta.get("source") if isinstance(meta, dict) else None
        if src:
            sources.add(src)
    return sorted(sources)